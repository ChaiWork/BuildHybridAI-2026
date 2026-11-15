"""
FastAPI Router for NASA DONKI Space Weather Integration.
Provides offline-cached space weather inspection, live synchronization across all
11 official NASA DONKI endpoints (when Earth link is CONNECTED or DELAYED),
and secret-safe backend API key configuration.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

import database
from donki_client import (
    DONKI_SERVICE_MAP,
    build_donki_public_state,
    get_donki_config_summary,
    sync_donki_services,
)
from models import DonkiConfigInput, DonkiSyncRequest

donki_router = APIRouter(prefix="/api/donki", tags=["donki"])
_build_full_state_fn: Optional[Callable[[], Dict[str, Any]]] = None


def register_donki_state_builder(builder: Callable[[], Dict[str, Any]]) -> None:
    global _build_full_state_fn
    _build_full_state_fn = builder


def _safe_full_state() -> Dict[str, Any]:
    if _build_full_state_fn is not None:
        return _build_full_state_fn()
    return {"donki_state": build_donki_public_state()}


@donki_router.get("/state")
def get_donki_state(
    service_type: Optional[str] = Query(default=None),
    limit: int = Query(default=80, ge=1, le=250),
    include_raw: bool = Query(default=False),
) -> Dict[str, Any]:
    state = build_donki_public_state(limit=limit, include_raw=include_raw)
    if service_type and service_type != "ALL":
        if service_type not in DONKI_SERVICE_MAP:
            raise HTTPException(status_code=400, detail=f"Unknown DONKI service_type '{service_type}'")
        filtered = database.fetch_donki_events(service_type=service_type, limit=limit)
        if not include_raw:
            filtered = [{k: v for k, v in ev.items() if k != "raw_payload"} for ev in filtered]
        state["events"] = filtered
    return state


@donki_router.post("/sync")
def trigger_donki_sync(payload: DonkiSyncRequest) -> Dict[str, Any]:
    if payload.services:
        invalid = [s for s in payload.services if s not in DONKI_SERVICE_MAP]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unsupported DONKI service(s): {', '.join(invalid)}")

    sync_result = sync_donki_services(
        start_date=payload.start_date,
        end_date=payload.end_date,
        services=payload.services,
        most_accurate_only=payload.most_accurate_only,
        cme_speed=payload.cme_speed,
        cme_half_angle=payload.cme_half_angle,
        catalog=payload.catalog,
        ips_location=payload.ips_location,
        notification_type=payload.notification_type,
    )
    full_state = _safe_full_state()
    return {
        "sync_result": sync_result,
        "donki_state": full_state.get("donki_state") or build_donki_public_state(),
        "state": full_state,
    }


@donki_router.post("/config")
def update_donki_config(payload: DonkiConfigInput) -> Dict[str, Any]:
    existing = database.fetch_donki_secret_config()
    if payload.clear_api_key:
        existing["api_key"] = ""
    elif payload.api_key is not None:
        cleaned = payload.api_key.strip()
        if len(cleaned) < 8:
            raise HTTPException(status_code=400, detail="NASA_API_KEY must be at least 8 characters.")
        existing["api_key"] = cleaned

    if payload.auto_advisory_in_eva is not None:
        existing["auto_advisory_in_eva"] = bool(payload.auto_advisory_in_eva)

    database.update_donki_secret_config(existing)
    full_state = _safe_full_state()
    return {
        "config": get_donki_config_summary(),
        "donki_state": full_state.get("donki_state") or build_donki_public_state(),
        "state": full_state,
    }
