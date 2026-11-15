"""
FastAPI Backend for TARS Care AI – Autonomous Astronaut Health Monitoring and Decision Support System.
Local-first architecture with SQLite persistence, Integrated 5-Hazard Assessment Engine,
Store-and-Forward Earth Telemetry Queue, and Local NASA/CSA RAG Retrieval Engine.
"""

from __future__ import annotations
import os
import sys
import threading
from contextlib import asynccontextmanager

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
from models import (
    AstronautBaseline,
    BaselineUpdateInput,
    RadiationConfigLimits,
    EnvironmentalConfigLimits,
    HealthMeasurementSubmission,
    PsychQuestionnaireInput,
    CommStatusUpdate,
    StoreForwardReportCreate,
    EmergencyEscalationInput,
    RAGQueryInput,
    SansAssessmentInput,
    MedKitAdjustInput,
    FlightSurgeonConsultInput,
    CrewSelectInput,
    CrewPinVerifyInput,
    CrewPinUpdateInput,
    DataProvenance,
    MissionPhase,
    RiskLevel,
)
from dataclasses import asdict
from hardware_devices import HARDWARE_CATALOG
from hardware_routes import (
    _normalize_device_states_for_crew,
    hardware_router,
    register_state_builder,
)
from donki_client import build_donki_public_state, trigger_background_auto_sync
from donki_routes import donki_router, register_donki_state_builder
from insight_client import build_insight_public_state, trigger_background_insight_auto_sync
from insight_routes import insight_router, register_insight_state_builder
from support_modules import (
    build_comm_centre_state,
    build_companion_and_journal_state,
    build_food_and_supplies_state,
    synchronize_all_communications,
)
from support_routes import register_support_state_builder, support_router
from database import (
    init_db,
    get_active_crew_id,
    set_active_crew_id,
    fetch_crew_baseline,
    fetch_crew_baseline_history,
    save_crew_baseline,
    fetch_all_telemetry,
    fetch_device_measurements,
    fetch_hardware_examinations,
    fetch_biosample_records,
    fetch_system_state,
    update_system_state,
    insert_telemetry_record,
    fetch_store_forward_reports,
    create_store_forward_report,
    synchronize_queued_reports,
    fetch_psych_questionnaires,
    insert_psych_questionnaire,
    fetch_sans_assessments,
    insert_sans_assessment,
    fetch_medical_kit_items,
    adjust_medical_kit_item,
)
from assessment_engine import evaluate_integrated_health, generate_local_emergency_protocol
from marscare_enhancer import normalize_comm_mode
from knowledge_base import rag_engine, KNOWLEDGE_CORPUS
from mission_ops import (
    CREW_ORDER,
    build_flight_surgeon_consult_packet,
    hash_privacy_pin,
    verify_privacy_pin,
)
from dataclasses import asdict


_DB_INIT_LOCK = threading.Lock()
_VERIFIED_DB_PATHS: set[str] = set()


def _ensure_db_initialized() -> None:
    current_path = database.DB_PATH
    if current_path in _VERIFIED_DB_PATHS and os.path.exists(current_path) and os.path.getsize(current_path) > 0:
        return
    with _DB_INIT_LOCK:
        current_path = database.DB_PATH
        if current_path in _VERIFIED_DB_PATHS and os.path.exists(current_path) and os.path.getsize(current_path) > 0:
            return
        init_db()
        _VERIFIED_DB_PATHS.add(current_path)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_db_initialized()
    if not os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("VERCEL"):
        trigger_background_auto_sync(max_age_hours=6.0)
        trigger_background_insight_auto_sync(max_age_hours=12.0)
    yield


app = FastAPI(
    title="TARS Care AI Backend API",
    description="Autonomous Astronaut Health Monitoring and Decision Support System (NASA Space Apps Challenge 2026)",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def ensure_serverless_db_ready(request, call_next):
    _ensure_db_initialized()
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_crew_fleet_matrix(
    rad_limits: RadiationConfigLimits,
    env_limits: EnvironmentalConfigLimits,
    comm_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build multi-crew CMO triage summary without leaking private journal reflections."""
    baselines = fetch_system_state("crew_baselines") or {}
    crew_ids = list(dict.fromkeys(list(CREW_ORDER) + list(baselines.keys())))
    matrix: List[Dict[str, Any]] = []
    for cid in crew_ids:
        hist = fetch_all_telemetry(crew_id=cid)
        if not hist:
            continue
        latest = hist[-1]
        b_dict = fetch_crew_baseline(cid)
        b_model = AstronautBaseline(**b_dict) if b_dict else AstronautBaseline()
        psych_list = fetch_psych_questionnaires(crew_id=cid)
        sans_list = fetch_sans_assessments(crew_id=cid)
        eval_res = evaluate_integrated_health(
            latest=latest,
            history=hist,
            baseline=b_model,
            rad_limits=rad_limits,
            env_limits=env_limits,
            comm_state=comm_state,
            latest_psych=psych_list[0] if psych_list else None,
            skip_rag=True,
            latest_sans=sans_list[0] if sans_list else None,
        )
        hr = float(latest.get("heart_rate_bpm", 68.0))
        recs = eval_res.get("recommendations") or []
        top_action = recs[0]["action"] if recs else "Nominal baseline monitoring."
        flagged_hazards = [
            hz for hz, st in (eval_res.get("hazard_statuses") or {}).items() if st in ("WARNING", "CRITICAL")
        ]
        matrix.append({
            "crew_id": cid,
            "name": b_model.name,
            "role": b_model.role,
            "mission_day": latest["mission_day"],
            "overall_status": eval_res["overall_status"],
            "eva_status": (eval_res.get("eva_readiness") or {}).get("status", "GO"),
            "eva_score_pct": (eval_res.get("eva_readiness") or {}).get("score_pct", 100),
            "exercise_contraindicated": bool(eval_res.get("exercise_contraindicated", False)),
            "heart_rate_bpm": round(hr),
            "baseline_hr_bpm": round(b_model.baseline_hr_bpm),
            "hr_delta": round(hr - b_model.baseline_hr_bpm),
            "bp_summary": f"{round(float(latest['systolic_bp_mmhg']))}/{round(float(latest['diastolic_bp_mmhg']))}",
            "spo2_pct": round(float(latest["spo2_pct"]), 1),
            "cumulative_dose_msv": round(float(latest["cumulative_effective_dose_msv"]), 1),
            "sleep_duration_hrs": round(float(latest["sleep_duration_hrs"]), 1),
            "dizziness_severity": int(latest.get("dizziness_severity", 0)),
            "sans_flagged": bool(latest.get("visual_disturbance_sans") or (sans_list and (sans_list[0].get("wavy_lines_detected") or len(sans_list[0].get("scotoma_cells") or []) > 0))),
            "flagged_hazards": flagged_hazards,
            "priority_headline": top_action,
            "behavioral_checkins_count": len(psych_list),
            "private_reflections_redacted": True,
        })
    rank_map = {"CRITICAL": 0, "WARNING": 1, "NORMAL": 2}
    matrix.sort(key=lambda item: (rank_map.get(item["overall_status"], 9), item["crew_id"]))
    return matrix


def _build_full_state() -> Dict[str, Any]:
    active_crew_id = get_active_crew_id()
    history = fetch_all_telemetry(crew_id=active_crew_id)
    if not history:
        init_db()
        active_crew_id = get_active_crew_id()
        history = fetch_all_telemetry(crew_id=active_crew_id)

    latest = history[-1]
    baseline_dict = fetch_crew_baseline(active_crew_id) or {}
    baseline = AstronautBaseline(**baseline_dict) if baseline_dict else AstronautBaseline()
    baseline.mission_day = latest["mission_day"]
    baseline.current_phase = MissionPhase(latest["mission_phase"])
    baseline.gravity_g = float(latest["gravity_g"])

    rad_limits_dict = fetch_system_state("rad_limits")
    rad_limits = RadiationConfigLimits(**rad_limits_dict) if rad_limits_dict else RadiationConfigLimits()

    env_limits_dict = fetch_system_state("env_limits")
    env_limits = EnvironmentalConfigLimits(**env_limits_dict) if env_limits_dict else EnvironmentalConfigLimits()

    comm_state = fetch_system_state("comm_state") or {}
    reports = fetch_store_forward_reports()
    pending_count = sum(1 for r in reports if r["transmission_status"] != "SYNCHRONIZED_ACK")
    comm_state["pending_reports_count"] = pending_count

    psych_history = fetch_psych_questionnaires(crew_id=active_crew_id)
    latest_psych = psych_history[0] if psych_history else None
    sans_history = fetch_sans_assessments(crew_id=active_crew_id)
    latest_sans = sans_history[0] if sans_history else None

    assessment = evaluate_integrated_health(
        latest=latest,
        history=history,
        baseline=baseline,
        rad_limits=rad_limits,
        env_limits=env_limits,
        comm_state=comm_state,
        latest_psych=latest_psych,
        latest_sans=latest_sans,
    )

    pins = fetch_system_state("crew_privacy_pins") or {}
    pin_hint = (pins.get(active_crew_id) or {}).get("hint", "Default demo PIN: 2026")

    food_state = build_food_and_supplies_state(active_crew_id)
    comm_centre_state = build_comm_centre_state()
    companion_state = build_companion_and_journal_state(active_crew_id)

    comm_state["round_trip_delay_minutes"] = comm_centre_state["round_trip_delay_minutes"]
    comm_state["comm_condition"] = comm_centre_state["comm_condition"]
    comm_state["mission_location"] = comm_centre_state["mission_location"]
    comm_state["mission_destination"] = comm_centre_state["mission_destination"]
    comm_state["pending_messages_count"] = comm_centre_state["pending_messages_count"]

    assessment["food_alerts"] = food_state.get("food_alerts", [])
    assessment["nutrition_overview"] = food_state.get("nutrition_overview", {})
    assessment["five_hazard_support_integration"] = {
        "Isolation and Confinement": {
            "connected_modules": ["Personal Journal", "TARSCARE AI Companion", "Self-Reported Mood Tracker"],
            "summary": (
                f"{len(companion_state.get('journal_entries', []))} private journal entries and "
                f"{len(companion_state.get('mood_checkins', []))} self-reported mood check-ins stored locally."
            ),
        },
        "Distance from Earth": {
            "connected_modules": ["Distance from Earth Dashboard", "Communication Delay Simulator", "Store-and-Forward Message Centre", "Food & Supplies Estimator"],
            "summary": (
                f"{comm_centre_state['distance_million_km']}M km from Earth "
                f"({comm_centre_state['one_way_delay_minutes']} min one-way / {comm_centre_state['round_trip_delay_minutes']} min round-trip; "
                f"{comm_centre_state['comm_condition']}). Primary meal projection: {food_state['primary_meal_projection']['estimated_remaining_days']} Sols."
            ),
        },
        "Hostile and Closed Environments": {
            "connected_modules": ["Food & Water Storage", "Shelf-Life & Expiry Safety", "ECLSS Potable Water Loop"],
            "summary": (
                f"Potable water reserve at {food_state['summary']['potable_water_liters']} L "
                f"(~{food_state['summary']['estimated_water_supply_days']} Sols); "
                f"{food_state['summary']['expiring_soon_count']} item(s) approaching expiry."
            ),
        },
        "Gravity Fields": {
            "connected_modules": ["Per-Astronaut Nutrition Targets", "Protein/Calcium/Vitamin D & Hydration Tracking", "ARED Countermeasure Alignment"],
            "summary": (
                f"Sol {food_state['mission_config']['current_mission_sol']} intake: "
                f"{food_state['nutrition_overview']['recorded']['calories_kcal']:.0f}/{food_state['nutrition_overview']['targets']['calories_target_kcal']:.0f} kcal, "
                f"Protein {food_state['nutrition_overview']['recorded']['protein_g']:.1f}/{food_state['nutrition_overview']['targets']['protein_target_g']:.0f}g."
            ),
        },
        "Space Radiation": {
            "connected_modules": ["Storm-Shelter Emergency Ration Reserve", "Antioxidant & Micronutrient Tracking", "Autonomous Offline Operations"],
            "summary": (
                "Storm-shelter high-density emergency rations and water-wall bladder reserves tracked continuously alongside radiation dosimetry."
            ),
        },
    }

    return {
        "active_crew_id": active_crew_id,
        "astronaut": baseline.model_dump(),
        "baseline_history": fetch_crew_baseline_history(active_crew_id),
        "latest_telemetry": latest,
        "telemetry_history": history,
        "assessment": assessment,
        "radiation_limits": rad_limits.model_dump(),
        "environmental_limits": env_limits.model_dump(),
        "comm_state": comm_state,
        "store_forward_reports": reports,
        "psych_questionnaires": psych_history,
        "sans_assessments": sans_history,
        "medical_kit": fetch_medical_kit_items(),
        "crew_fleet_matrix": _build_crew_fleet_matrix(rad_limits, env_limits, comm_state),
        "privacy_pin_hint": pin_hint,
        "devices_catalog": HARDWARE_CATALOG,
        "device_states": _normalize_device_states_for_crew(active_crew_id),
        "device_measurements": fetch_device_measurements(crew_id=active_crew_id, limit=80),
        "hardware_examinations": fetch_hardware_examinations(crew_id=active_crew_id, limit=50),
        "biosample_records": fetch_biosample_records(crew_id=active_crew_id, limit=50),
        "donki_state": build_donki_public_state(limit=250),
        "insight_state": build_insight_public_state(limit=14),
        "food_state": food_state,
        "comm_centre_state": comm_centre_state,
        "companion_state": companion_state,
        "knowledge_corpus": [asdict(doc) for doc in KNOWLEDGE_CORPUS],
        "local_ai_status": get_local_ai_status(),
    }


from local_ai_rag import get_local_ai_status
from marscare_routes import initialize_marscare_rag, marscare_router

initialize_marscare_rag()
app.include_router(marscare_router, prefix="/api")
register_state_builder(_build_full_state)
app.include_router(hardware_router)
register_donki_state_builder(_build_full_state)
app.include_router(donki_router)
register_insight_state_builder(_build_full_state)
app.include_router(insight_router)
register_support_state_builder(_build_full_state)
app.include_router(support_router)


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    return {"status": "ok", "system": "TARS Care AI", "offline_ready": True}


@app.get("/api/state")
def get_system_state() -> Dict[str, Any]:
    return _build_full_state()


@app.get("/api/baseline")
def get_baseline_calibration() -> Dict[str, Any]:
    cid = get_active_crew_id()
    return {
        "baseline": fetch_crew_baseline(cid) or AstronautBaseline().model_dump(),
        "history": fetch_crew_baseline_history(cid),
    }


@app.post("/api/baseline")
def update_baseline_calibration(payload: BaselineUpdateInput) -> Dict[str, Any]:
    cid = get_active_crew_id()
    current = fetch_crew_baseline(cid) or AstronautBaseline().model_dump()
    updates = payload.model_dump(exclude_none=True)
    reason = str(updates.pop("reason", "Crew / CMO Baseline Calibration")).strip() or "Crew / CMO Baseline Calibration"
    changed_fields: Dict[str, Any] = {}
    for k, v in updates.items():
        val = v.value if hasattr(v, "value") else v
        if current.get(k) != val:
            changed_fields[k] = {"from": current.get(k), "to": val}
        current[k] = val

    validated = AstronautBaseline(**current).model_dump()
    audit_entry = (
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "reason": reason,
            "changed_fields": changed_fields,
        }
        if changed_fields
        else None
    )
    save_crew_baseline(cid, validated, audit_entry)

    return _build_full_state()


@app.post("/api/measurements")
def submit_health_measurement(submission: HealthMeasurementSubmission) -> Dict[str, Any]:
    data = submission.model_dump()
    data["mission_phase"] = submission.mission_phase.value
    data["provenance"] = submission.provenance.value
    inserted = insert_telemetry_record(data)

    state = _build_full_state()
    assessment = state["assessment"]
    comm_norm = normalize_comm_mode(state["comm_state"])

    # Automatically queue a store-and-forward report if WARNING or CRITICAL
    if assessment["overall_status"] in ("WARNING", "CRITICAL"):
        triggered_hazards = [
            h for h, st in assessment["hazard_statuses"].items() if st in ("WARNING", "CRITICAL")
        ]
        create_store_forward_report(
            mission_day=inserted["mission_day"],
            title=f"Sol {inserted['mission_day']} Automated {assessment['overall_status']} Telemetry Package",
            summary=(
                f"Submitted measurement ({inserted['provenance']}) triggered {assessment['overall_status']} "
                f"in: {', '.join(triggered_hazards)}."
            ),
            risk_level=assessment["overall_status"],
            hazard_triggers=triggered_hazards,
            payload={
                "heart_rate_bpm": inserted["heart_rate_bpm"],
                "systolic_bp_mmhg": inserted["systolic_bp_mmhg"],
                "equivalent_dose_rate_msv_day": inserted["equivalent_dose_rate_msv_day"],
                "sleep_duration_hrs": inserted["sleep_duration_hrs"],
                "co2_mmhg": inserted["co2_mmhg"],
            },
            provenance=inserted["provenance"],
            comm_online=comm_norm["mode"] == "CONNECTED",
        )
        state = _build_full_state()

    return state


@app.post("/api/scenario/{scenario_id}")
def load_demo_scenario(scenario_id: str) -> Dict[str, Any]:
    history = fetch_all_telemetry()
    last = history[-1]
    next_day = int(last["mission_day"]) + 1
    cum_dose = float(last["cumulative_effective_dose_msv"])

    scenarios: Dict[str, Dict[str, Any]] = {
        "NOMINAL_MARS_SOL": {
            "mission_day": next_day,
            "mission_phase": MissionPhase.MARS_SURFACE.value,
            "gravity_g": 0.38,
            "provenance": DataProvenance.SYNTHETIC_DEMO.value,
            "absorbed_dose_mgy": 0.31,
            "absorbed_dose_rate_mgy_hr": 0.0129,
            "equivalent_dose_msv": 0.76,
            "equivalent_dose_rate_msv_day": 0.76,
            "cumulative_effective_dose_msv": round(cum_dose + 0.76, 2),
            "radiation_source": "HABITAT_TEPC_SYNTHETIC",
            "radiation_event_type": "GCR_MARS_SHIELDED",
            "mood_score": 8.2,
            "stress_level": 2.6,
            "emotional_wellbeing": 8.3,
            "fatigue_level": 3.1,
            "workload_score": 5.8,
            "social_interaction_score": 8.4,
            "sleep_duration_hrs": 7.6,
            "sleep_quality_pct": 89.0,
            "sleep_schedule_window": "22:15 - 05:50 UTC-MARS",
            "sleep_irregularities": 0,
            "feeling_isolated": False,
            "concentration_difficulty": False,
            "motivation_level": 8.6,
            "heart_rate_bpm": 60.0,
            "systolic_bp_mmhg": 111.0,
            "diastolic_bp_mmhg": 71.0,
            "spo2_pct": 98.4,
            "body_temp_c": 36.6,
            "dizziness_severity": 0,
            "faintness_presyncope": False,
            "physical_activity_mins": 115.0,
            "exercise_performance_pct": 97.0,
            "muscle_strength_idx": 96.5,
            "exercise_adherence_pct": 96.0,
            "musculoskeletal_discomfort": 0,
            "balance_score": 92.0,
            "coordination_score": 94.0,
            "spatial_disorientation": False,
            "visual_disturbance_sans": False,
            "cabin_temp_c": 21.2,
            "cabin_pressure_kpa": 70.3,
            "oxygen_pct": 21.1,
            "co2_mmhg": 2.2,
            "co2_ppm": 2890.0,
            "humidity_pct": 46.0,
            "air_quality_index": 18.0,
            "env_warning_event": "NONE",
            "respiratory_symptoms": [],
            "infection_symptoms": [],
            "hygiene_adherence_pct": 98.0,
            "notes": "Synthetic Scenario: Nominal Martian surface Sol following CDRA scrubber regeneration and 7.6h restorative sleep.",
        },
        "SPE_SOLAR_STORM_CRITICAL": {
            "mission_day": next_day,
            "mission_phase": MissionPhase.MARS_SURFACE.value,
            "gravity_g": 0.38,
            "provenance": DataProvenance.SYNTHETIC_DEMO.value,
            "absorbed_dose_mgy": 2.85,
            "absorbed_dose_rate_mgy_hr": 0.1188,
            "equivalent_dose_msv": 6.40,
            "equivalent_dose_rate_msv_day": 6.40,
            "cumulative_effective_dose_msv": round(cum_dose + 6.40, 2),
            "radiation_source": "ORBITAL_SEP_MONITOR_PLUS_CREW_DOSIMETER (SYNTHETIC)",
            "radiation_event_type": "SPE_MAJOR_CME_PROTON_STORM",
            "mood_score": 6.5,
            "stress_level": 6.8,
            "emotional_wellbeing": 6.2,
            "fatigue_level": 6.0,
            "workload_score": 7.5,
            "social_interaction_score": 7.2,
            "sleep_duration_hrs": 5.8,
            "sleep_quality_pct": 71.0,
            "sleep_schedule_window": "23:30 - 05:20 UTC-MARS",
            "sleep_irregularities": 3,
            "feeling_isolated": False,
            "concentration_difficulty": True,
            "motivation_level": 7.4,
            "heart_rate_bpm": 76.0,
            "systolic_bp_mmhg": 106.0,
            "diastolic_bp_mmhg": 69.0,
            "spo2_pct": 97.9,
            "body_temp_c": 36.8,
            "dizziness_severity": 1,
            "faintness_presyncope": False,
            "physical_activity_mins": 60.0,
            "exercise_performance_pct": 88.0,
            "muscle_strength_idx": 92.0,
            "exercise_adherence_pct": 85.0,
            "musculoskeletal_discomfort": 1,
            "balance_score": 85.0,
            "coordination_score": 88.0,
            "spatial_disorientation": False,
            "visual_disturbance_sans": False,
            "cabin_temp_c": 22.8,
            "cabin_pressure_kpa": 70.2,
            "oxygen_pct": 21.0,
            "co2_mmhg": 3.5,
            "co2_ppm": 4600.0,
            "humidity_pct": 48.0,
            "air_quality_index": 34.0,
            "env_warning_event": "STORM_SHELTER_CO2_BUILDUP",
            "respiratory_symptoms": ["Headache (CO2 correlated)"],
            "infection_symptoms": [],
            "hygiene_adherence_pct": 94.0,
            "notes": "Synthetic Scenario: X-class solar flare & coronal mass ejection (SPE) driving 6.40 mSv/day equivalent dose rate (2.85 mGy absorbed). Crew confined inside high-mass polyethylene storm shelter.",
        },
        "GRAVITY_ORTHOSTATIC_CRITICAL": {
            "mission_day": next_day,
            "mission_phase": MissionPhase.MARS_SURFACE.value,
            "gravity_g": 0.38,
            "provenance": DataProvenance.SYNTHETIC_DEMO.value,
            "absorbed_dose_mgy": 0.35,
            "absorbed_dose_rate_mgy_hr": 0.0146,
            "equivalent_dose_msv": 0.85,
            "equivalent_dose_rate_msv_day": 0.85,
            "cumulative_effective_dose_msv": round(cum_dose + 0.85, 2),
            "radiation_source": "HABITAT_TEPC_SYNTHETIC",
            "radiation_event_type": "GCR_MARS_SHIELDED",
            "mood_score": 6.2,
            "stress_level": 6.1,
            "emotional_wellbeing": 6.4,
            "fatigue_level": 7.4,
            "workload_score": 8.1,
            "social_interaction_score": 7.0,
            "sleep_duration_hrs": 5.6,
            "sleep_quality_pct": 70.0,
            "sleep_schedule_window": "23:15 - 04:50 UTC-MARS",
            "sleep_irregularities": 3,
            "feeling_isolated": False,
            "concentration_difficulty": True,
            "motivation_level": 7.0,
            "heart_rate_bpm": 96.0,
            "systolic_bp_mmhg": 86.0,
            "diastolic_bp_mmhg": 56.0,
            "spo2_pct": 97.1,
            "body_temp_c": 36.9,
            "dizziness_severity": 3,
            "faintness_presyncope": True,
            "physical_activity_mins": 45.0,
            "exercise_performance_pct": 74.0,
            "muscle_strength_idx": 86.0,
            "exercise_adherence_pct": 72.0,
            "musculoskeletal_discomfort": 2,
            "balance_score": 68.0,
            "coordination_score": 73.0,
            "spatial_disorientation": True,
            "visual_disturbance_sans": True,
            "cabin_temp_c": 22.1,
            "cabin_pressure_kpa": 70.3,
            "oxygen_pct": 21.0,
            "co2_mmhg": 2.9,
            "co2_ppm": 3810.0,
            "humidity_pct": 41.0,
            "air_quality_index": 29.0,
            "env_warning_event": "NONE",
            "respiratory_symptoms": [],
            "infection_symptoms": [],
            "hygiene_adherence_pct": 95.0,
            "notes": "Synthetic Scenario: Acute post-EVA orthostatic intolerance & presyncope in 0.38g (HR 96 bpm vs 58 bpm baseline; BP 86/56 mmHg) with SANS visual shift and neurovestibular balance drop.",
        },
        "ENV_CO2_CONFINEMENT_WARNING": {
            "mission_day": next_day,
            "mission_phase": MissionPhase.MICROGRAVITY_TRANSIT.value,
            "gravity_g": 0.0,
            "provenance": DataProvenance.SIMULATED_ENV.value,
            "absorbed_dose_mgy": 0.49,
            "absorbed_dose_rate_mgy_hr": 0.0204,
            "equivalent_dose_msv": 1.22,
            "equivalent_dose_rate_msv_day": 1.22,
            "cumulative_effective_dose_msv": round(cum_dose + 1.22, 2),
            "radiation_source": "TRANSIT_TEPC_SYNTHETIC",
            "radiation_event_type": "GCR_BACKGROUND",
            "mood_score": 5.4,
            "stress_level": 7.2,
            "emotional_wellbeing": 5.5,
            "fatigue_level": 7.6,
            "workload_score": 8.4,
            "social_interaction_score": 5.2,
            "sleep_duration_hrs": 5.1,
            "sleep_quality_pct": 64.0,
            "sleep_schedule_window": "01:10 - 06:15 UTC-MARS",
            "sleep_irregularities": 4,
            "feeling_isolated": True,
            "concentration_difficulty": True,
            "motivation_level": 5.8,
            "heart_rate_bpm": 69.0,
            "systolic_bp_mmhg": 115.0,
            "diastolic_bp_mmhg": 75.0,
            "spo2_pct": 95.8,
            "body_temp_c": 37.5,
            "dizziness_severity": 1,
            "faintness_presyncope": False,
            "physical_activity_mins": 70.0,
            "exercise_performance_pct": 82.0,
            "muscle_strength_idx": 90.5,
            "exercise_adherence_pct": 78.0,
            "musculoskeletal_discomfort": 1,
            "balance_score": 83.0,
            "coordination_score": 84.0,
            "spatial_disorientation": False,
            "visual_disturbance_sans": True,
            "cabin_temp_c": 25.4,
            "cabin_pressure_kpa": 70.1,
            "oxygen_pct": 20.1,
            "co2_mmhg": 4.1,
            "co2_ppm": 5390.0,
            "humidity_pct": 28.0,
            "air_quality_index": 68.0,
            "env_warning_event": "CO2_SCRUBBER_SATURATION_AND_LOW_HUMIDITY",
            "respiratory_symptoms": ["Dry cough", "Mucosal irritation", "Headache (CO2 pocket)"],
            "infection_symptoms": ["Low-grade temperature elevation (37.5°C)"],
            "hygiene_adherence_pct": 91.0,
            "notes": "Simulated Environment Scenario: Stagnant microgravity CO2 pocket (4.1 mmHg / 5390 ppm), low cabin humidity (28%), sleep truncation (5.1 hrs), isolation strain, and mucosal irritation.",
        },
    }

    alias_map = {
        "nominal": "NOMINAL_MARS_SOL",
        "spe_storm": "SPE_SOLAR_STORM_CRITICAL",
        "co2_sleep_fatigue": "ENV_CO2_CONFINEMENT_WARNING",
        "critical_orthostatic": "GRAVITY_ORTHOSTATIC_CRITICAL",
    }
    canonical_id = alias_map.get(scenario_id, scenario_id)

    if canonical_id not in scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    inserted = insert_telemetry_record(scenarios[canonical_id])
    state = _build_full_state()
    assessment = state["assessment"]
    comm_norm = normalize_comm_mode(state["comm_state"])
    if assessment["overall_status"] in ("WARNING", "CRITICAL"):
        triggered_hazards = [
            h for h, st in assessment["hazard_statuses"].items() if st in ("WARNING", "CRITICAL")
        ]
        create_store_forward_report(
            mission_day=inserted["mission_day"],
            title=f"Sol {inserted['mission_day']} Scenario [{canonical_id}] Assessment Packet",
            summary=scenarios[canonical_id]["notes"],
            risk_level=assessment["overall_status"],
            hazard_triggers=triggered_hazards,
            payload={
                "scenario_id": canonical_id,
                "overall_status": assessment["overall_status"],
                "equivalent_dose_rate_msv_day": inserted["equivalent_dose_rate_msv_day"],
                "heart_rate_bpm": inserted["heart_rate_bpm"],
                "co2_mmhg": inserted["co2_mmhg"],
                "sleep_duration_hrs": inserted["sleep_duration_hrs"],
            },
            provenance=inserted["provenance"],
            comm_online=comm_norm["mode"] == "CONNECTED",
        )
        state = _build_full_state()

    return state


@app.post("/api/psych-questionnaire")
def submit_psych_questionnaire(payload: PsychQuestionnaireInput) -> Dict[str, Any]:
    """
    Persist structured psychological & behavioral check-in independently in psych_questionnaires.
    Does NOT duplicate physiological telemetry_records or overwrite vital-sign values.
    """
    insert_psych_questionnaire(payload.model_dump())
    return _build_full_state()


@app.post("/api/comm/status")
def update_comm_status(payload: CommStatusUpdate) -> Dict[str, Any]:
    comm_state = fetch_system_state("comm_state") or {}
    comm_state["earth_comm_status"] = payload.earth_comm_status
    comm_state["one_way_delay_minutes"] = payload.one_way_delay_minutes
    comm_state["round_trip_delay_minutes"] = round(float(payload.one_way_delay_minutes) * 2.0, 2)
    comm_state["offline_mode_forced"] = payload.offline_mode_forced
    if payload.offline_mode_forced or "BLACKOUT" in payload.earth_comm_status.upper():
        comm_state["comm_condition"] = "BLACKOUT"
    elif "DEGRADED" in payload.earth_comm_status.upper():
        comm_state["comm_condition"] = "INTERMITTENT"
    elif float(payload.one_way_delay_minutes) <= 0.1:
        comm_state["comm_condition"] = "NORMAL"
    else:
        comm_state["comm_condition"] = "DELAYED"
    update_system_state("comm_state", comm_state)
    return _build_full_state()


@app.post("/api/comm/queue-report")
def queue_health_report(payload: StoreForwardReportCreate) -> Dict[str, Any]:
    state = _build_full_state()
    mission_day = state["latest_telemetry"]["mission_day"]
    create_store_forward_report(
        mission_day=mission_day,
        title=payload.title,
        summary=payload.summary,
        risk_level=payload.risk_level.value,
        hazard_triggers=payload.hazard_triggers,
        payload=payload.payload_snapshot,
        provenance=payload.provenance.value,
        comm_online=False,
    )
    return _build_full_state()


@app.post("/api/comm/sync")
def sync_reports_to_earth(simulate_intermittent_drop: bool = False) -> Dict[str, Any]:
    sync_result = synchronize_all_communications(simulate_intermittent_drop=simulate_intermittent_drop)
    state = _build_full_state()
    return {"sync_result": sync_result, "state": state}


@app.post("/api/emergency/escalate")
def trigger_emergency_escalation(payload: EmergencyEscalationInput) -> Dict[str, Any]:
    state = _build_full_state()
    comm_state = state["comm_state"]
    latest = state["latest_telemetry"]
    vital_summary = (payload.vital_signs_summary or "").strip()
    if not vital_summary:
        vital_summary = (
            f"Sol {latest['mission_day']} | HR {latest['heart_rate_bpm']} bpm | "
            f"BP {latest['systolic_bp_mmhg']}/{latest['diastolic_bp_mmhg']} mmHg | "
            f"SpO2 {latest['spo2_pct']}% | RR {latest.get('respiratory_rate_bpm', 16)}/min | "
            f"Temp {latest['body_temp_c']}°C | CO2 {latest['co2_mmhg']} mmHg | "
            f"Rad {latest['equivalent_dose_rate_msv_day']} mSv/day ({latest['absorbed_dose_mgy']} mGy)"
        )
    symptoms = list(payload.reported_symptoms or [])
    if not symptoms:
        for flag, label in [
            (latest.get("chest_discomfort"), "Chest discomfort"),
            (latest.get("palpitations"), "Palpitations"),
            (latest.get("shortness_of_breath"), "Shortness of breath"),
            (latest.get("faintness_presyncope"), "Faintness / presyncope"),
        ]:
            if flag and label not in symptoms:
                symptoms.append(label)
        for s in latest.get("reported_symptoms") or []:
            if s not in symptoms:
                symptoms.append(s)

    protocol = generate_local_emergency_protocol(
        trigger_hazard=payload.trigger_hazard,
        severity=payload.severity.value,
        reported_symptoms=symptoms,
        vital_signs_summary=vital_summary,
        mission_phase=payload.mission_phase.value,
        comm_state=comm_state,
    )
    mission_day = latest["mission_day"]
    comm_norm = normalize_comm_mode(comm_state)
    create_store_forward_report(
        mission_day=mission_day,
        title=f"PRIORITY-1 EMERGENCY ESCALATION: {protocol['protocol_id']}",
        summary=f"{protocol['protocol_title']} triggered for {payload.trigger_hazard}. Vital summary: {vital_summary}",
        risk_level="CRITICAL",
        hazard_triggers=[payload.trigger_hazard],
        payload=protocol,
        provenance=DataProvenance.USER_ENTERED.value,
        comm_online=comm_norm["mode"] == "CONNECTED",
    )
    updated_state = _build_full_state()
    return {"protocol": protocol, "state": updated_state}


@app.post("/api/rag/query")
def query_rag_knowledge_base(payload: RAGQueryInput) -> Dict[str, Any]:
    state = _build_full_state()
    ctx: Optional[Dict[str, Any]] = None
    if payload.include_astronaut_context:
        latest = state["latest_telemetry"]
        findings = state["assessment"].get("findings") or []
        ctx = {
            "astronaut_name": state["astronaut"].get("name", "SuChai"),
            "mission_day": latest["mission_day"],
            "mission_phase": latest["mission_phase"],
            "gravity_g": latest["gravity_g"],
            "overall_status": state["assessment"]["overall_status"],
            "hazard_statuses": state["assessment"].get("hazard_statuses", {}),
            "provenance": latest.get("provenance", "SYNTHETIC_DEMO"),
            "latest_telemetry": latest,
            "baseline": state["astronaut"],
            "active_alerts": [
                f"{f.get('title')} ({f.get('severity')}): {f.get('detail')}"
                for f in findings[:5]
            ],
            "history": [{"role": m.role, "content": m.content} for m in payload.history[-6:]],
            "allow_llm": True,
        }
    return rag_engine.answer_question(
        question=payload.question,
        hazard_filter=payload.hazard_filter,
        astronaut_context=ctx,
    )


class ConfigLimitsUpdate(BaseModel):
    radiation_limits: Optional[RadiationConfigLimits] = None
    environmental_limits: Optional[EnvironmentalConfigLimits] = None


@app.post("/api/config/limits")
def update_configured_limits(payload: ConfigLimitsUpdate) -> Dict[str, Any]:
    if payload.radiation_limits:
        update_system_state("rad_limits", payload.radiation_limits.model_dump())
    if payload.environmental_limits:
        update_system_state("env_limits", payload.environmental_limits.model_dump())
    return _build_full_state()


@app.post("/api/reset")
def reset_demo_database() -> Dict[str, Any]:
    _VERIFIED_DB_PATHS.discard(database.DB_PATH)
    if os.path.exists(database.DB_PATH):
        os.remove(database.DB_PATH)
    _ensure_db_initialized()
    return _build_full_state()


@app.get("/api/crew/matrix")
def get_crew_matrix() -> Dict[str, Any]:
    rad_limits = RadiationConfigLimits(**(fetch_system_state("rad_limits") or {}))
    env_limits = EnvironmentalConfigLimits(**(fetch_system_state("env_limits") or {}))
    comm_state = fetch_system_state("comm_state") or {}
    return {
        "active_crew_id": get_active_crew_id(),
        "crew_fleet_matrix": _build_crew_fleet_matrix(rad_limits, env_limits, comm_state),
    }


@app.post("/api/crew/select")
def select_active_crew(payload: CrewSelectInput) -> Dict[str, Any]:
    try:
        set_active_crew_id(payload.crew_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_full_state()


@app.post("/api/crew/unlock-reflections")
def unlock_crew_reflections(payload: CrewPinVerifyInput) -> Dict[str, Any]:
    pins = fetch_system_state("crew_privacy_pins") or {}
    entry = pins.get(payload.crew_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown crew profile: {payload.crew_id}")
    if not verify_privacy_pin(payload.pin, entry.get("pin_hash", "")):
        raise HTTPException(status_code=403, detail="Invalid Privacy PIN. Behavioral reflections remain locked.")
    return {
        "unlocked": True,
        "crew_id": payload.crew_id,
        "message": "Behavioral reflections unlocked locally for this session.",
    }


@app.post("/api/crew/pin")
def update_crew_privacy_pin(payload: CrewPinUpdateInput) -> Dict[str, Any]:
    pins = fetch_system_state("crew_privacy_pins") or {}
    entry = pins.get(payload.crew_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown crew profile: {payload.crew_id}")
    if not verify_privacy_pin(payload.current_pin, entry.get("pin_hash", "")):
        raise HTTPException(status_code=403, detail="Current PIN did not match.")
    pins[payload.crew_id] = {
        "pin_hash": hash_privacy_pin(payload.new_pin),
        "hint": "Custom crew PIN configured",
    }
    update_system_state("crew_privacy_pins", pins)
    return {
        "updated": True,
        "crew_id": payload.crew_id,
        "privacy_pin_hint": "Custom crew PIN configured",
    }


@app.get("/api/sans/assessments")
def get_sans_assessments() -> Dict[str, Any]:
    cid = get_active_crew_id()
    return {"crew_id": cid, "sans_assessments": fetch_sans_assessments(cid)}


@app.post("/api/sans/assessments")
def submit_sans_assessment(payload: SansAssessmentInput) -> Dict[str, Any]:
    data = payload.model_dump()
    data["provenance"] = payload.provenance.value
    record = insert_sans_assessment(data)
    state = _build_full_state()
    return {"sans_record": record, "state": state}


@app.get("/api/medkit")
def get_medical_kit() -> Dict[str, Any]:
    return {"medical_kit": fetch_medical_kit_items()}


@app.post("/api/medkit/adjust")
def adjust_medical_kit(payload: MedKitAdjustInput) -> Dict[str, Any]:
    try:
        updated = adjust_medical_kit_item(
            item_code=payload.item_code,
            quantity_delta=payload.quantity_delta,
            set_quantity=payload.set_quantity,
            notes=payload.notes,
            mark_inspected=payload.mark_inspected,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": updated, "medical_kit": fetch_medical_kit_items(), "state": _build_full_state()}


@app.post("/api/consult/flight-surgeon-draft")
def draft_flight_surgeon_consult(payload: FlightSurgeonConsultInput) -> Dict[str, Any]:
    state = _build_full_state()
    sans_list = state.get("sans_assessments") or []
    packet = build_flight_surgeon_consult_packet(
        astronaut=state["astronaut"],
        baseline_history=state.get("baseline_history") or [],
        latest=state["latest_telemetry"],
        assessment=state["assessment"],
        comm_state=state["comm_state"],
        med_kit=state.get("medical_kit") or [],
        latest_sans=(sans_list[0] if (payload.include_sans and sans_list) else None),
        cmo_notes=payload.cmo_notes,
    )
    comm_norm = normalize_comm_mode(state["comm_state"])
    report = create_store_forward_report(
        mission_day=state["latest_telemetry"]["mission_day"],
        title=packet["title"],
        summary=packet["summary"],
        risk_level=payload.urgency.value,
        hazard_triggers=packet["hazard_triggers"],
        payload=packet["payload"],
        provenance=DataProvenance.USER_ENTERED.value,
        comm_online=comm_norm["mode"] == "CONNECTED",
    )
    return {
        "report": report,
        "markdown_preview": packet["markdown_preview"],
        "state": _build_full_state(),
    }

