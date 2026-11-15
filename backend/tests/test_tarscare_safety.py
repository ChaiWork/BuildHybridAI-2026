"""Automated safety, medical logic, API, RAG, and offline integrity tests for TARSCARE."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import assessment_engine  # noqa: E402
import database  # noqa: E402
import local_ai_rag  # noqa: E402
import main  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Provide an isolated FastAPI TestClient backed by a disposable SQLite file."""
    temp_db = tmp_path / "test_tarscare_local.db"
    monkeypatch.setattr(database, "DB_PATH", str(temp_db))
    with TestClient(main.app) as test_client:
        test_client.post("/api/ai/config", json={"llm_enabled": False, "clear_selected_model": True})
        yield test_client
        test_client.post("/api/ai/config", json={"llm_enabled": True, "clear_selected_model": True})


def test_fix1_emergency_escalation_payloads_and_fallback(client):
    """Fix 1: Full and minimal emergency payloads succeed without 422 and store queued records."""
    # Full explicit cardiopulmonary payload
    res_full = client.post(
        "/api/emergency/escalate",
        json={
            "trigger_hazard": "Cardiopulmonary & Chest Triage",
            "reported_symptoms": ["Chest pain / discomfort", "Palpitations"],
            "vital_signs_summary": "HR 116 BPM | BP 146/94 mmHg | SpO2 93% | RR 24/min",
        },
    )
    assert res_full.status_code == 200
    body_full = res_full.json()
    proto = body_full["protocol"]
    assert proto["protocol_id"] == "EMG-CMO-CARDIOPULM-01"
    assert len(proto["immediate_steps"]) >= 4
    assert proto["protocol_gap_notice"]
    assert "state" in body_full

    # Minimal payload missing vital_signs_summary must auto-fill safely rather than 422
    res_min = client.post(
        "/api/emergency/escalate",
        json={"trigger_hazard": "Space Radiation"},
    )
    assert res_min.status_code == 200
    proto_min = res_min.json()["protocol"]
    assert proto_min["protocol_id"] == "EMG-RAD-SPE-SHELTER-01"
    assert "bpm" in proto_min["vital_signs_summary"].lower()

    # Deterministic offline protocol builder works independently of LLM/Earth link
    offline_proto = assessment_engine.generate_local_emergency_protocol(
        trigger_hazard="Hostile and Closed Environments",
        severity="CRITICAL",
        reported_symptoms=["Dyspnea"],
        vital_signs_summary="CO2 6.8 mmHg | SpO2 90%",
        mission_phase="Deep Space Transit",
        comm_state={
            "earth_comm_status": "CONJUNCTION_BLACKOUT",
            "offline_mode_forced": True,
            "one_way_delay_minutes": 22,
        },
    )
    assert offline_proto["execution_mode"] == "LOCAL_DETERMINISTIC_ZERO_LATENCY"
    assert offline_proto["earth_comm_status"] == "CONJUNCTION_BLACKOUT"
    assert offline_proto["protocol_id"] == "EMG-ENV-ECLSS-ATMOS-03"


def test_fix2_critical_vitals_suppress_exercise_and_sort_priority(client):
    """Fix 2: Critical vitals suppress ROUTINE exercise and prioritize IMMEDIATE actions first."""
    payload = {
        "mission_day": 187,
        "mission_phase": "MICROGRAVITY_TRANSIT",
        "gravity_g": 0.0,
        "heart_rate_bpm": 128,
        "systolic_bp_mmhg": 86,
        "diastolic_bp_mmhg": 55,
        "spo2_pct": 89,
        "respiratory_rate_bpm": 28,
        "body_temp_c": 37.3,
        "sleep_duration_hrs": 5.5,
        "sleep_quality_pct": 52,
        "stress_level": 8,
        "mood_score": 4,
        "fatigue_level": 8,
        "absorbed_dose_mgy": 0.45,
        "equivalent_dose_rate_msv_day": 1.4,
        "cumulative_effective_dose_msv": 95.0,
        "co2_mmhg": 2.3,
        "oxygen_pct": 20.9,
        "cabin_temp_c": 22.0,
        "humidity_pct": 45,
        "exercise_adherence_pct": 60,
        "muscle_strength_idx": 84,
        "balance_score": 78,
        "dizziness_severity": 2,
        "faintness_presyncope": True,
        "exercise_performance_pct": 65,
        "visual_disturbances": False,
        "chest_discomfort": False,
        "palpitations": True,
        "shortness_of_breath": True,
        "reported_symptoms": ["Faintness / presyncope", "Shortness of breath"],
        "respiratory_symptoms": ["Shortness of breath"],
        "notes": "Fix 2 critical triage regression test",
    }
    res = client.post("/api/measurements", json=payload)
    assert res.status_code == 200
    state = res.json()
    assessment = state["assessment"]

    assert assessment["overall_status"] == "CRITICAL"
    assert assessment["exercise_contraindicated"] is True
    assert assessment["auto_emergency_recommended"] is True

    recs = assessment["recommendations"]
    assert len(recs) > 0
    priorities = [r["priority"] for r in recs]
    assert "ROUTINE" not in priorities
    rank_map = {"IMMEDIATE": 0, "HIGH": 1, "ROUTINE": 2}
    ranks = [rank_map[p] for p in priorities]
    assert ranks == sorted(ranks), f"Recommendations out of priority order: {priorities}"
    assert priorities[0] == "IMMEDIATE"

    for rec in recs:
        action_lower = rec["action"].lower()
        assert "perform 20 minutes of resistance" not in action_lower
        assert "perform daily ared" not in action_lower

    # Guidance tiers must block routine exercise and place medical triage first
    tiers = assessment.get("guidance_tiers", {})
    prev_tiers = tiers.get("Preventive action", [])
    assert prev_tiers
    assert "HOLD" in prev_tiers[0]["action"].upper() or "SUSPEND" in prev_tiers[0]["action"].upper()
    imm_tiers = tiers.get("Immediate action", [])
    assert imm_tiers


def test_fix3_scenario_h_cardiopulmonary_red_flags(client):
    """Fix 3: Chest discomfort + palpitations trigger CRITICAL Cardiopulmonary triage & hardware gap notice."""
    res = client.post(
        "/api/measurements",
        json={
            "mission_day": 187,
            "mission_phase": "MICROGRAVITY_TRANSIT",
            "gravity_g": 0.0,
            "heart_rate_bpm": 116,
            "systolic_bp_mmhg": 146,
            "diastolic_bp_mmhg": 94,
            "spo2_pct": 93,
            "respiratory_rate_bpm": 24,
            "body_temp_c": 37.0,
            "sleep_duration_hrs": 6.2,
            "sleep_quality_pct": 65,
            "stress_level": 7,
            "mood_score": 5,
            "fatigue_level": 6,
            "absorbed_dose_mgy": 0.4,
            "equivalent_dose_rate_msv_day": 1.3,
            "cumulative_effective_dose_msv": 90.0,
            "co2_mmhg": 2.0,
            "oxygen_pct": 20.9,
            "cabin_temp_c": 22.0,
            "humidity_pct": 44,
            "exercise_adherence_pct": 85,
            "muscle_strength_idx": 90,
            "balance_score": 90,
            "dizziness_severity": 1,
            "faintness_presyncope": False,
            "exercise_performance_pct": 75,
            "visual_disturbances": False,
            "chest_discomfort": True,
            "palpitations": True,
            "shortness_of_breath": True,
            "reported_symptoms": ["Chest discomfort", "Palpitations", "Shortness of breath"],
            "respiratory_symptoms": ["Shortness of breath"],
        },
    )
    assert res.status_code == 200
    assessment = res.json()["assessment"]
    assert assessment["overall_status"] == "CRITICAL"
    assert assessment["hazard_statuses"]["Gravity Fields"] == "CRITICAL"
    assert any("Cardiopulmonary" in f["title"] for f in assessment["findings"])
    assert assessment["auto_emergency_recommended"] is True
    assert assessment["recommended_emergency_hazard"] == "Cardiopulmonary & Chest Triage"
    assert assessment["exercise_contraindicated"] is True
    assert "ECG" in (assessment.get("protocol_gap_notice") or "")


def test_fix4_5_6_rag_guardrails_refusals_and_llm_verification_gate(client):
    """Fixes 4-6: Offline RAG refuses medications/out-of-scope queries, avoids None leaks, separates conflicts, and gates bad LLM outputs."""
    # Set Offline mode to confirm zero internet dependency
    assert client.post("/api/comm/mode", json={"mode": "OFFLINE"}).status_code == 200

    # 1. Context query must contain real numeric telemetry and never leak "None"
    r_ctx = client.post(
        "/api/rag/query",
        json={"question": "What is my current heart rate, radiation status, and overall status?", "include_astronaut_context": True},
    )
    assert r_ctx.status_code == 200
    assert not r_ctx.json()["engine_mode"].startswith("LOCAL_OLLAMA")
    ans_ctx = r_ctx.json()["answer"]
    assert "None" not in ans_ctx
    assert "NaN" not in ans_ctx

    # 2. Medication request must be declined safely
    r_med = client.post(
        "/api/rag/query",
        json={"question": "Which painkiller or antibiotic medication dose should I take for chest pain?"},
    )
    assert r_med.status_code == 200
    body_med = r_med.json()
    assert body_med["sufficient_evidence"] is False
    assert "does not prescribe" in body_med["answer"].lower() or "cannot prescribe" in body_med["answer"].lower()

    # 3. Unrelated medical procedure / out-of-scope query must refuse cleanly
    r_oos = client.post(
        "/api/rag/query",
        json={"question": "How do you perform laparoscopic appendicitis surgery on Mars?"},
    )
    assert r_oos.status_code == 200
    assert r_oos.json()["sufficient_evidence"] is False

    # 4. Gy vs Sv & ARMAS distinction query returns conflict notice and separates evidence vs operational procedures
    r_rad = client.post(
        "/api/rag/query",
        json={"question": "Explain Gy vs Sv and whether NASA ARMAS flights guarantee my Mars mission radiation safety."},
    )
    assert r_rad.status_code == 200
    body_rad = r_rad.json()
    assert body_rad["sufficient_evidence"] is True
    assert "Gy" in body_rad["answer"] and "Sv" in body_rad["answer"]
    assert body_rad.get("conflict_notice")
    assert "ARMAS" in body_rad["conflict_notice"] or "Gy" in body_rad["conflict_notice"]
    assert len(body_rad.get("scientific_evidence") or []) >= 1
    assert len(body_rad.get("operational_procedures") or []) >= 1

    # 5. Direct unit checks on LLM output verification gate
    citations = [{"doc_id": "NASA-RADLAB-01", "title": "RadLab"}]
    crit_ctx = {"overall_status": "CRITICAL", "hazard_statuses": {"Cardiopulmonary & Chest Triage": "CRITICAL"}}
    assert local_ai_rag._verify_and_finalize_llm_answer("All vital signs are within normal limits.", "status", citations, crit_ctx) is None
    assert local_ai_rag._verify_and_finalize_llm_answer("Heart rate is None bpm today.", "status", citations, crit_ctx) is None
    assert local_ai_rag._verify_and_finalize_llm_answer("Take 400mg ibuprofen now [FAKE-DOC-99].", "meds", citations, crit_ctx) is None
    assert local_ai_rag._verify_and_finalize_llm_answer("ARMAS aviation measurements directly represent Mars surface exposure [NASA-RADLAB-01].", "rad", citations, crit_ctx) is None
    assert local_ai_rag._verify_and_finalize_llm_answer("You are guaranteed safe on Mars.", "rad", citations, crit_ctx) is None
    assert local_ai_rag._verify_and_finalize_llm_answer("Your reading shows elevated dose rate because", "rad", citations, crit_ctx) is None

    valid = local_ai_rag._verify_and_finalize_llm_answer(
        "Absorbed dose uses gray (Gy/mGy), whereas effective dose uses sievert (Sv/mSv) with biological radiation weighting [NASA-RADLAB-01].",
        "Explain Gy vs Sv",
        citations,
        {"overall_status": "NORMAL", "hazard_statuses": {}},
    )
    assert valid is not None and "NASA-RADLAB-01" in valid


def test_fix7_psych_questionnaire_does_not_duplicate_telemetry_or_diagnose(client):
    """Fix 7: Psych check-ins save independently without duplicating telemetry rows or overwriting vitals."""
    res_m = client.post(
        "/api/measurements",
        json={
            "mission_day": 188,
            "mission_phase": "MARS_SURFACE",
            "gravity_g": 0.38,
            "heart_rate_bpm": 91,
            "systolic_bp_mmhg": 124,
            "diastolic_bp_mmhg": 80,
            "spo2_pct": 98.0,
            "respiratory_rate_bpm": 16,
            "body_temp_c": 36.8,
            "sleep_duration_hrs": 7.1,
            "sleep_quality_pct": 80,
            "stress_level": 3,
            "mood_score": 8,
            "fatigue_level": 3,
            "absorbed_dose_mgy": 0.4,
            "equivalent_dose_rate_msv_day": 1.2,
            "cumulative_effective_dose_msv": 85.0,
            "co2_mmhg": 2.0,
            "oxygen_pct": 21.0,
            "cabin_temp_c": 21.5,
            "humidity_pct": 45,
            "exercise_adherence_pct": 90,
            "muscle_strength_idx": 93,
            "balance_score": 92,
            "dizziness_severity": 0,
            "faintness_presyncope": False,
            "exercise_performance_pct": 92,
            "visual_disturbances": False,
        },
    )
    assert res_m.status_code == 200
    count_before = len(res_m.json()["telemetry_history"])

    res_pq = client.post(
        "/api/psych-questionnaire",
        json={
            "mission_day": 188,
            "emotional_condition_rating": 3,
            "psychological_stress_rating": 8,
            "motivation_rating": 4,
            "fatigue_rating": 8,
            "sleep_difficulty_rating": 8,
            "isolation_feeling_rating": 9,
            "concentration_workload_rating": 4,
            "journal_reflection": "Extended confinement reflection Sol 188.",
        },
    )
    assert res_pq.status_code == 200
    after_state = res_pq.json()
    assert len(after_state["telemetry_history"]) == count_before
    assert after_state["latest_telemetry"]["heart_rate_bpm"] == 91
    assert after_state["psych_questionnaires"][0]["journal_reflection"] == "Extended confinement reflection Sol 188."
    assert after_state["assessment"]["hazard_statuses"]["Isolation and Confinement"] in ("WARNING", "CRITICAL")

    iso_findings = [
        f["detail"] for f in after_state["assessment"]["findings"] if f["hazard"] == "Isolation and Confinement"
    ]
    assert iso_findings
    combined_detail = " ".join(iso_findings).lower()
    assert "diagnose major depression" not in combined_detail
    assert "does not constitute a psychiatric diagnosis" in combined_detail


def test_fix8_scenarios_and_aliases(client):
    """Fix 8: Canonical scenarios and lowercase aliases switch telemetry cleanly."""
    r_spe = client.post("/api/scenario/SPE_SOLAR_STORM_CRITICAL")
    assert r_spe.status_code == 200
    assert r_spe.json()["assessment"]["hazard_statuses"]["Space Radiation"] == "CRITICAL"

    r_env = client.post("/api/scenario/co2_sleep_fatigue")
    assert r_env.status_code == 200
    assert r_env.json()["latest_telemetry"]["co2_mmhg"] >= 4.0

    r_grav = client.post("/api/scenario/critical_orthostatic")
    assert r_grav.status_code == 200
    assert r_grav.json()["assessment"]["exercise_contraindicated"] is True

    r_nom = client.post("/api/scenario/nominal")
    assert r_nom.status_code == 200
    assert r_nom.json()["assessment"]["overall_status"] == "NORMAL"


def test_fix9_baseline_calibration_and_audit(client):
    """Fix 9: Baseline updates record an audit entry and adjust relative baseline drift evaluation."""
    res_up = client.post(
        "/api/baseline",
        json={
            "baseline_hr_bpm": 82,
            "baseline_mood_score": 7.5,
            "baseline_stress_score": 3.2,
            "reason": "Calibrated mid-transit baseline shift per flight surgeon review",
        },
    )
    assert res_up.status_code == 200
    up_body = res_up.json()
    assert up_body["astronaut"]["baseline_hr_bpm"] == 82
    assert up_body["astronaut"]["baseline_mood_score"] == 7.5
    assert up_body["astronaut"]["baseline_stress_score"] == 3.2
    assert len(up_body["baseline_history"]) >= 1
    assert "Calibrated mid-transit" in up_body["baseline_history"][0]["reason"]
    assert "baseline_mood_score" in up_body["baseline_history"][0]["changed_fields"]
    assert "baseline_stress_score" in up_body["baseline_history"][0]["changed_fields"]

    # HR 84 vs calibrated baseline 82 (+2) should remain NORMAL
    res_check = client.post(
        "/api/measurements",
        json={
            "mission_day": 189,
            "mission_phase": "MARS_SURFACE",
            "gravity_g": 0.38,
            "heart_rate_bpm": 84,
            "systolic_bp_mmhg": 118,
            "diastolic_bp_mmhg": 76,
            "spo2_pct": 98.2,
            "body_temp_c": 36.8,
            "sleep_duration_hrs": 7.4,
            "sleep_quality_pct": 84,
            "stress_level": 3,
            "mood_score": 8,
            "fatigue_level": 3,
            "absorbed_dose_mgy": 0.4,
            "equivalent_dose_rate_msv_day": 1.2,
            "cumulative_effective_dose_msv": 86.0,
            "co2_mmhg": 2.0,
            "oxygen_pct": 21.0,
            "cabin_temp_c": 21.6,
            "humidity_pct": 44,
            "exercise_adherence_pct": 95,
            "muscle_strength_idx": 94,
            "balance_score": 94,
            "dizziness_severity": 0,
            "faintness_presyncope": False,
            "exercise_performance_pct": 95,
            "visual_disturbances": False,
        },
    )
    assert res_check.status_code == 200
    assert res_check.json()["assessment"]["overall_status"] == "NORMAL"


def test_fix16_offline_sync_blocking_and_delayed_sync(client):
    """Fix 16: Syncing while OFFLINE is blocked safely; switching to DELAYED synchronizes queue."""
    assert client.post("/api/comm/mode", json={"mode": "OFFLINE"}).status_code == 200
    assert client.post("/api/reports/generate", json={}).status_code == 200

    res_blocked = client.post("/api/comm/sync")
    assert res_blocked.status_code == 200
    sr_blocked = res_blocked.json()["sync_result"]
    assert sr_blocked["status"] == "BLOCKED_OFFLINE"
    assert sr_blocked["synchronized_count"] == 0
    assert sr_blocked["remaining_queued"] >= 1

    assert client.post("/api/comm/mode", json={"mode": "DELAYED"}).status_code == 200
    res_ok = client.post("/api/comm/sync")
    assert res_ok.status_code == 200
    sr_ok = res_ok.json()["sync_result"]
    assert sr_ok["synchronized_count"] >= 1
    assert sr_ok["remaining_queued"] == 0


def test_combined_assessment_route_and_history_filter(client):
    """Verify combined /api/assessment/evaluate route, /api/history filter, and /api/baseline GET."""
    res_base = client.get("/api/baseline")
    assert res_base.status_code == 200
    assert "baseline" in res_base.json()

    res_eval = client.post(
        "/api/assessment/evaluate",
        json={
            "heart_rate_bpm": 122,
            "chest_discomfort": True,
            "palpitations": True,
            "selected_symptoms": ["Chest pain / discomfort", "Palpitations"],
            "notes": "Combined endpoint cardiopulmonary check",
        },
    )
    assert res_eval.status_code == 200
    body_eval = res_eval.json()
    assert body_eval["assessment"]["overall_status"] == "CRITICAL"
    assert body_eval["assessment"]["exercise_contraindicated"] is True

    res_hist = client.get("/api/history?days=7")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert "telemetry_history" in hist and len(hist["telemetry_history"]) >= 1
