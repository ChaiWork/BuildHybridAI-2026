"""
NASA DONKI (Space Weather Database Of Notifications, Knowledge, Information)
Client, Query Builder, Offline-First Cache Normalizer, and Heliospheric Advisory Helper.

Supports all 11 official NASA DONKI component services:
  1. CME                 - Coronal Mass Ejection
  2. CMEAnalysis         - Coronal Mass Ejection (CME) Analysis
  3. GST                 - Geomagnetic Storm
  4. IPS                 - Interplanetary Shock
  5. FLR                 - Solar Flare
  6. SEP                 - Solar Energetic Particle
  7. MPC                 - Magnetopause Crossing
  8. RBE                 - Radiation Belt Enhancement
  9. HSS                 - High Speed Stream
 10. WSAEnlilSimulations - WSA+Enlil Solar Wind Prediction Simulation
 11. notifications       - SWRC Space Weather Notifications

Safety & Security Guarantees:
- Never exposes the raw NASA_API_KEY in public state snapshots, logs, or frontend payloads.
- Respects TARS Care Earth link mode: blocks live outbound HTTP polling during OFFLINE blackout
  while preserving SQLite-cached DONKI records for autonomous crew inspection.
- Never fabricates or overwrites personal radiation absorbed dose (mGy) or effective dose (mSv)
  measurements; personal dosimetry continues to come strictly from onboard dosimeters.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import database
from marscare_enhancer import normalize_comm_mode

DONKI_BASE_URL = "https://api.nasa.gov/DONKI"
DOTENV_PATH = Path(__file__).resolve().parent / ".env"
DEFAULT_DONKI_LOOKBACK_DAYS = 30
_AUTO_SYNC_LOCK = threading.Lock()
_AUTO_SYNC_RUNNING = False

DONKI_SERVICE_CATALOG: List[Dict[str, str]] = [
    {
        "id": "CME",
        "name": "Coronal Mass Ejection (CME)",
        "endpoint": "/DONKI/CME",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "Large solar plasma & magnetic field ejections measured by coronagraphs; informs deep-space radiation storm watch.",
    },
    {
        "id": "CMEAnalysis",
        "name": "CME Kinematic Analysis",
        "endpoint": "/DONKI/CMEAnalysis",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "Measured CME speed (km/s), half-angle, source longitude/latitude, and WSA-Enlil propagation inputs.",
    },
    {
        "id": "GST",
        "name": "Geomagnetic Storm (GST)",
        "endpoint": "/DONKI/GST",
        "regime_scope": "EARTH_MAGNETOSPHERE",
        "description": "Earth geomagnetic Kp disturbances; relevant to LEO/cislunar ops & Earth ground-station links (Mars lacks a global dipole).",
    },
    {
        "id": "IPS",
        "name": "Interplanetary Shock (IPS)",
        "endpoint": "/DONKI/IPS",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "Shock fronts propagating through the heliosphere past inner-planet or L1 monitors.",
    },
    {
        "id": "FLR",
        "name": "Solar Flare (FLR)",
        "endpoint": "/DONKI/FLR",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "X-ray solar flare bursts (C/M/X classes) associated with prompt photon bursts, HF blackouts, and CME/SEP onsets.",
    },
    {
        "id": "SEP",
        "name": "Solar Energetic Particle (SEP)",
        "endpoint": "/DONKI/SEP",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "High-energy solar proton/ion events — highest acute radiation relevance for EVA & deep-space storm shelter decisions.",
    },
    {
        "id": "MPC",
        "name": "Magnetopause Crossing (MPC)",
        "endpoint": "/DONKI/MPC",
        "regime_scope": "EARTH_MAGNETOSPHERE",
        "description": "Earth magnetopause compression events during solar wind pressure surges (Earth/geosynchronous regime).",
    },
    {
        "id": "RBE",
        "name": "Radiation Belt Enhancement (RBE)",
        "endpoint": "/DONKI/RBE",
        "regime_scope": "EARTH_MAGNETOSPHERE",
        "description": "Van Allen outer electron belt enhancements (Earth orbital regime, not Mars surface exposure).",
    },
    {
        "id": "HSS",
        "name": "High Speed Stream (HSS)",
        "endpoint": "/DONKI/HSS",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "Coronal-hole fast solar wind streams sweeping across the heliosphere.",
    },
    {
        "id": "WSAEnlilSimulations",
        "name": "WSA+Enlil Simulation",
        "endpoint": "/DONKI/WSAEnlilSimulations",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "MHD heliospheric propagation model predicting CME shock arrival time at Earth, Mars, or spacecraft.",
    },
    {
        "id": "notifications",
        "name": "SWRC Notifications",
        "endpoint": "/DONKI/notifications",
        "regime_scope": "HELIOSPHERIC_DEEP_SPACE",
        "description": "Official Space Weather Research Center alerts summarizing coupled FLR/CME/SEP/GST events.",
    },
]

DONKI_SERVICE_MAP: Dict[str, Dict[str, str]] = {item["id"]: item for item in DONKI_SERVICE_CATALOG}
ALL_DONKI_SERVICE_IDS: List[str] = [item["id"] for item in DONKI_SERVICE_CATALOG]


def _read_key_from_dotenv(env_path: Path = DOTENV_PATH) -> str:
    if not env_path.exists():
        return ""
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "NASA_API_KEY":
                cleaned = v.strip().strip('"').strip("'")
                if cleaned:
                    return cleaned
    except OSError:
        return ""
    return ""


def resolve_nasa_api_key() -> Tuple[str, str]:
    """
    Resolve NASA_API_KEY without ever exposing it to frontend callers.
    Priority: local SQLite config -> process env var -> backend/.env -> DEMO_KEY.
    """
    try:
        cfg = database.fetch_donki_secret_config()
        if cfg.get("api_key"):
            return cfg["api_key"], "LOCAL_CONFIG"
    except Exception:
        pass

    env_val = os.environ.get("NASA_API_KEY", "").strip()
    if env_val:
        return env_val, "ENV_VAR"

    dotenv_val = _read_key_from_dotenv()
    if dotenv_val:
        return dotenv_val, "DOTENV_FILE"

    return "DEMO_KEY", "DEMO_KEY"


def redact_api_key(api_key: str) -> str:
    if not api_key or api_key == "DEMO_KEY":
        return "DEMO_KEY (rate-limited)"
    if len(api_key) <= 8:
        return "Configured (****)"
    return f"Configured ({api_key[:4]}...{api_key[-4:]})"


def get_donki_config_summary() -> Dict[str, Any]:
    key, source = resolve_nasa_api_key()
    try:
        cfg = database.fetch_donki_secret_config()
        auto_eva = bool(cfg.get("auto_advisory_in_eva", True))
    except Exception:
        auto_eva = True
    return {
        "key_status": redact_api_key(key),
        "key_source": source,
        "using_custom_key": key != "DEMO_KEY",
        "auto_advisory_in_eva": auto_eva,
        "base_url": DONKI_BASE_URL,
        "services_count": len(DONKI_SERVICE_CATALOG),
    }


def _default_date_window(days: int = DEFAULT_DONKI_LOOKBACK_DAYS) -> Tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    return start.isoformat(), today.isoformat()


def _validate_iso_date(date_str: str, fallback: str) -> str:
    cleaned = str(date_str or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned
    return fallback


def build_donki_request(
    service_id: str,
    start_date: str,
    end_date: str,
    api_key: str,
    most_accurate_only: bool = True,
    cme_speed: int = 500,
    cme_half_angle: int = 30,
    catalog: str = "ALL",
    ips_location: str = "ALL",
    notification_type: str = "all",
) -> Tuple[str, str]:
    """
    Build exact NASA DONKI endpoint URL and a key-redacted display endpoint string.
    Matches the 11 official NASA DONKI API component specifications.
    """
    if service_id not in DONKI_SERVICE_MAP:
        raise ValueError(f"Unsupported NASA DONKI service '{service_id}'")

    params: Dict[str, str] = {
        "startDate": start_date,
        "endDate": end_date,
    }
    if service_id == "CMEAnalysis":
        params["mostAccurateOnly"] = "true" if most_accurate_only else "false"
        params["speed"] = str(max(0, int(cme_speed)))
        params["halfAngle"] = str(max(0, int(cme_half_angle)))
        params["catalog"] = catalog or "ALL"
    elif service_id == "IPS":
        if ips_location:
            params["location"] = ips_location
        if catalog:
            params["catalog"] = catalog
    elif service_id == "notifications":
        params["type"] = notification_type or "all"

    display_qs = urllib.parse.urlencode(params)
    full_params = dict(params)
    full_params["api_key"] = api_key
    full_qs = urllib.parse.urlencode(full_params)

    endpoint_path = DONKI_SERVICE_MAP[service_id]["endpoint"]
    full_url = f"https://api.nasa.gov{endpoint_path}?{full_qs}"
    redacted_url = f"https://api.nasa.gov{endpoint_path}?{display_qs}"
    return full_url, redacted_url


def _extract_linked_ids(raw_item: Dict[str, Any]) -> List[str]:
    linked = raw_item.get("linkedEvents") or []
    out: List[str] = []
    if isinstance(linked, list):
        for entry in linked:
            if isinstance(entry, dict) and entry.get("activityID"):
                out.append(str(entry["activityID"]))
    return out


def _pick_flare_severity(class_type: str) -> str:
    ct = str(class_type or "").upper().strip()
    if ct.startswith("X"):
        return "CRITICAL"
    if ct.startswith("M"):
        try:
            mag = float(ct[1:])
            if mag >= 5.0:
                return "CRITICAL"
        except ValueError:
            pass
        return "WARNING"
    return "INFO"


def _normalize_donki_item(service_id: str, raw_item: Dict[str, Any], fetched_at: str) -> Dict[str, Any]:
    meta = DONKI_SERVICE_MAP[service_id]
    regime_scope = meta["regime_scope"]
    linked_ids = _extract_linked_ids(raw_item)
    source_url = str(raw_item.get("link") or raw_item.get("messageURL") or "")
    severity = "INFO"
    metrics: Dict[str, Any] = {}

    if service_id == "CME":
        activity_id = str(raw_item.get("activityID") or f"CME-{raw_item.get('startTime', fetched_at)}")
        start_time = str(raw_item.get("startTime") or fetched_at)
        analyses = raw_item.get("cmeAnalyses") or []
        best = next((a for a in analyses if isinstance(a, dict) and a.get("isMostAccurate")), analyses[0] if analyses else {})
        speed = best.get("speed") if isinstance(best, dict) else None
        half_angle = best.get("halfAngle") if isinstance(best, dict) else None
        cme_type = best.get("type") if isinstance(best, dict) else None
        if isinstance(speed, (int, float)):
            metrics["speed_km_s"] = speed
            if speed >= 1500:
                severity = "CRITICAL"
            elif speed >= 800:
                severity = "WARNING"
        if half_angle is not None:
            metrics["half_angle_deg"] = half_angle
        if raw_item.get("sourceLocation"):
            metrics["source_location"] = raw_item["sourceLocation"]
        speed_txt = f"{speed} km/s ({cme_type or 'CME'})" if speed is not None else "analysis pending"
        title = f"CME {activity_id} · {speed_txt}"
        note = str(raw_item.get("note") or "").strip()
        summary = note[:320] if note else f"Coronal Mass Ejection observed at {start_time} (source {raw_item.get('sourceLocation') or 'unspecified'})."

    elif service_id == "CMEAnalysis":
        activity_id = str(raw_item.get("associatedCMEID") or f"CMEA-{raw_item.get('time21_5', fetched_at)}")
        start_time = str(raw_item.get("time21_5") or fetched_at)
        speed = raw_item.get("speed")
        half_angle = raw_item.get("halfAngle")
        cme_type = raw_item.get("type") or "S"
        if isinstance(speed, (int, float)):
            metrics["speed_km_s"] = speed
            if speed >= 1500:
                severity = "CRITICAL"
            elif speed >= 800:
                severity = "WARNING"
        if half_angle is not None:
            metrics["half_angle_deg"] = half_angle
        if raw_item.get("catalog"):
            metrics["catalog"] = raw_item["catalog"]
        title = f"CME Analysis · {speed or '?'} km/s · Half-Angle {half_angle or '?'}° ({cme_type})"
        summary = str(raw_item.get("note") or f"Kinematic CME fit for {activity_id} in catalog {raw_item.get('catalog', 'ALL')}.")[:320]
        event_uid = f"CMEAnalysis:{activity_id}:{start_time}"
        return {
            "event_uid": event_uid,
            "service_type": service_id,
            "activity_id": activity_id,
            "start_time": start_time,
            "severity": severity,
            "regime_scope": regime_scope,
            "title": title,
            "summary": summary,
            "linked_ids": linked_ids,
            "source_url": source_url,
            "metrics": metrics,
            "raw_payload": raw_item,
            "data_provenance": "LIVE_NASA_DONKI",
            "fetched_at": fetched_at,
        }

    elif service_id == "GST":
        activity_id = str(raw_item.get("gstID") or f"GST-{raw_item.get('startTime', fetched_at)}")
        start_time = str(raw_item.get("startTime") or fetched_at)
        kp_entries = raw_item.get("allKpIndex") or []
        kp_vals = [float(k["kpIndex"]) for k in kp_entries if isinstance(k, dict) and k.get("kpIndex") is not None]
        max_kp = max(kp_vals) if kp_vals else None
        if max_kp is not None:
            metrics["kp_max"] = max_kp
            if max_kp >= 7.0:
                severity = "CRITICAL"
            elif max_kp >= 5.0:
                severity = "WARNING"
        title = f"Geomagnetic Storm {activity_id}" + (f" · Peak Kp {max_kp:.1f}" if max_kp is not None else "")
        summary = (
            f"Earth magnetospheric disturbance recorded (max Kp {max_kp if max_kp is not None else 'N/A'}). "
            "Applies to Earth LEO/cislunar regimes & DSN links; Mars lacks a global dipole."
        )

    elif service_id == "IPS":
        activity_id = str(raw_item.get("activityID") or f"IPS-{raw_item.get('eventTime', fetched_at)}")
        start_time = str(raw_item.get("eventTime") or fetched_at)
        loc = str(raw_item.get("location") or "Unspecified")
        metrics["location"] = loc
        metrics["catalog"] = raw_item.get("catalog") or "ALL"
        severity = "WARNING"
        title = f"Interplanetary Shock · {loc}"
        summary = f"Heliospheric shock passage detected at {loc} ({raw_item.get('catalog') or 'SWRC catalog'}) at {start_time}."

    elif service_id == "FLR":
        activity_id = str(raw_item.get("flrID") or f"FLR-{raw_item.get('beginTime', fetched_at)}")
        start_time = str(raw_item.get("peakTime") or raw_item.get("beginTime") or fetched_at)
        class_type = str(raw_item.get("classType") or "Unknown")
        metrics["class_type"] = class_type
        if raw_item.get("sourceLocation"):
            metrics["source_location"] = raw_item["sourceLocation"]
        severity = _pick_flare_severity(class_type)
        title = f"Solar Flare · Class {class_type}"
        summary = (
            f"Class {class_type} solar flare peak at {start_time}"
            + (f" from active region {raw_item.get('activeRegionNum')} ({raw_item.get('sourceLocation')})." if raw_item.get("sourceLocation") else ".")
        )

    elif service_id == "SEP":
        activity_id = str(raw_item.get("sepID") or f"SEP-{raw_item.get('eventTime', fetched_at)}")
        start_time = str(raw_item.get("eventTime") or fetched_at)
        severity = "CRITICAL"
        instruments = [i.get("displayName") for i in (raw_item.get("instruments") or []) if isinstance(i, dict) and i.get("displayName")]
        metrics["instruments"] = instruments
        title = f"Solar Energetic Particle Event · {activity_id}"
        summary = (
            f"Elevated solar energetic proton/particle flux reported at {start_time}"
            + (f" via {', '.join(instruments[:3])}." if instruments else ".")
            + " Verify onboard EVARM / Radi-N2 / CANS dosimetry before EVA egress."
        )

    elif service_id == "MPC":
        activity_id = str(raw_item.get("mpcID") or f"MPC-{raw_item.get('eventTime', fetched_at)}")
        start_time = str(raw_item.get("eventTime") or fetched_at)
        severity = "WARNING"
        title = f"Magnetopause Crossing · {activity_id}"
        summary = f"Earth magnetopause compressed inside geosynchronous orbit at {start_time} (Earth orbital regime)."

    elif service_id == "RBE":
        activity_id = str(raw_item.get("rbeID") or f"RBE-{raw_item.get('eventTime', fetched_at)}")
        start_time = str(raw_item.get("eventTime") or fetched_at)
        severity = "WARNING"
        title = f"Radiation Belt Enhancement · {activity_id}"
        summary = f"Earth outer Van Allen radiation belt electron flux enhancement at {start_time} (Earth orbital regime)."

    elif service_id == "HSS":
        activity_id = str(raw_item.get("hssID") or f"HSS-{raw_item.get('eventTime', fetched_at)}")
        start_time = str(raw_item.get("eventTime") or fetched_at)
        title = f"High Speed Solar Wind Stream · {activity_id}"
        summary = f"Fast coronal-hole solar wind stream onset recorded at {start_time}."

    elif service_id == "WSAEnlilSimulations":
        activity_id = str(raw_item.get("simulationID") or f"ENLIL-{raw_item.get('modelCompletionTime', fetched_at)}")
        start_time = str(raw_item.get("modelCompletionTime") or fetched_at)
        impacts = raw_item.get("impactList") or []
        impact_locs = [str(imp.get("location")) for imp in impacts if isinstance(imp, dict) and imp.get("location")]
        shock_eta = raw_item.get("estimatedShockArrivalTime")
        metrics["impact_locations"] = impact_locs
        if shock_eta:
            metrics["estimated_shock_arrival_time"] = shock_eta
        if any("mars" in loc.lower() or "earth" in loc.lower() for loc in impact_locs) or shock_eta:
            severity = "WARNING"
        if any("mars" in loc.lower() for loc in impact_locs):
            severity = "CRITICAL"
        impact_desc = ", ".join(impact_locs) if impact_locs else ("Earth hit/glancing blow modeled" if raw_item.get("isEarthGB") else "no planetary impact listed")
        title = f"WSA+Enlil Simulation · {impact_desc}"
        summary = (
            f"Heliospheric MHD run completed {start_time}; "
            + (f"estimated shock arrival {shock_eta}; " if shock_eta else "")
            + f"modeled targets: {impact_desc}."
        )

    else:  # notifications
        activity_id = str(raw_item.get("messageID") or f"NOTIF-{raw_item.get('messageIssueTime', fetched_at)}")
        start_time = str(raw_item.get("messageIssueTime") or fetched_at)
        msg_type = str(raw_item.get("messageType") or "Summary")
        metrics["message_type"] = msg_type
        if msg_type.upper() in {"SEP", "FLR", "CME"}:
            severity = "WARNING"
        if msg_type.upper() == "SEP":
            severity = "CRITICAL"
        body = str(raw_item.get("messageBody") or "").replace("\r", " ").replace("\n", " ")
        title = f"SWRC Notification [{msg_type}] · {activity_id}"
        summary = re.sub(r"\s+", " ", body).strip()[:320] or f"Space Weather Research Center {msg_type} bulletin."

    return {
        "event_uid": f"{service_id}:{activity_id}",
        "service_type": service_id,
        "activity_id": activity_id,
        "start_time": start_time,
        "severity": severity,
        "regime_scope": regime_scope,
        "title": title,
        "summary": summary,
        "linked_ids": linked_ids,
        "source_url": source_url,
        "metrics": metrics,
        "raw_payload": raw_item,
        "data_provenance": "LIVE_NASA_DONKI",
        "fetched_at": fetched_at,
    }


def _http_get_json(url: str, timeout_sec: float = 10.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TARS-Care-Space-Weather-Client/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw_bytes = resp.read()
        if not raw_bytes:
            return []
        text = raw_bytes.decode("utf-8", errors="replace").strip()
        if not text:
            return []
        return json.loads(text)


def sync_donki_services(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    services: Optional[List[str]] = None,
    most_accurate_only: bool = True,
    cme_speed: int = 500,
    cme_half_angle: int = 30,
    catalog: str = "ALL",
    ips_location: str = "ALL",
    notification_type: str = "all",
) -> Dict[str, Any]:
    """
    Synchronize selected or all 11 NASA DONKI endpoints into local SQLite storage.
    Enforces TARS Care OFFLINE blackout discipline: refuses external HTTP requests
    during OFFLINE mode while leaving cached SQLite records untouched.
    """
    default_start, default_end = _default_date_window()
    s_date = _validate_iso_date(start_date or "", default_start)
    e_date = _validate_iso_date(end_date or "", default_end)
    if s_date > e_date:
        s_date, e_date = e_date, s_date

    requested_services = [s for s in (services or ALL_DONKI_SERVICE_IDS) if s in DONKI_SERVICE_MAP]
    if not requested_services:
        requested_services = list(ALL_DONKI_SERVICE_IDS)

    comm_state = database.fetch_system_state("comm_state") or {}
    comm_norm = normalize_comm_mode(comm_state)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if comm_norm["mode"] == "OFFLINE":
        prev_meta = database.fetch_donki_sync_meta()
        blocked_meta = {
            "last_sync_at": prev_meta.get("last_sync_at", ""),
            "last_sync_status": "BLOCKED_OFFLINE",
            "last_sync_message": (
                "Earth link is in OFFLINE blackout — external NASA DONKI polling paused. "
                "Displaying locally cached SQLite space-weather events."
            ),
            "last_window": {"start_date": s_date, "end_date": e_date},
            "service_statuses": prev_meta.get("service_statuses", {}),
        }
        database.update_donki_sync_meta(blocked_meta)
        return {
            "status": "BLOCKED_OFFLINE",
            "message": blocked_meta["last_sync_message"],
            "fetched_count": 0,
            "services_checked": 0,
            "errors": [],
            "sync_meta": blocked_meta,
        }

    api_key, _ = resolve_nasa_api_key()
    prev_meta = database.fetch_donki_sync_meta()
    service_statuses: Dict[str, Any] = dict(prev_meta.get("service_statuses") or {})
    normalized_batch: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    ok_services = 0

    def _fetch_one(sid: str) -> Tuple[str, str, List[Dict[str, Any]], Optional[str], str]:
        full_url, redacted_url = build_donki_request(
            service_id=sid,
            start_date=s_date,
            end_date=e_date,
            api_key=api_key,
            most_accurate_only=most_accurate_only,
            cme_speed=cme_speed,
            cme_half_angle=cme_half_angle,
            catalog=catalog,
            ips_location=ips_location,
            notification_type=notification_type,
        )
        try:
            payload = _http_get_json(full_url)
            items = payload if isinstance(payload, list) else ([payload] if isinstance(payload, dict) and payload else [])
            converted = [
                _normalize_donki_item(sid, row, now_iso)
                for row in items
                if isinstance(row, dict)
            ]
            return sid, "OK", converted, None, redacted_url
        except urllib.error.HTTPError as exc:
            err_msg = (
                "NASA API rate limit reached (HTTP 429)"
                if exc.code == 429
                else ("NASA API key rejected (HTTP 403)" if exc.code == 403 else f"HTTP {exc.code}: {exc.reason}")
            )
            st = "RATE_LIMITED" if exc.code == 429 else "ERROR"
            return sid, st, [], err_msg, redacted_url
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return sid, "ERROR", [], f"Network/parse error: {type(exc).__name__}", redacted_url

    worker_count = max(1, min(8, len(requested_services)))
    results_by_sid: Dict[str, Tuple[str, str, List[Dict[str, Any]], Optional[str], str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_map = {pool.submit(_fetch_one, sid): sid for sid in requested_services}
        for fut in concurrent.futures.as_completed(future_map):
            res = fut.result()
            results_by_sid[res[0]] = res

    for sid in requested_services:
        _, st, converted, err_msg, redacted_url = results_by_sid[sid]
        if st == "OK":
            normalized_batch.extend(converted)
            service_statuses[sid] = {
                "status": "OK",
                "count": len(converted),
                "endpoint": redacted_url,
                "synced_at": now_iso,
                "error": "",
            }
            ok_services += 1
        else:
            errors.append({"service": sid, "error": err_msg or "Request failed"})
            service_statuses[sid] = {
                "status": st,
                "count": service_statuses.get(sid, {}).get("count", 0),
                "endpoint": redacted_url,
                "synced_at": now_iso,
                "error": err_msg or "Request failed",
            }

    saved_count = database.upsert_donki_events(normalized_batch)
    if ok_services == len(requested_services):
        overall_sync_status = "SYNCED"
        sync_msg = f"Synced {saved_count} live NASA DONKI events across all {ok_services} requested feeds ({s_date} to {e_date})."
    elif ok_services > 0:
        overall_sync_status = "PARTIAL"
        sync_msg = f"Synced {saved_count} DONKI events from {ok_services}/{len(requested_services)} feeds; {len(errors)} feed(s) returned errors while local cache remains intact."
    else:
        overall_sync_status = "ERROR"
        sync_msg = f"NASA DONKI sync failed on {len(errors)} feed(s) ({errors[0]['error'] if errors else 'unavailable'}); cached offline events preserved."

    new_meta = {
        "last_sync_at": now_iso,
        "last_sync_status": overall_sync_status,
        "last_sync_message": sync_msg,
        "last_window": {"start_date": s_date, "end_date": e_date},
        "service_statuses": service_statuses,
    }
    database.update_donki_sync_meta(new_meta)

    return {
        "status": overall_sync_status,
        "message": sync_msg,
        "fetched_count": saved_count,
        "services_checked": len(requested_services),
        "services_succeeded": ok_services,
        "errors": errors,
        "sync_meta": new_meta,
    }


def build_donki_eva_advisory(events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Summarize cached DONKI space-weather events for EVA Readiness & Radiation situational awareness.
    Strictly informational / advisory — never mutates personal onboard dosimeter readings.
    """
    cached = events if events is not None else database.fetch_donki_events(limit=120)
    sep_events = [e for e in cached if e.get("service_type") == "SEP"]
    critical_flares = [e for e in cached if e.get("service_type") == "FLR" and e.get("severity") == "CRITICAL"]
    fast_cmes = [
        e for e in cached
        if e.get("service_type") in {"CME", "CMEAnalysis"}
        and float((e.get("metrics") or {}).get("speed_km_s") or 0) >= 1000
    ]
    mars_or_target_enlil = [
        e for e in cached
        if e.get("service_type") == "WSAEnlilSimulations"
        and e.get("severity") in {"WARNING", "CRITICAL"}
    ]
    earth_mag_count = sum(1 for e in cached if e.get("regime_scope") == "EARTH_MAGNETOSPHERE")

    advisories: List[str] = []
    if sep_events:
        top = sep_events[0]
        advisories.append(
            f"NASA DONKI SEP Cache ({top['activity_id']}): verify live onboard EVARM / Radi-N2 / CANS proton & neutron dosimetry prior to EVA egress."
        )
    if critical_flares:
        top_flr = critical_flares[0]
        ct = (top_flr.get("metrics") or {}).get("class_type", "X/M5+")
        advisories.append(
            f"NASA DONKI Intense Flare Cache (Class {ct}): expect HF/ground-link disruption & elevated solar storm watch."
        )
    if mars_or_target_enlil or fast_cmes:
        ref = mars_or_target_enlil[0] if mars_or_target_enlil else fast_cmes[0]
        advisories.append(
            f"NASA DONKI CME / WSA-Enlil Cache ({ref['title']}): track shock arrival window against onboard habitat dosimeters."
        )

    return {
        "total_cached_events": len(cached),
        "sep_count": len(sep_events),
        "critical_flare_count": len(critical_flares),
        "fast_cme_count": len(fast_cmes),
        "enlil_alert_count": len(mars_or_target_enlil),
        "earth_magnetosphere_count": earth_mag_count,
        "advisories": advisories,
        "has_heliospheric_watch": bool(advisories),
    }


def build_donki_public_state(limit: int = 250, include_raw: bool = False) -> Dict[str, Any]:
    """Assemble safe, secret-free NASA DONKI dashboard state for UI and /api/donki/state."""
    events = database.fetch_donki_events(limit=limit)
    if not include_raw:
        events = [{k: v for k, v in ev.items() if k != "raw_payload"} for ev in events]
    counts = database.fetch_donki_service_counts()
    sync_meta = database.fetch_donki_sync_meta()
    config = get_donki_config_summary()
    advisory_summary = build_donki_eva_advisory(events)
    advisory_summary["total_cached_events"] = sum(counts.values())
    return {
        "config": config,
        "services": DONKI_SERVICE_CATALOG,
        "sync_meta": sync_meta,
        "service_counts": counts,
        "advisory_summary": advisory_summary,
        "events": events,
    }


def should_auto_sync(max_age_hours: float = 6.0) -> bool:
    """Return True when Earth link is not OFFLINE and cached 30-day DONKI data is empty/stale."""
    comm_state = database.fetch_system_state("comm_state") or {}
    if normalize_comm_mode(comm_state)["mode"] == "OFFLINE":
        return False
    meta = database.fetch_donki_sync_meta()
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


def trigger_background_auto_sync(max_age_hours: float = 6.0) -> bool:
    """Kick off a non-blocking 30-day concurrent DONKI sync in a daemon thread when eligible."""
    global _AUTO_SYNC_RUNNING
    if not should_auto_sync(max_age_hours=max_age_hours):
        return False
    with _AUTO_SYNC_LOCK:
        if _AUTO_SYNC_RUNNING:
            return False
        _AUTO_SYNC_RUNNING = True

    def _runner() -> None:
        global _AUTO_SYNC_RUNNING
        try:
            sync_donki_services()
        except Exception:
            pass
        finally:
            with _AUTO_SYNC_LOCK:
                _AUTO_SYNC_RUNNING = False

    threading.Thread(target=_runner, daemon=True, name="tars-donki-autosync").start()
    return True
