"""
FastAPI Router for NASA InSight Mars Weather Service API Integration.
Caches Elysium Planitia per-Sol surface weather telemetry locally in SQLite and
enforces TARS Care OFFLINE blackout discipline without mutating habitat ECLSS data.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Query

from insight_client import build_insight_public_state, sync_insight_weather
from models import InsightSyncRequest

insight_router = APIRouter(prefix="/api/insight", tags=["insight"])
_build_full_state_fn: Optional[Callable[[], Dict[str, Any]]] = None


def register_insight_state_builder(builder: Callable[[], Dict[str, Any]]) -> None:
    global _build_full_state_fn
    _build_full_state_fn = builder


def _safe_full_state() -> Dict[str, Any]:
    if _build_full_state_fn is not None:
        return _build_full_state_fn()
    return {"insight_state": build_insight_public_state()}


@insight_router.get("/state")
def get_insight_state(limit: int = Query(default=14, ge=1, le=60)) -> Dict[str, Any]:
    return build_insight_public_state(limit=limit)


@insight_router.post("/sync")
def trigger_insight_sync(payload: InsightSyncRequest) -> Dict[str, Any]:
    sync_result = sync_insight_weather(feedtype=payload.feedtype, version=payload.version)
    full_state = _safe_full_state()
    return {
        "sync_result": sync_result,
        "insight_state": full_state.get("insight_state") or build_insight_public_state(),
        "state": full_state,
    }
