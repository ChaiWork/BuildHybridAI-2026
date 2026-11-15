"""
FastAPI Router for Hardware Integration, Medical Instruments,
Guided Examinations, Telemetry File Imports, and Biological Samples.
"""

from __future__ import annotations
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from database import (
    attach_biosample_assay,
    create_store_forward_report,
    fetch_all_telemetry,
    fetch_biosample_records,
    fetch_crew_baseline,
    fetch_device_measurements,
    fetch_device_states,
    fetch_hardware_examinations,
    get_active_crew_id,
    insert_biosample_record,
    insert_device_measurements,
    insert_hardware_examination,
    insert_psych_questionnaire,
    insert_sans_assessment,
    insert_telemetry_record,
    upsert_device_state,
)
from hardware_devices import (
    CATALOG_BY_ID,
    HARDWARE_CATALOG,
    get_device_adapter,
    validate_and_normalize_measurement,
)
from models import (
    DataProvenance,
    DeviceConfirmInput,
    DeviceConnectRequest,
    DeviceConnectionStatus,
    DeviceDataQuality,
    HardwareExamInput,
    HealthMeasurementSubmission,
    BiosampleAssayImportInput,
    BiosampleCreateInput,
    TelemetryImportParseInput,
)

hardware_router = APIRouter(prefix="/api/devices", tags=["hardware"])

_STATE_BUILDER: Optional[Callable[[], Dict[str, Any]]] = None


def register_state_builder(builder: Callable[[], Dict[str, Any]]) -> None:
    """Register main._build_full_state without creating circular module imports."""
    global _STATE_BUILDER
    _STATE_BUILDER = builder


def _get_full_state() -> Dict[str, Any]:
    if _STATE_BUILDER is not None:
        return _STATE_BUILDER()
    return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_device(device_id: str) -> Dict[str, Any]:
    dev = CATALOG_BY_ID.get(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Unknown medical instrument '{device_id}'.")
    return dev


def _normalize_device_states_for_crew(crew_id: str) -> Dict[str, Dict[str, Any]]:
    stored = fetch_device_states(crew_id)
    result: Dict[str, Dict[str, Any]] = {}
    for dev in HARDWARE_CATALOG:
        did = dev["device_id"]
        if did in stored:
            result[did] = stored[did]
        else:
            result[did] = {
                "crew_id": crew_id,
                "device_id": did,
                "connection_status": DeviceConnectionStatus.NOT_CONNECTED.value,
                "active_mode": "none",
                "last_error": "",
                "last_measurement_at": "",
                "updated_at": "",
            }
    return result


def _safe_float(val: Any) -> Optional[float]:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _convert_canonical_telemetry_value(field: str, value: float, unit: str) -> float:
    if field == "absorbed_dose_mgy" and unit == "Gy":
        return round(value * 1000.0, 3)
    if field in ("equivalent_dose_rate_msv_day", "cumulative_effective_dose_msv") and unit in ("Sv", "Sv/day"):
        return round(value * 1000.0, 3)
    return float(value)


def _merge_and_save_telemetry(
    crew_id: str,
    updates: Dict[str, Any],
    provenance: str,
    note_suffix: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    history = fetch_all_telemetry(crew_id=crew_id)
    latest = dict(history[-1]) if history else HealthMeasurementSubmission().model_dump(mode="json")

    merged: Dict[str, Any] = {}
    valid_fields = set(HealthMeasurementSubmission.model_fields.keys())
    for k in valid_fields:
        if k in latest:
            merged[k] = latest[k]

    for k, v in updates.items():
        if k in valid_fields and v is not None:
            merged[k] = v

    if extra_fields:
        for k, v in extra_fields.items():
            if k in valid_fields and v is not None:
                merged[k] = v

    # Maintain physical coherence for paired radiation fields when updated
    if "absorbed_dose_mgy" in updates and "absorbed_dose_rate_mgy_hr" not in updates:
        merged["absorbed_dose_rate_mgy_hr"] = round(float(merged["absorbed_dose_mgy"]) / 24.0, 4)
    if "equivalent_dose_rate_msv_day" in updates and "equivalent_dose_msv" not in updates:
        merged["equivalent_dose_msv"] = float(merged["equivalent_dose_rate_msv_day"])

    merged["provenance"] = provenance
    existing_note = str(latest.get("notes") or "").strip()
    merged["notes"] = f"{note_suffix}" + (f" | Prior: {existing_note[:120]}" if existing_note else "")

    validated = HealthMeasurementSubmission(**merged)
    payload = validated.model_dump()
    payload["mission_phase"] = validated.mission_phase.value
    payload["provenance"] = validated.provenance.value

    inserted = insert_telemetry_record(payload, crew_id=crew_id)
    return inserted


@hardware_router.get("/catalog")
def get_device_catalog() -> Dict[str, Any]:
    crew_id = get_active_crew_id()
    return {
        "active_crew_id": crew_id,
        "catalog": HARDWARE_CATALOG,
        "device_states": _normalize_device_states_for_crew(crew_id),
    }


@hardware_router.get("/logs")
def get_hardware_logs() -> Dict[str, Any]:
    crew_id = get_active_crew_id()
    return {
        "active_crew_id": crew_id,
        "device_states": _normalize_device_states_for_crew(crew_id),
        "device_measurements": fetch_device_measurements(crew_id=crew_id, limit=80),
        "hardware_examinations": fetch_hardware_examinations(crew_id=crew_id, limit=50),
        "biosample_records": fetch_biosample_records(crew_id=crew_id, limit=50),
    }


@hardware_router.post("/{device_id}/connect")
def connect_medical_device(device_id: str, req: DeviceConnectRequest) -> Dict[str, Any]:
    device = _require_device(device_id)
    crew_id = get_active_crew_id()
    adapter = get_device_adapter(device_id)

    if req.mode == "hardware":
        ok, msg = adapter.probe_live_interface()
        hint_low = (req.interface_hint or "").lower()
        status = (
            DeviceConnectionStatus.ERROR.value
            if any(tok in hint_low for tok in ("error", "fault", "timeout", "fail"))
            else DeviceConnectionStatus.UNAVAILABLE.value
        )
        # Never claim connected or NORMAL when no live device interface exists
        state = upsert_device_state(
            crew_id=crew_id,
            device_id=device_id,
            connection_status=status,
            active_mode="hardware",
            last_error=msg,
        )
        return {
            "device_id": device_id,
            "connected": bool(ok),
            "connection_status": status,
            "message": msg,
            "supports_simulation": bool(device["capabilities"]["supports_simulation"]),
            "supports_import": bool(device["capabilities"]["supports_import"]),
            "supports_guided_exam": bool(device["capabilities"]["supports_guided_exam"]),
            "device_state": state,
        }

    # req.mode == "simulation"
    if not device["capabilities"]["supports_simulation"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{device['name']} does not support synthetic simulation vitals/readings. "
                "Use its documented workflow (Guided Examination, File Import, or Biological Specimen Log)."
            ),
        )

    sim_msg = (
        f"Simulation Mode active for {device['name']}. "
        "All generated values are labeled SYNTHETIC DEMONSTRATIONS and never real hardware streams."
    )
    state = upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=DeviceConnectionStatus.SIMULATION.value,
        active_mode="simulation",
        last_error="",
    )
    return {
        "device_id": device_id,
        "connected": False,
        "simulation_active": True,
        "connection_status": DeviceConnectionStatus.SIMULATION.value,
        "message": sim_msg,
        "device_state": state,
    }


@hardware_router.post("/{device_id}/disconnect")
def disconnect_medical_device(device_id: str) -> Dict[str, Any]:
    _require_device(device_id)
    crew_id = get_active_crew_id()
    state = upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=DeviceConnectionStatus.DISCONNECTED.value,
        active_mode="none",
        last_error="",
    )
    return {
        "device_id": device_id,
        "connection_status": DeviceConnectionStatus.DISCONNECTED.value,
        "device_state": state,
    }


@hardware_router.post("/{device_id}/collect")
def collect_simulated_device_readings(device_id: str) -> Dict[str, Any]:
    device = _require_device(device_id)
    if not device["capabilities"]["supports_simulation"]:
        raise HTTPException(
            status_code=400,
            detail=f"{device['name']} cannot stream or simulate automated physiological vitals.",
        )

    crew_id = get_active_crew_id()
    adapter = get_device_adapter(device_id)
    baseline = fetch_crew_baseline(crew_id) or {}
    history = fetch_all_telemetry(crew_id=crew_id)
    mission_day = int(history[-1]["mission_day"]) if history else 184

    readings = adapter.build_simulation_readings(crew_id, baseline, mission_day)
    if not readings:
        raise HTTPException(
            status_code=400,
            detail=f"No simulation generator implemented for {device['name']}.",
        )

    state = upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=DeviceConnectionStatus.SIMULATION.value,
        active_mode="simulation",
        last_error="",
    )
    return {
        "device_id": device_id,
        "connection_status": DeviceConnectionStatus.SIMULATION.value,
        "requires_confirmation": True,
        "staged_readings": readings,
        "device_state": state,
    }


@hardware_router.post("/{device_id}/parse-import")
def parse_device_telemetry_import(
    device_id: str, payload: TelemetryImportParseInput
) -> Dict[str, Any]:
    device = _require_device(device_id)
    if not device["capabilities"]["supports_import"]:
        raise HTTPException(
            status_code=400,
            detail=f"{device['name']} does not accept tabular CSV/JSON telemetry imports.",
        )

    crew_id = get_active_crew_id()
    adapter = get_device_adapter(device_id)
    rows, errors = adapter.parse_import(
        payload.raw_text, payload.format, payload.filename, crew_id
    )

    valid_count = sum(1 for r in rows if r["quality_status"] == DeviceDataQuality.VALID.value)
    invalid_count = len(rows) - valid_count
    return {
        "device_id": device_id,
        "filename": payload.filename,
        "requires_confirmation": True,
        "parsed_readings": rows,
        "validation_errors": errors,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
    }


@hardware_router.post("/{device_id}/confirm")
def confirm_device_measurements(
    device_id: str, payload: DeviceConfirmInput
) -> Dict[str, Any]:
    device = _require_device(device_id)
    caps = device["capabilities"]
    if caps.get("is_countermeasure_only") or caps.get("is_wellbeing_activity") or caps.get("supports_biosample"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{device['name']} is a countermeasure, wellbeing, or biological specimen kit and must never submit vital signs."
            ),
        )

    crew_id = get_active_crew_id()
    validated_items: List[Dict[str, Any]] = []
    errors: List[str] = []

    for idx, item in enumerate(payload.measurements):
        if item.device_id != device_id:
            errors.append(
                f"Reading #{idx + 1} has mismatched device_id '{item.device_id}' (expected '{device_id}')."
            )
            continue
        if not item.confirmed:
            errors.append(
                f"Reading #{idx + 1} ({item.measurement_type}) is unconfirmed. Astronaut must explicitly review and confirm before saving."
            )
            continue

        rechecked = validate_and_normalize_measurement(
            astronaut_id=crew_id,
            device=device,
            measurement_type=item.measurement_type,
            raw_value=item.value if item.value is not None else item.value_text,
            unit=item.unit,
            recorded_at=item.recorded_at,
            connection_method=item.connection_method,
            data_source=item.data_source,
            connection_status=item.connection_status.value,
            confirmed=True,
            metadata=item.metadata,
        )
        if rechecked["quality_status"] in (
            DeviceDataQuality.INVALID_UNIT.value,
            DeviceDataQuality.INCOMPLETE.value,
            DeviceDataQuality.OUT_OF_RANGE.value,
        ):
            errors.append(
                f"Reading #{idx + 1} ({rechecked['measurement_type']}): {rechecked['quality_note']}"
            )
            continue
        validated_items.append(rechecked)

    if errors:
        raise HTTPException(status_code=422, detail=" | ".join(errors))

    if not validated_items:
        raise HTTPException(status_code=400, detail="No valid confirmed readings provided.")

    saved = insert_device_measurements(crew_id, validated_items)

    now_iso = _now_iso()
    has_sim = any(r["data_source"] == "simulated" for r in validated_items)
    current_state = _normalize_device_states_for_crew(crew_id)[device_id]
    new_status = (
        DeviceConnectionStatus.SIMULATION.value
        if has_sim
        else current_state.get("connection_status", DeviceConnectionStatus.NOT_CONNECTED.value)
    )
    if new_status == DeviceConnectionStatus.CONNECTED.value and not has_sim:
        new_status = DeviceConnectionStatus.DISCONNECTED.value

    upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=new_status,
        active_mode="simulation" if has_sim else current_state.get("active_mode", "import"),
        last_error="",
        last_measurement_at=now_iso,
    )

    state_payload: Dict[str, Any] = {}
    if payload.evaluate_health_assessment:
        telemetry_updates: Dict[str, Any] = {}
        extra_updates: Dict[str, Any] = {}
        for r in validated_items:
            tfield = r.get("telemetry_field")
            if tfield and r.get("value") is not None:
                telemetry_updates[tfield] = _convert_canonical_telemetry_value(
                    tfield, float(r["value"]), str(r["unit"])
                )
        if any(r["measurement_category"] == "radiation" for r in validated_items):
            src_tag = "SIMULATED" if has_sim else "IMPORTED"
            extra_updates["radiation_source"] = f"{device['name']} ({src_tag})"

        if telemetry_updates:
            prov = (
                DataProvenance.SYNTHETIC_DEMO.value
                if has_sim
                else DataProvenance.USER_ENTERED.value
            )
            source_desc = "Simulation Mode" if has_sim else "Imported File"
            user_note = f" — {payload.notes.strip()}" if payload.notes.strip() else ""
            _merge_and_save_telemetry(
                crew_id=crew_id,
                updates=telemetry_updates,
                provenance=prov,
                note_suffix=f"Hardware {source_desc} ({device['name']}){user_note}",
                extra_fields=extra_updates,
            )

        state_payload = _get_full_state()
        assessment = state_payload.get("assessment") or {}
        if assessment.get("overall_status") in ("WARNING", "CRITICAL") and telemetry_updates:
            comm_online = str((state_payload.get("comm_state") or {}).get("mode", "")).upper() == "CONNECTED"
            triggered = [
                h for h, st in (assessment.get("hazard_statuses") or {}).items()
                if st in ("WARNING", "CRITICAL")
            ]
            latest_t = state_payload.get("latest_telemetry") or {}
            create_store_forward_report(
                mission_day=int(latest_t.get("mission_day", 184)),
                title=f"Sol {latest_t.get('mission_day', 184)} Hardware {assessment['overall_status']} Alert ({device['code']})",
                summary=(
                    f"{device['name']} confirmed readings triggered {assessment['overall_status']} "
                    f"in: {', '.join(triggered) or 'Integrated Assessment'}."
                ),
                risk_level=assessment["overall_status"],
                hazard_triggers=triggered,
                payload={k: telemetry_updates[k] for k in telemetry_updates},
                provenance=latest_t.get("provenance", DataProvenance.USER_ENTERED.value),
                comm_online=comm_online,
                crew_id=crew_id,
            )
            state_payload = _get_full_state()
    else:
        state_payload = _get_full_state()

    return {
        "device_id": device_id,
        "saved_measurements": saved,
        "evaluated": bool(payload.evaluate_health_assessment),
        "state": state_payload,
    }


@hardware_router.post("/{device_id}/examination")
def record_hardware_examination(
    device_id: str, payload: HardwareExamInput
) -> Dict[str, Any]:
    device = _require_device(device_id)
    if not device["capabilities"]["supports_guided_exam"]:
        raise HTTPException(
            status_code=400,
            detail=f"{device['name']} does not support guided examination workflows.",
        )
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Examination record must be reviewed and confirmed before saving.",
        )

    crew_id = get_active_crew_id()
    findings = dict(payload.findings or {})
    summary_note = payload.summary.strip()
    abnormal_flag = bool(findings.get("abnormal_flag", False))
    abnormal_reasons: List[str] = []
    if findings.get("abnormal_reason"):
        abnormal_reasons.append(str(findings["abnormal_reason"]).strip())

    exam_type = f"{device['code']}_GUIDED_EXAM"
    extra_measurements: List[Dict[str, Any]] = []
    telemetry_updates: Dict[str, Any] = {}

    if device_id == "ULTRASOUND_VASCULAR":
        exam_type = "ULTRASOUND_EXAM_LOG"
        caution = "TARS Care logs ultrasound metadata and operator/image files only; automated ultrasound diagnosis is NOT performed."
        summary_note = f"{summary_note} — {caution}".strip(" —")
        if bool(findings.get("cmo_review_requested")):
            abnormal_flag = True
            abnormal_reasons.append("Operator flagged ultrasound findings for CMO/Flight Surgeon review.")

    elif device_id == "OCULAR_TONOMETER_SANS":
        exam_type = "OCULAR_TONOMETRY_SANS"
        iop_od = _safe_float(findings.get("iop_od_mmhg"))
        iop_os = _safe_float(findings.get("iop_os_mmhg"))
        wavy = bool(findings.get("wavy_lines_detected", False))
        acuity = bool(findings.get("near_acuity_shift", False))
        if iop_od is not None and iop_od > 21.0:
            abnormal_flag = True
            abnormal_reasons.append(f"Right eye IOP {iop_od} mmHg exceeds 21 mmHg screening threshold.")
        if iop_os is not None and iop_os > 21.0:
            abnormal_flag = True
            abnormal_reasons.append(f"Left eye IOP {iop_os} mmHg exceeds 21 mmHg screening threshold.")
        if iop_od is not None and iop_os is not None and abs(iop_od - iop_os) >= 4.0:
            abnormal_flag = True
            abnormal_reasons.append(f"Inter-eye IOP asymmetry {abs(iop_od - iop_os):.1f} mmHg (>= 4 mmHg).")
        if wavy or acuity:
            abnormal_flag = True
            abnormal_reasons.append("Subjective SANS visual distortion or hyperopic near-acuity shift reported.")
            insert_sans_assessment(
                {
                    "mission_day": payload.mission_day,
                    "eye_tested": str(findings.get("eye_tested") or "BOTH"),
                    "wavy_lines_detected": wavy,
                    "scotoma_cells": list(findings.get("scotoma_cells") or []),
                    "near_acuity_shift": acuity,
                    "notes": f"Tonometer Exam (OD={iop_od}, OS={iop_os} mmHg): {summary_note}",
                    "provenance": DataProvenance.USER_ENTERED.value,
                },
                crew_id=crew_id,
            )
            telemetry_updates["visual_disturbance_sans"] = True
        for key, mtype in (("iop_od_mmhg", "intraocular_pressure_od"), ("iop_os_mmhg", "intraocular_pressure_os")):
            val = _safe_float(findings.get(key))
            if val is not None:
                m = validate_and_normalize_measurement(
                    astronaut_id=crew_id,
                    device=device,
                    measurement_type=mtype,
                    raw_value=val,
                    unit="mmHg",
                    recorded_at=_now_iso(),
                    connection_method="Guided Ocular Tonometry Exam",
                    data_source=payload.data_source,
                    connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                    confirmed=True,
                )
                if m["quality_status"] == DeviceDataQuality.VALID.value:
                    extra_measurements.append(m)

    elif device_id == "MRI_NEURO_OCULAR":
        exam_type = "MRI_NEURO_OCULAR_RECORD"
        if bool(findings.get("ventricular_enlargement")) or bool(findings.get("globe_flattening")):
            abnormal_flag = True
            abnormal_reasons.append("MRI record indicates neuro-ocular / SANS structural finding requiring Flight Surgeon correlation.")

    elif device_id == "TBONE_3D_SCANNER":
        exam_type = "TBONE_HRPQCT_SCAN"
        vbmd = _safe_float(findings.get("vbmd_mg_ha_cm3"))
        delta_pct = _safe_float(findings.get("bone_density_delta_pct"))
        if delta_pct is not None and delta_pct <= -2.0:
            abnormal_flag = True
            abnormal_reasons.append(f"TBone HR-pQCT density change {delta_pct:.1f}% indicates accelerated skeletal unloading loss.")
        if vbmd is not None:
            m = validate_and_normalize_measurement(
                astronaut_id=crew_id,
                device=device,
                measurement_type="tbone_vbmd",
                raw_value=vbmd,
                unit="mg HA/cm³",
                recorded_at=_now_iso(),
                connection_method="TBone HR-pQCT Scan Record",
                data_source=payload.data_source,
                connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                confirmed=True,
            )
            if m["quality_status"] == DeviceDataQuality.VALID.value:
                extra_measurements.append(m)

    elif device_id == "THIGH_CUFFS_COUNTERMEASURE":
        exam_type = "THIGH_CUFFS_COUNTERMEASURE_LOG"
        # Countermeasure strictly logs intervention — NEVER alters physiological vitals
        telemetry_updates.clear()

    elif device_id == "RADI_N2_BUBBLE":
        exam_type = "RADI_N2_NEUTRON_LOG"
        bubbles = _safe_float(findings.get("neutron_bubble_count"))
        if bubbles is not None:
            m = validate_and_normalize_measurement(
                astronaut_id=crew_id,
                device=device,
                measurement_type="neutron_bubble_count",
                raw_value=bubbles,
                unit="bubbles",
                recorded_at=_now_iso(),
                connection_method=f"Radi-N2 Reader ({findings.get('deployment_location', 'Crew Quarters')})",
                data_source=payload.data_source,
                connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                confirmed=True,
                metadata={"detector_serial": findings.get("detector_serial", "")},
            )
            if m["quality_status"] == DeviceDataQuality.VALID.value:
                extra_measurements.append(m)

    elif device_id == "BEHAVIORAL_SURVEY_SUITE":
        exam_type = "BEHAVIORAL_SURVEY_RECORD"
        mood = _safe_float(findings.get("mood_score"))
        stress = _safe_float(findings.get("stress_level"))
        sleep_q = _safe_float(findings.get("sleep_quality_pct"))
        if mood is not None or stress is not None:
            insert_psych_questionnaire(
                {
                    "mission_day": payload.mission_day,
                    "questionnaire_type": str(findings.get("survey_name") or "BMed Behavioural Survey"),
                    "stress_score_10": stress if stress is not None else 4.0,
                    "mood_score_10": mood if mood is not None else 7.0,
                    "isolation_impact_10": _safe_float(findings.get("isolation_score")) or 3.5,
                    "sleep_quality_rating_10": round((sleep_q or 80.0) / 10.0, 1),
                    "private_reflection": str(findings.get("private_reflection") or ""),
                    "provenance": DataProvenance.USER_ENTERED.value,
                },
                crew_id=crew_id,
            )
            if payload.update_telemetry:
                if mood is not None:
                    telemetry_updates["mood_score"] = mood
                if stress is not None:
                    telemetry_updates["stress_level"] = stress
                if sleep_q is not None:
                    telemetry_updates["sleep_quality_pct"] = sleep_q

    elif device_id == "POSTUROGRAPHY_BALANCE":
        exam_type = "POSTUROGRAPHY_BALANCE_TEST"
        bal = _safe_float(findings.get("balance_score"))
        coord = _safe_float(findings.get("coordination_score"))
        if bal is not None:
            m = validate_and_normalize_measurement(
                astronaut_id=crew_id,
                device=device,
                measurement_type="balance_score",
                raw_value=bal,
                unit="/100",
                recorded_at=_now_iso(),
                connection_method="Guided Posturography Balance Assessment",
                data_source=payload.data_source,
                connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                confirmed=True,
            )
            if m["quality_status"] == DeviceDataQuality.VALID.value:
                extra_measurements.append(m)
            if bal < 70.0:
                abnormal_flag = True
                abnormal_reasons.append(f"Balance stability score {bal}/100 indicates elevated postural instability.")
            if payload.update_telemetry:
                telemetry_updates["balance_score"] = bal
                if coord is not None:
                    telemetry_updates["coordination_score"] = coord

    elif device_id == "CYCLE_ERGOMETER_ASTROFIT":
        exam_type = "CYCLE_ERGOMETER_EXERCISE"
        perf = _safe_float(findings.get("exercise_performance_pct"))
        pwr = _safe_float(findings.get("ergometer_power_w"))
        mins = _safe_float(findings.get("physical_activity_mins"))
        strength = _safe_float(findings.get("muscle_strength_idx"))
        for val, mtype, unit in (
            (perf, "exercise_performance", "%"),
            (pwr, "ergometer_power", "W"),
            (mins, "physical_activity", "mins"),
            (strength, "muscle_strength_index", "index"),
        ):
            if val is not None:
                m = validate_and_normalize_measurement(
                    astronaut_id=crew_id,
                    device=device,
                    measurement_type=mtype,
                    raw_value=val,
                    unit=unit,
                    recorded_at=_now_iso(),
                    connection_method="Guided Cycle Ergometer Countermeasure",
                    data_source=payload.data_source,
                    connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                    confirmed=True,
                )
                if m["quality_status"] == DeviceDataQuality.VALID.value:
                    extra_measurements.append(m)
        if payload.update_telemetry:
            if perf is not None:
                telemetry_updates["exercise_performance_pct"] = perf
            if mins is not None:
                telemetry_updates["physical_activity_mins"] = mins
            if strength is not None:
                telemetry_updates["muscle_strength_idx"] = strength

    elif device_id == "VEGGIE_SPACE_GARDENING":
        exam_type = "VEGGIE_WELLBEING_ACTIVITY"
        # Strictly activity/psychological note — NEVER alters vital signs telemetry
        telemetry_updates.clear()

    if extra_measurements:
        insert_device_measurements(crew_id, extra_measurements)

    if telemetry_updates:
        _merge_and_save_telemetry(
            crew_id=crew_id,
            updates=telemetry_updates,
            provenance=DataProvenance.USER_ENTERED.value,
            note_suffix=f"Guided Examination ({device['name']})",
        )

    attachments_clean = [att.model_dump() for att in payload.attachments]
    saved_exam = insert_hardware_examination(
        crew_id,
        {
            "device_id": device_id,
            "device_name": device["name"],
            "exam_type": exam_type,
            "mission_day": payload.mission_day,
            "recorded_at": _now_iso(),
            "data_source": payload.data_source,
            "findings": findings,
            "summary_note": summary_note or f"{device['name']} examination logged.",
            "abnormal_flag": abnormal_flag,
            "abnormal_reason": " ".join(abnormal_reasons).strip(),
            "attachments": attachments_clean,
        },
    )

    upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=DeviceConnectionStatus.DISCONNECTED.value,
        active_mode="guided_exam",
        last_error="",
        last_measurement_at=saved_exam["recorded_at"],
    )

    return {
        "examination": saved_exam,
        "state": _get_full_state(),
    }


@hardware_router.post("/{device_id}/biosample")
def log_biological_sample(
    device_id: str, payload: BiosampleCreateInput
) -> Dict[str, Any]:
    device = _require_device(device_id)
    if not device["capabilities"]["supports_biosample"]:
        raise HTTPException(
            status_code=400,
            detail=f"{device['name']} is not a biological specimen collection kit.",
        )

    crew_id = get_active_crew_id()
    protocol = (
        "Filter-paper saliva absorption & dry storage booklet"
        if device_id == "SALIVA_BLOTTING_BOOKLET"
        else "Cold stowage biosample tube / multi-matrix collection"
    )
    saved = insert_biosample_record(
        crew_id,
        {
            "device_id": device_id,
            "device_name": device["name"],
            "specimen_type": payload.sample_type.strip(),
            "collection_protocol": protocol,
            "mission_day": payload.mission_day,
            "collected_at": payload.collected_at or _now_iso(),
            "storage_location": payload.storage_location.strip(),
            "status": "COLLECTED_STORED",
            "notes": payload.notes.strip(),
        },
    )
    upsert_device_state(
        crew_id=crew_id,
        device_id=device_id,
        connection_status=DeviceConnectionStatus.DISCONNECTED.value,
        active_mode="specimen_log",
        last_error="",
        last_measurement_at=saved["collected_at"],
    )
    return {
        "biosample": saved,
        "state": _get_full_state(),
    }


@hardware_router.post("/biosamples/{sample_uid}/assay")
def import_biosample_assay_results(
    sample_uid: str, payload: BiosampleAssayImportInput
) -> Dict[str, Any]:
    crew_id = get_active_crew_id()
    text = payload.raw_text.strip()
    parsed_assays: List[Dict[str, Any]] = []

    if payload.format == "json":
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON assay payload: {exc}")
        if isinstance(loaded, dict):
            if isinstance(loaded.get("assays"), list):
                parsed_assays = [dict(x) for x in loaded["assays"] if isinstance(x, dict)]
            else:
                parsed_assays = [loaded]
        elif isinstance(loaded, list):
            parsed_assays = [dict(x) for x in loaded if isinstance(x, dict)]
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=422, detail="CSV assay file is missing headers.")
        parsed_assays = [dict(r) for r in reader]

    if not parsed_assays:
        raise HTTPException(status_code=422, detail="No valid assay rows found in uploaded laboratory report.")

    assay_bundle = {
        "filename": payload.filename,
        "format": payload.format,
        "notes": payload.notes.strip(),
        "markers": parsed_assays,
        "provenance": "IMPORTED_LAB_ASSAY",
    }

    try:
        updated = attach_biosample_assay(crew_id, sample_uid, assay_bundle)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "biosample": updated,
        "state": _get_full_state(),
    }
