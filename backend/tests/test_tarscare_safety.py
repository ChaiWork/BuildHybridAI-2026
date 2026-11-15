"""Automated safety, medical logic, API, RAG, and offline integrity tests for TARS Care."""

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


def test_physiological_recommendation_sort_tie_breaker(client):
    """Cardiopulmonary IMMEDIATE alerts always outrank concurrent behavioral IMMEDIATE/HIGH alerts."""
    res_pq = client.post(
        "/api/psych-questionnaire",
        json={
            "mission_day": 190,
            "emotional_condition_rating": 2,
            "psychological_stress_rating": 9,
            "motivation_rating": 3,
            "fatigue_rating": 9,
            "sleep_difficulty_rating": 9,
            "isolation_feeling_rating": 9,
            "concentration_workload_rating": 3,
            "journal_reflection": "Severe confinement distress Sol 190.",
        },
    )
    assert res_pq.status_code == 200

    res_crit = client.post(
        "/api/measurements",
        json={
            "mission_day": 190,
            "heart_rate_bpm": 128,
            "systolic_bp_mmhg": 86,
            "diastolic_bp_mmhg": 55,
            "spo2_pct": 89.0,
            "respiratory_rate_bpm": 28,
            "sleep_duration_hrs": 3.5,
            "mood_score": 2,
            "stress_level": 9,
            "chest_discomfort": True,
            "shortness_of_breath": True,
            "faintness_presyncope": True,
        },
    )
    assert res_crit.status_code == 200
    recs = res_crit.json()["assessment"]["recommendations"]
    assert recs and recs[0]["priority"] == "IMMEDIATE"
    assert recs[0]["procedure_code"] == "PROC-CARDIO-REDFLAG-01"
    iso_indices = [
        i for i, r in enumerate(recs) if "ISO" in str(r.get("procedure_code", "")) or "Isolation" in str(r.get("hazard", ""))
    ]
    if iso_indices:
        assert 0 < iso_indices[0]


def test_eva_readiness_and_predictive_runways(client):
    """EVA readiness switches between HOLD and GO/CAUTION and computes deterministic runways."""
    r_crit = client.post("/api/scenario/critical_orthostatic")
    assert r_crit.status_code == 200
    crit_body = r_crit.json()
    eva_crit = crit_body["assessment"]["eva_readiness"]
    assert eva_crit["status"] == "HOLD"
    assert len(eva_crit["blocking_factors"]) >= 1

    r_nom = client.post("/api/scenario/nominal")
    assert r_nom.status_code == 200
    nom_body = r_nom.json()
    eva_nom = nom_body["assessment"]["eva_readiness"]
    assert eva_nom["status"] in ("GO", "CAUTION")
    assert eva_nom["score_pct"] >= 50
    runways = nom_body["assessment"]["predictive_runways"]
    for key in ("co2", "radiation_budget", "sleep_debt", "musculoskeletal"):
        assert key in runways


def test_sans_amsler_assessment_updates_eye_region_and_eva(client):
    """Interactive Amsler Grid distortion updates eye triage region and EVA readiness advisories."""
    r_nom = client.post("/api/scenario/nominal")
    assert r_nom.status_code == 200

    res = client.post(
        "/api/sans/assessments",
        json={
            "mission_day": 191,
            "eye_tested": "BOTH",
            "wavy_lines_detected": True,
            "scotoma_cells": ["D4", "E5"],
            "near_acuity_shift": True,
            "notes": "Mild central grid waviness post-microgravity shift",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["sans_record"]["wavy_lines_detected"] is True
    st = body["state"]
    assert st["assessment"]["latest_sans"]["wavy_lines_detected"] is True
    eye_region = next(
        (r for r in st["assessment"]["marscare_body_regions"] if r["id"] == "eyes"),
        None,
    )
    assert eye_region is not None
    assert eye_region["status"] in ("WARNING", "CRITICAL")
    eva_advisories = " ".join(st["assessment"]["eva_readiness"]["advisory_factors"]).lower()
    assert "sans" in eva_advisories or "amsler" in eva_advisories


def test_medkit_adjustment_and_flight_surgeon_consult_draft(client):
    """Medical Kit tracking & Flight Surgeon draft omit private psych journals and never prescribe."""
    res_pq = client.post(
        "/api/psych-questionnaire",
        json={
            "mission_day": 192,
            "emotional_condition_rating": 4,
            "psychological_stress_rating": 7,
            "journal_reflection": "SUPER_SECRET_DIARY_TOKEN_99",
        },
    )
    assert res_pq.status_code == 200

    mk_list = client.get("/api/medkit")
    assert mk_list.status_code == 200
    items = mk_list.json()["medical_kit"]
    assert len(items) == 7
    locked = next(i for i in items if i["item_code"] == "MED-CMO-LOCKED")
    assert locked["cmo_auth_required"] is True

    o2_before = next(i for i in items if i["item_code"] == "MED-O2-PORT")["quantity"]
    adj = client.post(
        "/api/medkit/adjust",
        json={"item_code": "MED-O2-PORT", "quantity_delta": -1, "mark_inspected": True},
    )
    assert adj.status_code == 200
    assert adj.json()["item"]["quantity"] == o2_before - 1

    draft = client.post(
        "/api/consult/flight-surgeon-draft",
        json={
            "cmo_notes": "Request asynchronous Flight Surgeon review of orthostatic fluids.",
            "urgency": "WARNING",
            "include_sans": True,
        },
    )
    assert draft.status_code == 200
    draft_body = draft.json()
    preview = draft_body["markdown_preview"]
    assert "SUPER_SECRET_DIARY_TOKEN_99" not in preview
    assert "cmo" in preview.lower() or "flight surgeon" in preview.lower()
    assert "prescribe" not in draft_body["report"]["summary"].lower() or "never" in preview.lower()


def test_multi_crew_matrix_select_and_privacy_pin(client):
    """Multi-crew switcher, severity-sorted CMO matrix redaction, and SHA-256 Privacy PIN gates."""
    m_res = client.get("/api/crew/matrix")
    assert m_res.status_code == 200
    matrix = m_res.json()["crew_fleet_matrix"]
    crew_ids = {m["crew_id"] for m in matrix}
    assert crew_ids == {"ARES-IV-SUCHAI", "ARES-IV-VANCE", "ARES-IV-CHEN", "ARES-IV-OKAFOR"}
    assert all(m["private_reflections_redacted"] is True for m in matrix)

    sel = client.post("/api/crew/select", json={"crew_id": "ARES-IV-CHEN"})
    assert sel.status_code == 200
    assert sel.json()["active_crew_id"] == "ARES-IV-CHEN"
    assert sel.json()["astronaut"]["astronaut_id"] == "ARES-IV-CHEN"

    bad_pin = client.post(
        "/api/crew/unlock-reflections",
        json={"crew_id": "ARES-IV-CHEN", "pin": "0000"},
    )
    assert bad_pin.status_code == 403

    ok_pin = client.post(
        "/api/crew/unlock-reflections",
        json={"crew_id": "ARES-IV-CHEN", "pin": "2026"},
    )
    assert ok_pin.status_code == 200
    assert ok_pin.json()["unlocked"] is True

    upd = client.post(
        "/api/crew/pin",
        json={"crew_id": "ARES-IV-CHEN", "current_pin": "2026", "new_pin": "4321"},
    )
    assert upd.status_code == 200 and upd.json()["updated"] is True

    old_again = client.post(
        "/api/crew/unlock-reflections",
        json={"crew_id": "ARES-IV-CHEN", "pin": "2026"},
    )
    assert old_again.status_code == 403

    new_ok = client.post(
        "/api/crew/unlock-reflections",
        json={"crew_id": "ARES-IV-CHEN", "pin": "4321"},
    )
    assert new_ok.status_code == 200 and new_ok.json()["unlocked"] is True


def test_hw1_catalog_all_20_instruments_and_verified_urls(client):
    """Hardware integration: all 20 instruments across Categories A-F load with official NASA/CSA URLs."""
    res = client.get("/api/devices/catalog")
    assert res.status_code == 200
    body = res.json()
    catalog = body["catalog"]
    assert len(catalog) == 20
    codes = {d["code"] for d in catalog}
    expected_codes = {
        "A1", "A2", "A3", "A4",
        "B1", "B2", "B3", "B4",
        "C1", "C2", "C3", "C4",
        "D1", "D2",
        "E1", "E2",
        "F1", "F2", "F3", "F4",
    }
    assert codes == expected_codes

    allowed_domains = ("https://www.nasa.gov/", "https://science.nasa.gov/", "https://osdr.nasa.gov/", "https://nlsp.nasa.gov/", "https://www.asc-csa.gc.ca/")
    for dev in catalog:
        assert dev["research_references"], f"{dev['device_id']} missing references"
        for ref in dev["research_references"]:
            assert ref["url"].startswith(allowed_domains), f"Unverified URL in {dev['device_id']}: {ref['url']}"
        assert body["device_states"][dev["device_id"]]["connection_status"] == "not_connected"

    state_res = client.get("/api/state")
    assert state_res.status_code == 200
    assert len(state_res.json()["devices_catalog"]) == 20


def test_hw2_truthful_hardware_probe_and_simulation_lifecycle(client):
    """Hardware integration: failed physical probe never fakes Connected/NORMAL; simulation labels SYNTHETIC_DEMO."""
    probe = client.post("/api/devices/CSA_BIO_MONITOR/connect", json={"mode": "hardware"})
    assert probe.status_code == 200
    pbody = probe.json()
    assert pbody["connected"] is False
    assert pbody["connection_status"] in ("unavailable", "error")
    assert pbody["connection_status"] != "connected"

    sim = client.post("/api/devices/CSA_BIO_MONITOR/connect", json={"mode": "simulation"})
    assert sim.status_code == 200
    assert sim.json()["connection_status"] == "simulation"
    assert sim.json()["connected"] is False

    col = client.post("/api/devices/CSA_BIO_MONITOR/collect")
    assert col.status_code == 200
    staged = col.json()["staged_readings"]
    assert len(staged) >= 4
    assert all(r["data_source"] == "simulated" for r in staged)
    assert all(r["connection_status"] == "simulation" for r in staged)
    assert all(r["confirmed"] is False for r in staged)

    # Reject unconfirmed readings cleanly
    unconf = client.post(
        "/api/devices/CSA_BIO_MONITOR/confirm",
        json={"measurements": staged, "evaluate_health_assessment": True},
    )
    assert unconf.status_code == 422

    # Astronaut edits/confirms simulated HR reading cleanly
    confirmed_items = [{**r, "confirmed": True} for r in staged]
    conf_ok = client.post(
        "/api/devices/CSA_BIO_MONITOR/confirm",
        json={
            "measurements": confirmed_items,
            "evaluate_health_assessment": True,
            "notes": "Verified Bio-Monitor simulation packet",
        },
    )
    assert conf_ok.status_code == 200
    cbody = conf_ok.json()
    assert len(cbody["saved_measurements"]) == len(confirmed_items)
    assert cbody["state"]["latest_telemetry"]["provenance"] == "SYNTHETIC_DEMO"
    assert len(cbody["state"]["device_measurements"]) >= len(confirmed_items)

    disc = client.post("/api/devices/CSA_BIO_MONITOR/disconnect")
    assert disc.status_code == 200
    assert disc.json()["connection_status"] == "disconnected"


def test_hw3_import_unit_gy_vs_sv_protection_and_confirm(client):
    """Hardware integration: CSV/JSON import rejects Gy/Sv confusion and updates radiation hazard when valid."""
    bad_csv = "measurement_type,value,unit,recorded_at\nabsorbed_dose,0.52,mSv,2026-11-15T09:00:00Z"
    parse_bad = client.post(
        "/api/devices/CANS_SPECTROMETER/parse-import",
        json={"format": "csv", "filename": "bad_units.csv", "raw_text": bad_csv},
    )
    assert parse_bad.status_code == 200
    pb = parse_bad.json()
    assert pb["invalid_count"] == 1
    assert pb["parsed_readings"][0]["quality_status"] == "invalid_unit"
    assert "gy/mgy" in pb["parsed_readings"][0]["quality_note"].lower()

    # Attempting to confirm invalid_unit fails 422 without saving
    bad_confirm = client.post(
        "/api/devices/CANS_SPECTROMETER/confirm",
        json={"measurements": [{**pb["parsed_readings"][0], "confirmed": True}], "evaluate_health_assessment": True},
    )
    assert bad_confirm.status_code == 422

    # Valid Gy/Sv storm reading escalates Space Radiation hazard cleanly
    good_csv = (
        "measurement_type,value,unit,recorded_at\n"
        "absorbed_dose,2.80,mGy,2026-11-15T10:00:00Z\n"
        "equivalent_dose_rate,7.20,mSv/day,2026-11-15T10:00:00Z\n"
    )
    parse_ok = client.post(
        "/api/devices/CANS_SPECTROMETER/parse-import",
        json={"format": "csv", "filename": "cans_spe.csv", "raw_text": good_csv},
    )
    assert parse_ok.status_code == 200
    po = parse_ok.json()
    assert po["valid_count"] == 2 and po["invalid_count"] == 0

    confirmed = [{**r, "confirmed": True} for r in po["parsed_readings"]]
    save_ok = client.post(
        "/api/devices/CANS_SPECTROMETER/confirm",
        json={"measurements": confirmed, "evaluate_health_assessment": True},
    )
    assert save_ok.status_code == 200
    s_state = save_ok.json()["state"]
    assert s_state["latest_telemetry"]["provenance"] == "USER_ENTERED"
    assert s_state["latest_telemetry"]["absorbed_dose_mgy"] == 2.8
    assert s_state["latest_telemetry"]["equivalent_dose_rate_msv_day"] == 7.2
    assert s_state["assessment"]["hazard_statuses"]["Space Radiation"] == "CRITICAL"


def test_hw4_non_vital_kits_countermeasures_and_guided_exams(client):
    """Hardware integration: Thigh Cuffs, Veggie, Biosamples never fabricate vitals; IOP flags abnormality; assays separate."""
    before_state = client.get("/api/state").json()
    tele_count_before = len(before_state["telemetry_history"])

    for non_vital_id in ("THIGH_CUFFS_COUNTERMEASURE", "VEGGIE_SPACE_GARDENING", "SALIVA_BLOTTING_BOOKLET", "BIOLOGICAL_SAMPLING_KIT"):
        assert client.post(f"/api/devices/{non_vital_id}/connect", json={"mode": "simulation"}).status_code == 400
        assert client.post(f"/api/devices/{non_vital_id}/collect").status_code == 400

    # Countermeasure & wellbeing logs do not alter physiological vitals row count
    cuff_res = client.post(
        "/api/devices/THIGH_CUFFS_COUNTERMEASURE/examination",
        json={"mission_day": 184, "summary": "45-min thigh cuff session", "findings": {"duration_mins": 45}, "confirmed": True},
    )
    assert cuff_res.status_code == 200
    assert len(cuff_res.json()["state"]["telemetry_history"]) == tele_count_before

    # Biological sample collection & separate lab assay import
    bio_res = client.post(
        "/api/devices/BIOLOGICAL_SAMPLING_KIT/biosample",
        json={"sample_type": "Whole Blood", "mission_day": 184, "storage_location": "MELFI-A Tray 1", "notes": "Fasting draw"},
    )
    assert bio_res.status_code == 200
    sample_uid = bio_res.json()["biosample"]["sample_uid"]
    assert bio_res.json()["biosample"]["status"] == "COLLECTED_STORED"

    assay_res = client.post(
        f"/api/devices/biosamples/{sample_uid}/assay",
        json={
            "format": "json",
            "filename": "cytokines.json",
            "raw_text": '{"assays":[{"biomarker":"IL-6","value":2.1,"unit":"pg/mL"}]}',
        },
    )
    assert assay_res.status_code == 200
    assert assay_res.json()["biosample"]["status"] == "ASSAY_IMPORTED"
    assert assay_res.json()["biosample"]["assay_results"]["markers"][0]["biomarker"] == "IL-6"

    # Eye-pressure exam flags abnormal IOP (> 21 mmHg) & Ultrasound retains operator disclaimer
    iop_res = client.post(
        "/api/devices/OCULAR_TONOMETER_SANS/examination",
        json={"mission_day": 184, "summary": "Tonometry check", "findings": {"iop_od_mmhg": 24.0, "iop_os_mmhg": 18.0}, "confirmed": True},
    )
    assert iop_res.status_code == 200
    assert iop_res.json()["examination"]["abnormal_flag"] is True
    assert "21 mmHg" in iop_res.json()["examination"]["abnormal_reason"]

    us_res = client.post(
        "/api/devices/ULTRASOUND_VASCULAR/examination",
        json={
            "mission_day": 184,
            "summary": "Internal jugular vein view recorded",
            "findings": {"anatomical_window": "IJV"},
            "attachments": [{"filename": "ijv_scan.png", "mime_type": "image/png", "size_bytes": 1024}],
            "confirmed": True,
        },
    )
    assert us_res.status_code == 200
    assert "automated ultrasound diagnosis is not performed" in us_res.json()["examination"]["summary_note"].lower()


def test_donki_1_all_11_endpoints_normalization_and_secret_safety(client, monkeypatch):
    """DONKI: All 11 official NASA endpoints parse cleanly and raw NASA_API_KEY never leaks in API JSON."""
    import json
    import urllib.parse
    import donki_client

    secret_val = "TESTKEY_DO_NOT_LEAK_9999"
    cfg_res = client.post("/api/donki/config", json={"api_key": secret_val, "auto_advisory_in_eva": True})
    assert cfg_res.status_code == 200
    cfg_body = cfg_res.json()
    assert cfg_body["config"]["using_custom_key"] is True
    assert "TEST" in cfg_body["config"]["key_status"]
    assert "9999" in cfg_body["config"]["key_status"]
    assert secret_val not in json.dumps(cfg_body)

    called_urls = []
    mock_payloads = {
        "/DONKI/CME": [{
            "activityID": "2024-05-10T01:00:00-CME-001",
            "startTime": "2024-05-10T01:00:00Z",
            "sourceLocation": "S18W35",
            "note": "Halo CME associated with active region AR3664",
            "cmeAnalyses": [{"isMostAccurate": True, "speed": 1150, "halfAngle": 42, "type": "O"}],
            "linkedEvents": [{"activityID": "2024-05-10T00:50:00-FLR-001"}],
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/CME/31001/-1",
        }],
        "/DONKI/CMEAnalysis": [{
            "time21_5": "2024-05-10T04:15:00Z",
            "speed": 1220,
            "halfAngle": 45,
            "type": "O",
            "isMostAccurate": True,
            "associatedCMEID": "2024-05-10T01:00:00-CME-001",
            "catalog": "M2M_CATALOG",
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/CMEAnalysis/31002/-1",
        }],
        "/DONKI/GST": [{
            "gstID": "2024-05-11T02:00:00-GST-001",
            "startTime": "2024-05-11T02:00:00Z",
            "allKpIndex": [{"observedTime": "2024-05-11T03:00:00Z", "kpIndex": 8.0, "source": "NOAA"}],
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/GST/31003/-1",
        }],
        "/DONKI/IPS": [{
            "activityID": "2024-05-10T17:00:00-IPS-001",
            "eventTime": "2024-05-10T17:00:00Z",
            "location": "Earth",
            "catalog": "M2M_CATALOG",
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/IPS/31004/-1",
        }],
        "/DONKI/FLR": [{
            "flrID": "2024-05-10T00:50:00-FLR-001",
            "beginTime": "2024-05-10T00:40:00Z",
            "peakTime": "2024-05-10T00:55:00Z",
            "classType": "X1.8",
            "sourceLocation": "S18W35",
            "activeRegionNum": 3664,
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/FLR/31005/-1",
        }],
        "/DONKI/SEP": [{
            "sepID": "2024-05-10T02:30:00-SEP-001",
            "eventTime": "2024-05-10T02:30:00Z",
            "instruments": [{"displayName": "GOES-16 SEISS >10 MeV"}],
            "linkedEvents": [{"activityID": "2024-05-10T01:00:00-CME-001"}],
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/SEP/31006/-1",
        }],
        "/DONKI/MPC": [{
            "mpcID": "2024-05-11T01:10:00-MPC-001",
            "eventTime": "2024-05-11T01:10:00Z",
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/MPC/31007/-1",
        }],
        "/DONKI/RBE": [{
            "rbeID": "2024-05-11T12:00:00-RBE-001",
            "eventTime": "2024-05-11T12:00:00Z",
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/RBE/31008/-1",
        }],
        "/DONKI/HSS": [{
            "hssID": "2024-05-09T09:00:00-HSS-001",
            "eventTime": "2024-05-09T09:00:00Z",
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/HSS/31009/-1",
        }],
        "/DONKI/WSAEnlilSimulations": [{
            "simulationID": "M2M_20240510_01",
            "modelCompletionTime": "2024-05-10T05:00:00Z",
            "estimatedShockArrivalTime": "2024-05-12T18:00:00Z",
            "impactList": [{"isGlancingBlow": False, "location": "Mars", "arrivalTime": "2024-05-12T18:00:00Z"}],
            "link": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/WSAEnlil/31010/-1",
        }],
        "/DONKI/notifications": [{
            "messageType": "SEP",
            "messageID": "20240510-AL-001",
            "messageURL": "https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/Alert/20240510-AL-001/1",
            "messageIssueTime": "2024-05-10T02:45:00Z",
            "messageBody": "## Space Weather Research Center\nSEP proton watch issued for inner heliosphere.",
        }],
    }

    def fake_get(url: str, timeout_sec: float = 15.0):
        called_urls.append(url)
        parsed = urllib.parse.urlparse(url)
        assert f"api_key={secret_val}" in parsed.query
        return mock_payloads[parsed.path]

    monkeypatch.setattr(donki_client, "_http_get_json", fake_get)

    # Empty payload auto-defaults to last 30 UTC days across all 11 endpoints concurrently
    from datetime import datetime, timedelta, timezone
    expected_end = datetime.now(timezone.utc).date()
    expected_start = expected_end - timedelta(days=30)

    sync_res = client.post("/api/donki/sync", json={})
    assert sync_res.status_code == 200
    body = sync_res.json()
    assert len(called_urls) == 11
    assert body["sync_result"]["status"] == "SYNCED"
    assert body["sync_result"]["fetched_count"] == 11
    assert body["sync_result"]["sync_meta"]["last_window"] == {
        "start_date": expected_start.isoformat(),
        "end_date": expected_end.isoformat(),
    }

    raw_json = json.dumps(body)
    assert secret_val not in raw_json

    donki_state = client.get("/api/donki/state").json()
    assert secret_val not in json.dumps(donki_state)
    counts = donki_state["service_counts"]
    assert set(counts.keys()) == set(donki_client.ALL_DONKI_SERVICE_IDS)

    by_type = {ev["service_type"]: ev for ev in donki_state["events"]}
    assert by_type["GST"]["regime_scope"] == "EARTH_MAGNETOSPHERE"
    assert by_type["MPC"]["regime_scope"] == "EARTH_MAGNETOSPHERE"
    assert by_type["RBE"]["regime_scope"] == "EARTH_MAGNETOSPHERE"
    assert by_type["SEP"]["regime_scope"] == "HELIOSPHERIC_DEEP_SPACE"
    assert by_type["SEP"]["severity"] == "CRITICAL"
    assert by_type["FLR"]["severity"] == "CRITICAL"
    assert by_type["WSAEnlilSimulations"]["severity"] == "CRITICAL"


def test_donki_2_offline_blackout_http429_and_eva_advisory(client, monkeypatch):
    """DONKI: OFFLINE blocks polling while preserving SQLite cache; HTTP 429 handled cleanly; EVA advisory leaves dosimetry intact."""
    import io
    import urllib.error
    import urllib.parse
    import donki_client

    before_state = client.get("/api/state").json()
    base_mgy = before_state["latest_telemetry"]["absorbed_dose_mgy"]
    base_msv_day = before_state["latest_telemetry"]["equivalent_dose_rate_msv_day"]

    def fake_sep(url: str, timeout_sec: float = 15.0):
        return [{
            "sepID": "2026-11-15T01:00:00-SEP-TEST",
            "eventTime": "2026-11-15T01:00:00Z",
            "instruments": [{"displayName": "SOHO EPHIN"}],
            "link": "https://api.nasa.gov/DONKI/SEP",
        }]

    monkeypatch.setattr(donki_client, "_http_get_json", fake_sep)
    res_sep = client.post(
        "/api/donki/sync",
        json={"start_date": "2026-11-14", "end_date": "2026-11-15", "services": ["SEP"]},
    )
    assert res_sep.status_code == 200
    assert res_sep.json()["sync_result"]["status"] == "SYNCED"

    # Active SEP advisory surfaces in EVA readiness without overwriting personal dosimetry
    after_sep_state = res_sep.json()["state"]
    assert after_sep_state["latest_telemetry"]["absorbed_dose_mgy"] == base_mgy
    assert after_sep_state["latest_telemetry"]["equivalent_dose_rate_msv_day"] == base_msv_day
    eva_adv = " ".join(after_sep_state["assessment"]["eva_readiness"]["advisory_factors"])
    assert "DONKI SEP Cache" in eva_adv

    # OFFLINE blackout blocks external polling & auto-sync while preserving SQLite cache
    assert client.post("/api/comm/mode", json={"mode": "OFFLINE"}).status_code == 200
    assert donki_client.should_auto_sync() is False

    def forbid_http(*args, **kwargs):
        raise AssertionError("Outbound HTTP call must not occur while Earth Link is OFFLINE")

    monkeypatch.setattr(donki_client, "_http_get_json", forbid_http)
    offline_sync = client.post("/api/donki/sync", json={"services": ["CME", "SEP"]})
    assert offline_sync.status_code == 200
    assert offline_sync.json()["sync_result"]["status"] == "BLOCKED_OFFLINE"
    assert len(offline_sync.json()["donki_state"]["events"]) == 1

    # Reconnect and verify HTTP 429 rate-limit graceful partial handling
    assert client.post("/api/comm/mode", json={"mode": "CONNECTED"}).status_code == 200

    def partial_rate_limit(url: str, timeout_sec: float = 15.0):
        path = urllib.parse.urlparse(url).path
        if path == "/DONKI/FLR":
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO(b"rate limit"))
        return []

    monkeypatch.setattr(donki_client, "_http_get_json", partial_rate_limit)
    partial_res = client.post("/api/donki/sync", json={"services": ["CME", "FLR"]})
    assert partial_res.status_code == 200
    ps = partial_res.json()["sync_result"]
    assert ps["status"] == "PARTIAL"
    assert ps["sync_meta"]["service_statuses"]["FLR"]["status"] == "RATE_LIMITED"
    # Existing SEP cache survives failed/partial sync cleanly
    assert partial_res.json()["donki_state"]["service_counts"]["SEP"] == 1


def test_insight_mars_weather_normalization_gaps_offline_and_habitat_isolation(client, monkeypatch):
    """InSight: Per-Sol AT/HWS/PRE/WD parsing, missing-sensor gaps, OFFLINE blocking, and habitat isolation."""
    import json
    import urllib.parse
    import insight_client

    secret_val = "INSIGHT_SECRET_KEY_8888"
    assert client.post("/api/donki/config", json={"api_key": secret_val}).status_code == 200

    before_state = client.get("/api/state").json()
    base_cabin_kpa = before_state["latest_telemetry"]["cabin_pressure_kpa"]
    base_cabin_c = before_state["latest_telemetry"]["cabin_temp_c"]

    def fake_insight(url: str, timeout_sec: float = 10.0):
        parsed = urllib.parse.urlparse(url)
        assert parsed.path == "/insight_weather/"
        assert f"api_key={secret_val}" in parsed.query
        return {
            "sol_keys": ["680", "681"],
            "680": {
                "AT": {"av": -63.5, "mn": -95.2, "mx": -17.4, "ct": 170000},
                "PRE": {"av": 748.2, "mn": 720.1, "mx": 766.8, "ct": 880000},
                # Simulate NASA InSight power-saving missing HWS / WD sensors on Sol 680
                "Season": "fall",
                "Northern_season": "early winter",
                "Southern_season": "early summer",
                "Month_ordinal": 10,
                "First_UTC": "2020-10-24T18:00:00Z",
                "Last_UTC": "2020-10-25T18:39:00Z",
            },
            "681": {
                "AT": {"av": -62.3, "mn": -96.8, "mx": -15.9, "ct": 177556},
                "HWS": {"av": 7.2, "mn": 1.0, "mx": 22.4, "ct": 88628},
                "PRE": {"av": 750.5, "mn": 722.0, "mx": 768.7, "ct": 887776},
                "WD": {
                    "0": {"compass_degrees": 0.0, "compass_point": "N", "compass_right": 0.0, "compass_up": 1.0, "ct": 254},
                    "13": {"compass_degrees": 292.5, "compass_point": "WNW", "compass_right": -0.9238, "compass_up": 0.3826, "ct": 27816},
                    "most_common": {"compass_degrees": 292.5, "compass_point": "WNW", "ct": 27816},
                },
                "Season": "fall",
                "Northern_season": "early winter",
                "Southern_season": "early summer",
                "Month_ordinal": 10,
                "First_UTC": "2020-10-25T18:39:00Z",
                "Last_UTC": "2020-10-26T19:18:00Z",
            },
            "validity_checks": {
                "681": {
                    "AT": {"sol_hours_with_data": list(range(24)), "valid": True},
                    "HWS": {"sol_hours_with_data": list(range(24)), "valid": True},
                }
            },
        }

    monkeypatch.setattr(insight_client, "_http_get_insight_json", fake_insight)
    res = client.post("/api/insight/sync", json={"feedtype": "json", "version": "1.0"})
    assert res.status_code == 200
    body = res.json()
    assert secret_val not in json.dumps(body)
    assert body["sync_result"]["status"] == "SYNCED"
    assert body["sync_result"]["fetched_count"] == 2

    # Exterior Martian ~0.75 kPa / -62C never overwrites habitat interior cabin telemetry
    assert body["state"]["latest_telemetry"]["cabin_pressure_kpa"] == base_cabin_kpa
    assert body["state"]["latest_telemetry"]["cabin_temp_c"] == base_cabin_c

    ins = body["insight_state"]
    assert ins["summary"]["latest_sol_id"] == "681"
    assert ins["summary"]["latest_wind_compass"] == "WNW"
    sol_by_id = {s["sol_id"]: s for s in ins["sols"]}
    assert "HWS" in sol_by_id["680"]["missing_sensors"]
    assert "WD" in sol_by_id["680"]["missing_sensors"]
    assert sol_by_id["681"]["missing_sensors"] == []
    assert len(sol_by_id["681"]["wd"]["bins"]) == 2

    # Empty sol_keys (InSight data gap) returns EMPTY_GAP without wiping SQLite cache
    monkeypatch.setattr(insight_client, "_http_get_insight_json", lambda url, timeout_sec=10.0: {"sol_keys": []})
    gap_res = client.post("/api/insight/sync", json={})
    assert gap_res.status_code == 200
    assert gap_res.json()["sync_result"]["status"] == "EMPTY_GAP"
    assert gap_res.json()["insight_state"]["summary"]["sol_count"] == 2

    # OFFLINE blackout blocks outbound HTTP while serving SQLite cache cleanly
    assert client.post("/api/comm/mode", json={"mode": "OFFLINE"}).status_code == 200
    assert insight_client.should_auto_sync_insight() is False
    monkeypatch.setattr(
        insight_client,
        "_http_get_insight_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Must not poll InSight when OFFLINE")),
    )
    off_res = client.post("/api/insight/sync", json={})
    assert off_res.status_code == 200
    assert off_res.json()["sync_result"]["status"] == "BLOCKED_OFFLINE"
    assert client.get("/api/insight/state").json()["summary"]["sol_count"] == 2


