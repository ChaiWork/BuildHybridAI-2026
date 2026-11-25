"""
FastAPI Router for Integrated Astronaut Support Modules:
1. Food & Life-Support Supplies Management (/api/food/*)
2. Distance from Earth & Mission Communication Centre (/api/comm/*)
3. Isolation Support — Personal Journal, Mood Check-Ins & AI Companion (/api/journal/*, /api/companion/*)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from support_modules import (
    add_food_item,
    build_comm_centre_state,
    build_companion_and_journal_state,
    build_food_and_supplies_state,
    calculate_supply_projection,
    configure_comm_simulator,
    create_journal_entry,
    create_or_queue_comm_message,
    delete_comm_message,
    delete_journal_entry,
    fetch_comm_messages,
    fetch_journal_entries,
    record_food_consumption,
    record_food_resupply,
    record_mood_checkin,
    remove_food_item,
    retry_or_send_comm_message,
    send_companion_message,
    trigger_companion_safety_escalation,
    update_comm_message,
    update_crew_nutrition_target,
    update_food_item,
    update_food_mission_config,
    update_journal_entry,
    update_privacy_settings,
)

support_router = APIRouter(prefix="/api", tags=["support_modules"])

_STATE_BUILDER: Optional[Callable[[], Dict[str, Any]]] = None


def register_support_state_builder(builder: Callable[[], Dict[str, Any]]) -> None:
    global _STATE_BUILDER
    _STATE_BUILDER = builder


def _full_state_or_none() -> Optional[Dict[str, Any]]:
    return _STATE_BUILDER() if _STATE_BUILDER else None


# =============================================================================
# PYDANTIC SCHEMAS — PART 1: FOOD & LIFE-SUPPORT SUPPLIES
# =============================================================================

class FoodItemCreateInput(BaseModel):
    name: str
    category: str = "Freeze-dried meals"
    quantity: float = Field(ge=0.0, default=20.0)
    initial_quantity: Optional[float] = None
    serving_size: str = "1 portion"
    unit: str = "portions"
    calories_per_serving: float = Field(ge=0.0, default=450.0)
    protein_g: float = Field(ge=0.0, default=24.0)
    carbs_g: float = Field(ge=0.0, default=55.0)
    fat_g: float = Field(ge=0.0, default=14.0)
    water_ml_per_serving: float = Field(ge=0.0, default=0.0)
    micronutrients: Dict[str, float] = Field(default_factory=dict)
    nutrition_complete: bool = True
    storage_requirements: str = "Ambient Dry Galley Rack (18–24°C)"
    bay_location: str = "Galley G1"
    expiry_sol: Optional[int] = None
    expiry_date: Optional[str] = None
    shelf_life_days: int = 365
    food_source: str = "User-Entered Mission Inventory"
    min_threshold: float = 15.0
    critical_threshold: float = 5.0
    daily_ration_per_astronaut: float = 0.5
    notes: str = ""
    authorised_by: str = "Crew Member"


class FoodItemUpdateInput(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    quantity_delta: Optional[float] = None
    serving_size: Optional[str] = None
    unit: Optional[str] = None
    calories_per_serving: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    water_ml_per_serving: Optional[float] = None
    micronutrients: Optional[Dict[str, float]] = None
    nutrition_complete: Optional[bool] = None
    storage_requirements: Optional[str] = None
    bay_location: Optional[str] = None
    expiry_sol: Optional[int] = None
    expiry_date: Optional[str] = None
    min_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    daily_ration_per_astronaut: Optional[float] = None
    notes: Optional[str] = None


class FoodConsumptionInput(BaseModel):
    food_item_uid: str
    quantity_consumed: float = Field(gt=0.0, default=1.0)
    meal_type: str = "Lunch"
    mission_day: Optional[int] = None
    extra_water_ml: float = Field(ge=0.0, default=0.0)
    notes: str = ""


class FoodResupplyInput(BaseModel):
    food_item_uid: str
    quantity_added: float = Field(gt=0.0)
    event_type: str = "RESUPPLY_DELIVERY"
    mission_day: Optional[int] = None
    source: str = "Cargo Module Transfer / Veggie Harvest"
    authorised_by: str = "Mission Commander"
    notes: str = ""


class NutritionTargetsUpdateInput(BaseModel):
    crew_id: Optional[str] = None
    calories_target_kcal: Optional[float] = None
    protein_target_g: Optional[float] = None
    carbs_target_g: Optional[float] = None
    fat_target_g: Optional[float] = None
    water_target_ml: Optional[float] = None
    vitamin_d_target_iu: Optional[float] = None
    calcium_target_mg: Optional[float] = None
    notes: Optional[str] = None


class FoodMissionConfigUpdateInput(BaseModel):
    crew_count: Optional[int] = Field(default=None, ge=1, le=20)
    planned_mission_end_sol: Optional[int] = None
    next_resupply_sol: Optional[int] = None
    next_resupply_label: Optional[str] = None
    portions_per_astronaut_per_day: Optional[float] = Field(default=None, gt=0.1)
    water_liters_per_astronaut_per_day: Optional[float] = Field(default=None, gt=0.1)
    water_warning_threshold_liters: Optional[float] = Field(default=None, ge=10.0)


class SupplyProjectionCalcInput(BaseModel):
    total_portions: float = Field(ge=0.0, default=120.0)
    astronaut_count: int = Field(ge=1, default=2)
    portions_per_astronaut_per_day: float = Field(gt=0.0, default=3.0)
    current_sol: int = 184
    planned_mission_end_sol: int = 260
    next_resupply_sol: Optional[int] = 240


# =============================================================================
# PYDANTIC SCHEMAS — PART 2: DISTANCE FROM EARTH & COMM MESSAGE CENTRE
# =============================================================================

class CommSimulatorUpdateInput(BaseModel):
    scenario_id: Optional[str] = None
    comm_condition: Optional[str] = None
    one_way_delay_minutes: Optional[float] = Field(default=None, ge=0.0, le=60.0)
    distance_million_km: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    mission_location: Optional[str] = None
    mission_destination: Optional[str] = None
    next_comm_window_utc: Optional[str] = None
    relay_satellite: Optional[str] = None


class CommMessageCreateInput(BaseModel):
    subject: str
    body: str
    recipient: str = "Earth Mission Control & Flight Surgeons (MCC-Houston)"
    message_type: str = "MISSION_CONTROL_MESSAGE"
    priority: str = "NORMAL"
    save_as_draft: bool = False
    transmit_immediately: bool = False
    simulate_failure: bool = False


class CommMessageUpdateInput(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    recipient: Optional[str] = None
    message_type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class CommMessageRetryInput(BaseModel):
    simulate_failure: bool = False


# =============================================================================
# PYDANTIC SCHEMAS — PART 3: PERSONAL JOURNAL, MOOD & AI COMPANION
# =============================================================================

class JournalEntryCreateInput(BaseModel):
    title: str
    content: str
    mission_day: Optional[int] = None
    mood: str = ""
    feelings: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    guided_prompt: str = ""
    is_private: bool = True
    allow_ai_access: bool = False


class JournalEntryUpdateInput(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    mood: Optional[str] = None
    feelings: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    guided_prompt: Optional[str] = None
    allow_ai_access: Optional[bool] = None


class MoodCheckInInput(BaseModel):
    mood: str
    feelings: List[str] = Field(default_factory=list)
    note: str = ""
    mission_day: Optional[int] = None


class PrivacySettingsUpdateInput(BaseModel):
    allow_ai_journal_context: Optional[bool] = None
    allow_ai_mood_context: Optional[bool] = None
    allow_ai_mission_telemetry_context: Optional[bool] = None
    store_companion_history: Optional[bool] = None
    preferred_topics: Optional[List[str]] = None
    escalation_contact_role: Optional[str] = None
    escalation_procedure_note: Optional[str] = None


class CompanionChatInput(BaseModel):
    message: str
    conversation_uid: Optional[str] = None
    mode: str = "COMPANION_CHAT"
    client_on_device_reply: Optional[str] = None
    client_engine_used: Optional[str] = None


class CompanionEscalationInput(BaseModel):
    summary_note: str = "Astronaut requested immediate onboard CMO / psychological safety support."
    queue_urgent_report: bool = True


# =============================================================================
# ENDPOINTS — PART 1: FOOD & LIFE-SUPPORT SUPPLIES
# =============================================================================

@support_router.get("/food/state")
def api_get_food_state() -> Dict[str, Any]:
    return build_food_and_supplies_state()


@support_router.post("/food/items")
def api_add_food_item(payload: FoodItemCreateInput) -> Dict[str, Any]:
    item = add_food_item(payload.model_dump())
    return {
        "item": item,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.put("/food/items/{item_uid}")
def api_update_food_item(item_uid: str, payload: FoodItemUpdateInput) -> Dict[str, Any]:
    try:
        updated = update_food_item(item_uid, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "item": updated,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.delete("/food/items/{item_uid}")
def api_remove_food_item(
    item_uid: str,
    reason: str = Query(default="Removed expired or unavailable item from galley inventory"),
) -> Dict[str, Any]:
    try:
        removed = remove_food_item(item_uid, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "removed": removed,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/food/consume")
def api_record_food_consumption(payload: FoodConsumptionInput) -> Dict[str, Any]:
    try:
        record = record_food_consumption(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "consumption": record,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/food/resupply")
def api_record_food_resupply(payload: FoodResupplyInput) -> Dict[str, Any]:
    try:
        resupply = record_food_resupply(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "resupply": resupply,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/food/targets")
def api_update_nutrition_targets(payload: NutritionTargetsUpdateInput) -> Dict[str, Any]:
    updated = update_crew_nutrition_target(payload.crew_id, payload.model_dump(exclude_none=True))
    return {
        "targets": updated,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/food/config")
def api_update_food_config(payload: FoodMissionConfigUpdateInput) -> Dict[str, Any]:
    cfg = update_food_mission_config(payload.model_dump(exclude_none=True))
    return {
        "mission_config": cfg,
        "food_state": build_food_and_supplies_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/food/estimate")
def api_calculate_supply_projection(payload: SupplyProjectionCalcInput) -> Dict[str, Any]:
    return calculate_supply_projection(
        total_portions=payload.total_portions,
        astronaut_count=payload.astronaut_count,
        portions_per_astronaut_per_day=payload.portions_per_astronaut_per_day,
        current_sol=payload.current_sol,
        planned_mission_end_sol=payload.planned_mission_end_sol,
        next_resupply_sol=payload.next_resupply_sol,
    )


# =============================================================================
# ENDPOINTS — PART 2: DISTANCE FROM EARTH & MISSION COMMUNICATION CENTRE
# =============================================================================

@support_router.get("/comm/overview")
def api_get_comm_overview() -> Dict[str, Any]:
    return build_comm_centre_state()


@support_router.post("/comm/simulator")
def api_configure_comm_simulator(payload: CommSimulatorUpdateInput) -> Dict[str, Any]:
    configure_comm_simulator(payload.model_dump(exclude_none=True))
    return {
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


@support_router.get("/comm/messages")
def api_list_comm_messages() -> Dict[str, Any]:
    return {"messages": fetch_comm_messages()}


@support_router.post("/comm/messages")
def api_create_comm_message(payload: CommMessageCreateInput) -> Dict[str, Any]:
    msg = create_or_queue_comm_message(payload.model_dump())
    return {
        "message": msg,
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


@support_router.put("/comm/messages/{message_uid}")
def api_update_comm_message(message_uid: str, payload: CommMessageUpdateInput) -> Dict[str, Any]:
    try:
        updated = update_comm_message(message_uid, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "message": updated,
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


@support_router.delete("/comm/messages/{message_uid}")
def api_delete_comm_message(message_uid: str) -> Dict[str, Any]:
    try:
        deleted = delete_comm_message(message_uid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "deleted": deleted,
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/comm/messages/{message_uid}/send")
def api_send_comm_message(message_uid: str, payload: Optional[CommMessageRetryInput] = None) -> Dict[str, Any]:
    try:
        sim_fail = bool(payload.simulate_failure) if payload else False
        sent = retry_or_send_comm_message(message_uid, simulate_failure=sim_fail)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "message": sent,
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/comm/messages/{message_uid}/retry")
def api_retry_comm_message(message_uid: str, payload: Optional[CommMessageRetryInput] = None) -> Dict[str, Any]:
    try:
        sim_fail = bool(payload.simulate_failure) if payload else False
        retried = retry_or_send_comm_message(message_uid, simulate_failure=sim_fail)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "message": retried,
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }


# =============================================================================
# ENDPOINTS — PART 3: PERSONAL JOURNAL, MOOD & AI COMPANION
# =============================================================================

@support_router.get("/companion/state")
def api_get_companion_state() -> Dict[str, Any]:
    return build_companion_and_journal_state()


@support_router.get("/journal/entries")
def api_list_journal_entries(
    search: Optional[str] = Query(default=None),
    mood: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    mission_day: Optional[int] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    entries = fetch_journal_entries(
        search_query=search,
        mood_filter=mood,
        tag_filter=tag,
        mission_day=mission_day,
        date_from=date_from,
        date_to=date_to,
    )
    return {"entries": entries}


@support_router.post("/journal/entries")
def api_create_journal_entry(payload: JournalEntryCreateInput) -> Dict[str, Any]:
    try:
        entry = create_journal_entry(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "entry": entry,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.put("/journal/entries/{entry_uid}")
def api_update_journal_entry(entry_uid: str, payload: JournalEntryUpdateInput) -> Dict[str, Any]:
    try:
        entry = update_journal_entry(entry_uid, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "entry": entry,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.delete("/journal/entries/{entry_uid}")
def api_delete_journal_entry(entry_uid: str) -> Dict[str, Any]:
    try:
        deleted = delete_journal_entry(entry_uid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "deleted": deleted,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/companion/mood-checkin")
def api_record_mood_checkin(payload: MoodCheckInInput) -> Dict[str, Any]:
    try:
        checkin = record_mood_checkin(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "checkin": checkin,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/companion/privacy")
def api_update_privacy_settings(payload: PrivacySettingsUpdateInput) -> Dict[str, Any]:
    updated = update_privacy_settings(None, payload.model_dump(exclude_none=True))
    return {
        "privacy_settings": updated,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/companion/chat")
def api_send_companion_chat(payload: CompanionChatInput) -> Dict[str, Any]:
    try:
        res = send_companion_message(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **res,
        "companion_state": build_companion_and_journal_state(),
        "state": _full_state_or_none(),
    }


@support_router.post("/companion/escalate-support")
def api_escalate_companion_support(payload: CompanionEscalationInput) -> Dict[str, Any]:
    res = trigger_companion_safety_escalation(payload.model_dump())
    return {
        **res,
        "companion_state": build_companion_and_journal_state(),
        "comm_centre_state": build_comm_centre_state(),
        "state": _full_state_or_none(),
    }
