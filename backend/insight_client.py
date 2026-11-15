"""
NASA InSight: Mars Weather Service API Client & Offline-First Normalizer.

Queries GET https://api.nasa.gov/insight_weather/?api_key=...&feedtype=json&ver=1.0
and caches per-Sol Elysium Planitia ambient weather summaries (AT, HWS, PRE, WD,
Season, First_UTC, Last_UTC, and validity_checks) in SQLite.

Scientific & Operational Integrity Guarantees:
- Never exposes the raw NASA_API_KEY in API payloads or frontend bundles.
- Respects TARS Care OFFLINE blackout mode: blocks outbound polling while preserving
  locally cached SQLite Sol summaries.
- Explicitly distinguishes archival external Martian surface ambient conditions
  (InSight power-limited archive at Elysium Planitia, last updated 2021) from
  pressurized crew habitat ECLSS sensors; never mutates cabin telemetry or EVA gating.
- Handles missing sensor keys (AT, HWS, PRE, WD) and empty sol_keys gracefully per
  NASA JPL / Cornell power-management documentation.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import database
from donki_client import get_donki_config_summary, resolve_nasa_api_key
from marscare_enhancer import normalize_comm_mode

INSIGHT_BASE_URL = "https://api.nasa.gov/insight_weather/"
_INSIGHT_AUTO_LOCK = threading.Lock()
_INSIGHT_AUTO_RUNNING = False


def build_insight_url(
    api_key: str,
    feedtype: str = "json",
    version: str = "1.0",
) -> Tuple[str, str]:
    clean_feed = "json" if str(feedtype).lower() != "json" else "json"
    clean_ver = str(version or "1.0").strip() or "1.0"
    display_qs = urllib.parse.urlencode({"feedtype": clean_feed, "ver": clean_ver})
    full_qs = urllib.parse.urlencode({"api_key": api_key, "feedtype": clean_feed, "ver": clean_ver})
    return f"{INSIGHT_BASE_URL}?{full_qs}", f"{INSIGHT_BASE_URL}?{display_qs}"


def _http_get_insight_json(url: str, timeout_sec: float = 10.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TARS-Care-InSight-Weather-Client/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw_bytes = resp.read()
        if not raw_bytes:
            return {}
        return json.loads(raw_bytes.decode("utf-8", errors="replace"))


def _extract_stat_block(block: Any) -> Dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("av", "mn", "mx", "ct"):
        if block.get(k) is not None:
            out[k] = round(float(block[k]), 3) if k != "ct" else int(block[k])
    return out


def _extract_wind_direction(wd_raw: Any) -> Dict[str, Any]:
    if not isinstance(wd_raw, dict):
        return {}
    bins: List[Dict[str, Any]] = []
    for k, val in wd_raw.items():
        if k == "most_common" or not isinstance(val, dict):
            continue
        try:
            sector_idx = int(k)
        except ValueError:
            sector_idx = len(bins)
        bins.append(
            {
                "sector": sector_idx,
                "compass_degrees": float(val.get("compass_degrees", sector_idx * 22.5)),
                "compass_point": str(val.get("compass_point") or ""),
                "compass_right": float(val.get("compass_right", 0.0)),
                "compass_up": float(val.get("compass_up", 0.0)),
                "ct": int(val.get("ct", 0)),
            }
        )
    bins.sort(key=lambda b: b["sector"])
    mc_raw = wd_raw.get("most_common")
    most_common: Optional[Dict[str, Any]] = None
    if isinstance(mc_raw, dict):
        most_common = {
            "compass_degrees": float(mc_raw.get("compass_degrees", 0.0)),
            "compass_point": str(mc_raw.get("compass_point") or ""),
            "ct": int(mc_raw.get("ct", 0)),
        }
    return {
        "most_common": most_common,
        "bins": bins,
    }


def _normalize_sol(
    sol_id: str,
    sol_raw: Dict[str, Any],
    validity_raw: Dict[str, Any],
    fetched_at: str,
) -> Dict[str, Any]:
    at = _extract_stat_block(sol_raw.get("AT"))
    hws = _extract_stat_block(sol_raw.get("HWS"))
    pre = _extract_stat_block(sol_raw.get("PRE"))
    wd = _extract_wind_direction(sol_raw.get("WD"))

    missing_sensors: List[str] = []
    if not at:
        missing_sensors.append("AT")
    if not hws:
        missing_sensors.append("HWS")
    if not pre:
        missing_sensors.append("PRE")
    if not wd or not wd.get("bins"):
        missing_sensors.append("WD")

    validity_summary: Dict[str, Any] = {}
    if isinstance(validity_raw, dict):
        for sensor_key in ("AT", "HWS", "PRE", "WD"):
            s_val = validity_raw.get(sensor_key)
            if isinstance(s_val, dict):
                hours = s_val.get("sol_hours_with_data") or []
                validity_summary[sensor_key] = {
                    "valid": bool(s_val.get("valid", False)),
                    "hours_count": len(hours) if isinstance(hours, list) else 0,
                }

    return {
        "sol_id": str(sol_id),
        "first_utc": str(sol_raw.get("First_UTC") or ""),
        "last_utc": str(sol_raw.get("Last_UTC") or ""),
        "season": str(sol_raw.get("Season") or ""),
        "northern_season": str(sol_raw.get("Northern_season") or ""),
        "southern_season": str(sol_raw.get("Southern_season") or ""),
        "month_ordinal": int(sol_raw["Month_ordinal"]) if sol_raw.get("Month_ordinal") is not None else None,
        "at": at,
        "hws": hws,
        "pre": pre,
        "wd": wd,
        "validity": validity_summary,
        "missing_sensors": missing_sensors,
        "data_provenance": "REAL_NASA_INSIGHT",
        "fetched_at": fetched_at,
    }


def sync_insight_weather(feedtype: str = "json", version: str = "1.0") -> Dict[str, Any]:
    """Fetch NASA InSight Mars Weather JSON feed and cache per-Sol summaries into SQLite."""
    comm_state = database.fetch_system_state("comm_state") or {}
    comm_norm = normalize_comm_mode(comm_state)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_meta = database.fetch_insight_sync_meta()

    if comm_norm["mode"] == "OFFLINE":
        blocked_meta = {
            "last_sync_at": prev_meta.get("last_sync_at", ""),
            "last_sync_status": "BLOCKED_OFFLINE",
            "last_sync_message": (
                "Earth link is in OFFLINE blackout — external NASA InSight polling paused. "
                "Displaying locally cached SQLite Elysium Planitia weather Sols."
            ),
            "sol_keys": prev_meta.get("sol_keys", []),
            "endpoint": prev_meta.get("endpoint", f"{INSIGHT_BASE_URL}?feedtype=json&ver={version}"),
        }
        database.update_insight_sync_meta(blocked_meta)
        return {
            "status": "BLOCKED_OFFLINE",
            "message": blocked_meta["last_sync_message"],
            "fetched_count": 0,
            "sync_meta": blocked_meta,
        }

    api_key, _ = resolve_nasa_api_key()
    full_url, redacted_url = build_insight_url(api_key=api_key, feedtype=feedtype, version=version)

    try:
        payload = _http_get_insight_json(full_url)
    except urllib.error.HTTPError as exc:
        err_msg = (
            "NASA API rate limit reached (HTTP 429)"
            if exc.code == 429
            else ("NASA API key rejected (HTTP 403)" if exc.code == 403 else f"HTTP {exc.code}: {exc.reason}")
        )
        err_meta = {
            "last_sync_at": prev_meta.get("last_sync_at", ""),
            "last_sync_status": "RATE_LIMITED" if exc.code == 429 else "ERROR",
            "last_sync_message": f"NASA InSight sync failed ({err_msg}); previously cached Sol summaries preserved.",
            "sol_keys": prev_meta.get("sol_keys", []),
            "endpoint": redacted_url,
        }
        database.update_insight_sync_meta(err_meta)
        return {
            "status": err_meta["last_sync_status"],
            "message": err_meta["last_sync_message"],
            "fetched_count": 0,
            "sync_meta": err_meta,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        err_msg = f"Network/parse error: {type(exc).__name__}"
        err_meta = {
            "last_sync_at": prev_meta.get("last_sync_at", ""),
            "last_sync_status": "ERROR",
            "last_sync_message": f"NASA InSight sync failed ({err_msg}); previously cached Sol summaries preserved.",
            "sol_keys": prev_meta.get("sol_keys", []),
            "endpoint": redacted_url,
        }
        database.update_insight_sync_meta(err_meta)
        return {
            "status": "ERROR",
            "message": err_meta["last_sync_message"],
            "fetched_count": 0,
            "sync_meta": err_meta,
        }

    if not isinstance(payload, dict):
        payload = {}

    raw_sol_keys = payload.get("sol_keys") or []
    sol_keys = [str(s) for s in raw_sol_keys if isinstance(payload.get(str(s)), dict)]
    validity_checks = payload.get("validity_checks") or {}

    normalized_sols = [
        _normalize_sol(
            sol_id=sol_id,
            sol_raw=payload[sol_id],
            validity_raw=validity_checks.get(sol_id, {}) if isinstance(validity_checks, dict) else {},
            fetched_at=now_iso,
        )
        for sol_id in sol_keys
    ]
    saved_count = database.upsert_insight_sols(normalized_sols)

    if saved_count == 0:
        sync_status = "EMPTY_GAP"
        sync_msg = (
            "NASA InSight API returned 0 Sol summaries (active sensor/power-management data gap); "
            "existing SQLite cache remains intact."
        )
    else:
        any_missing = any(bool(s["missing_sensors"]) for s in normalized_sols)
        sync_status = "SYNCED"
        sync_msg = (
            f"Synced {saved_count} NASA InSight Sol summaries from Elysium Planitia "
            f"(Sols {', '.join(sol_keys)}"
            + ("; partial missing sensors flagged)." if any_missing else ").")
        )

    new_meta = {
        "last_sync_at": now_iso,
        "last_sync_status": sync_status,
        "last_sync_message": sync_msg,
        "sol_keys": sol_keys,
        "endpoint": redacted_url,
    }
    database.update_insight_sync_meta(new_meta)

    return {
        "status": sync_status,
        "message": sync_msg,
        "fetched_count": saved_count,
        "sync_meta": new_meta,
    }


def should_auto_sync_insight(max_age_hours: float = 12.0) -> bool:
    """Return True when Earth link is not OFFLINE and InSight cache is empty or stale."""
    comm_state = database.fetch_system_state("comm_state") or {}
    if normalize_comm_mode(comm_state)["mode"] == "OFFLINE":
        return False
    meta = database.fetch_insight_sync_meta()
    status = str(meta.get("last_sync_status") or "NEVER_SYNCED")
    last_at = str(meta.get("last_sync_at") or "").strip()
    if not last_at or status in {"NEVER_SYNCED", "BLOCKED_OFFLINE", "ERROR"}:
        return True
    try:
        dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        return age_hours >= max_age_hours
    except ValueError:
        return True


def trigger_background_insight_auto_sync(max_age_hours: float = 12.0) -> bool:
    """Kick off a non-blocking NASA InSight cache refresh in a background daemon thread."""
    global _INSIGHT_AUTO_RUNNING
    if not should_auto_sync_insight(max_age_hours=max_age_hours):
        return False
    with _INSIGHT_AUTO_LOCK:
        if _INSIGHT_AUTO_RUNNING:
            return False
        _INSIGHT_AUTO_RUNNING = True

    def _runner() -> None:
        global _INSIGHT_AUTO_RUNNING
        try:
            sync_insight_weather()
        except Exception:
            pass
        finally:
            with _INSIGHT_AUTO_LOCK:
                _INSIGHT_AUTO_RUNNING = False

    threading.Thread(target=_runner, daemon=True, name="tars-insight-autosync").start()
    return True


def build_insight_public_state(limit: int = 14) -> Dict[str, Any]:
    """Assemble secret-free NASA InSight Elysium Planitia weather state for frontend consumption."""
    sols = database.fetch_insight_sols(limit=limit)
    sync_meta = database.fetch_insight_sync_meta()
    cfg = get_donki_config_summary()
    latest_sol = sols[0] if sols else None

    latest_pressure_pa = (latest_sol or {}).get("pre", {}).get("av") if latest_sol else None
    latest_temp_av = (latest_sol or {}).get("at", {}).get("av") if latest_sol else None
    latest_temp_min = (latest_sol or {}).get("at", {}).get("mn") if latest_sol else None
    latest_temp_max = (latest_sol or {}).get("at", {}).get("mx") if latest_sol else None
    latest_wind_av = (latest_sol or {}).get("hws", {}).get("av") if latest_sol else None
    latest_wind_dir = ((latest_sol or {}).get("wd") or {}).get("most_common") or {}
    sols_with_missing_sensors = [s["sol_id"] for s in sols if s.get("missing_sensors")]

    return {
        "config": {
            "key_status": cfg["key_status"],
            "key_source": cfg["key_source"],
            "using_custom_key": cfg["using_custom_key"],
            "endpoint": sync_meta.get("endpoint"),
        },
        "sync_meta": sync_meta,
        "summary": {
            "sol_count": len(sols),
            "latest_sol_id": latest_sol["sol_id"] if latest_sol else None,
            "landing_site": "Elysium Planitia (4.5°N, 135.6°E)",
            "data_archive_notice": (
                "Archival NASA JPL / Cornell InSight feed (last updated 2021; power management & sensor outages can leave multi-Sol gaps)."
            ),
            "latest_pressure_pa": latest_pressure_pa,
            "latest_pressure_kpa": round(latest_pressure_pa / 1000.0, 3) if latest_pressure_pa is not None else None,
            "latest_temp_av_c": latest_temp_av,
            "latest_temp_min_c": latest_temp_min,
            "latest_temp_max_c": latest_temp_max,
            "diurnal_temp_swing_c": (
                round(latest_temp_max - latest_temp_min, 1)
                if (latest_temp_max is not None and latest_temp_min is not None)
                else None
            ),
            "latest_wind_av_ms": latest_wind_av,
            "latest_wind_compass": latest_wind_dir.get("compass_point") if isinstance(latest_wind_dir, dict) else None,
            "sols_with_missing_sensors": sols_with_missing_sensors,
        },
        "sols": sols,
    }
