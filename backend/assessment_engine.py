"""
Integrated Astronaut Health Assessment Engine (Section 8) and Local Emergency Protocol Engine.
Integrates telemetry across all 5 NASA spaceflight hazards, compares against individual astronaut
baselines and historical trends, maps findings to anatomical regions for the Interactive Body Map,
and generates explainable NORMAL / WARNING / CRITICAL classifications with research citations.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from models import (
    AstronautBaseline,
    RadiationConfigLimits,
    EnvironmentalConfigLimits,
    RiskLevel,
    MissionPhase,
)
from knowledge_base import rag_engine


def _pct_delta(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return round(((current - baseline) / baseline) * 100.0, 1)


def _gravity_regime_label(grav_g: float) -> str:
    if grav_g <= 0.05:
        return "microgravity (0.00g)"
    if grav_g < 0.8:
        return f"Mars partial gravity ({grav_g:.2f}g)"
    return f"Earth gravity ({grav_g:.2f}g)"


def evaluate_integrated_health(
    latest: Dict[str, Any],
    history: List[Dict[str, Any]],
    baseline: AstronautBaseline,
    rad_limits: RadiationConfigLimits,
    env_limits: EnvironmentalConfigLimits,
    comm_state: Dict[str, Any],
    latest_psych: Optional[Dict[str, Any]] = None,
    skip_rag: bool = False,
) -> Dict[str, Any]:
    """
    Central assessment engine integrating all five hazard modules, personal baseline comparisons,
    historical trends, mission phase, environmental conditions, and red-flag cardiopulmonary symptoms.
    """
    findings: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    active_alerts: List[Dict[str, Any]] = []

    # 1. Baseline Comparisons
    baseline_comparisons = [
        {
            "metric": "Heart Rate",
            "key": "heart_rate_bpm",
            "current": latest["heart_rate_bpm"],
            "baseline": baseline.baseline_hr_bpm,
            "unit": "bpm",
            "delta": round(latest["heart_rate_bpm"] - baseline.baseline_hr_bpm, 1),
            "delta_pct": _pct_delta(latest["heart_rate_bpm"], baseline.baseline_hr_bpm),
            "hazard": "Gravity Fields",
        },
        {
            "metric": "Systolic BP",
            "key": "systolic_bp_mmhg",
            "current": latest["systolic_bp_mmhg"],
            "baseline": baseline.baseline_systolic_mmhg,
            "unit": "mmHg",
            "delta": round(latest["systolic_bp_mmhg"] - baseline.baseline_systolic_mmhg, 1),
            "delta_pct": _pct_delta(latest["systolic_bp_mmhg"], baseline.baseline_systolic_mmhg),
            "hazard": "Gravity Fields",
        },
        {
            "metric": "Diastolic BP",
            "key": "diastolic_bp_mmhg",
            "current": latest["diastolic_bp_mmhg"],
            "baseline": baseline.baseline_diastolic_mmhg,
            "unit": "mmHg",
            "delta": round(latest["diastolic_bp_mmhg"] - baseline.baseline_diastolic_mmhg, 1),
            "delta_pct": _pct_delta(latest["diastolic_bp_mmhg"], baseline.baseline_diastolic_mmhg),
            "hazard": "Gravity Fields",
        },
        {
            "metric": "Oxygen Saturation (SpO2)",
            "key": "spo2_pct",
            "current": latest["spo2_pct"],
            "baseline": baseline.baseline_spo2_pct,
            "unit": "%",
            "delta": round(latest["spo2_pct"] - baseline.baseline_spo2_pct, 1),
            "delta_pct": _pct_delta(latest["spo2_pct"], baseline.baseline_spo2_pct),
            "hazard": "Hostile and Closed Environments",
        },
        {
            "metric": "Body Temperature",
            "key": "body_temp_c",
            "current": latest["body_temp_c"],
            "baseline": baseline.baseline_temp_c,
            "unit": "°C",
            "delta": round(latest["body_temp_c"] - baseline.baseline_temp_c, 2),
            "delta_pct": _pct_delta(latest["body_temp_c"], baseline.baseline_temp_c),
            "hazard": "Hostile and Closed Environments",
        },
        {
            "metric": "Sleep Duration",
            "key": "sleep_duration_hrs",
            "current": latest["sleep_duration_hrs"],
            "baseline": baseline.baseline_sleep_hrs,
            "unit": "hrs",
            "delta": round(latest["sleep_duration_hrs"] - baseline.baseline_sleep_hrs, 1),
            "delta_pct": _pct_delta(latest["sleep_duration_hrs"], baseline.baseline_sleep_hrs),
            "hazard": "Isolation and Confinement",
        },
        {
            "metric": "Mood Score",
            "key": "mood_score",
            "current": latest["mood_score"],
            "baseline": baseline.baseline_mood_score,
            "unit": "/10",
            "delta": round(latest["mood_score"] - baseline.baseline_mood_score, 1),
            "delta_pct": _pct_delta(latest["mood_score"], baseline.baseline_mood_score),
            "hazard": "Isolation and Confinement",
        },
        {
            "metric": "Psychological Stress",
            "key": "stress_level",
            "current": latest["stress_level"],
            "baseline": baseline.baseline_stress_score,
            "unit": "/10",
            "delta": round(latest["stress_level"] - baseline.baseline_stress_score, 1),
            "delta_pct": _pct_delta(latest["stress_level"], baseline.baseline_stress_score),
            "hazard": "Isolation and Confinement",
        },
        {
            "metric": "Muscle Strength Index",
            "key": "muscle_strength_idx",
            "current": latest["muscle_strength_idx"],
            "baseline": baseline.baseline_muscle_strength_idx,
            "unit": "idx",
            "delta": round(latest["muscle_strength_idx"] - baseline.baseline_muscle_strength_idx, 1),
            "delta_pct": _pct_delta(latest["muscle_strength_idx"], baseline.baseline_muscle_strength_idx),
            "hazard": "Gravity Fields",
        },
        {
            "metric": "Sensorimotor Balance",
            "key": "balance_score",
            "current": latest["balance_score"],
            "baseline": baseline.baseline_balance_score,
            "unit": "/100",
            "delta": round(latest["balance_score"] - baseline.baseline_balance_score, 1),
            "delta_pct": _pct_delta(latest["balance_score"], baseline.baseline_balance_score),
            "hazard": "Gravity Fields",
        },
    ]

    # Historical window (last 4 records)
    recent_window = history[-4:] if len(history) >= 4 else history

    # =========================================================================
    # MODULE 1 ASSESSMENT: SPACE RADIATION
    # =========================================================================
    rad_status = RiskLevel.NORMAL
    eq_rate = float(latest["equivalent_dose_rate_msv_day"])
    abs_dose = float(latest["absorbed_dose_mgy"])
    cum_dose = float(latest["cumulative_effective_dose_msv"])
    rad_event = latest.get("radiation_event_type", "GCR_BACKGROUND")

    if eq_rate >= rad_limits.daily_equivalent_crit_msv or cum_dose >= rad_limits.cumulative_mission_limit_msv:
        rad_status = RiskLevel.CRITICAL
        msg = (
            f"Acute radiation threshold exceeded: Equivalent dose rate is {eq_rate:.2f} mSv/day "
            f"(absorptive physical dose {abs_dose:.2f} mGy; configured critical limit {rad_limits.daily_equivalent_crit_msv:.1f} mSv/day). "
            f"Event source: {rad_event}."
        )
        findings.append({
            "hazard": "Space Radiation",
            "severity": "CRITICAL",
            "title": "Acute Solar Particle Event (SPE) / Dose Limit Exceedance",
            "detail": msg,
            "rule_type": rad_limits.rule_classification,
            "ref_doc": "NASA-HRP-RAD-01",
        })
        active_alerts.append({
            "id": "ALERT-RAD-CRIT",
            "hazard": "Space Radiation",
            "severity": "CRITICAL",
            "message": msg,
            "action_required": "Enter high-mass storm shelter immediately; suspend surface EVA; log active biodosimetry.",
        })
        recommendations.append({
            "hazard": "Space Radiation",
            "priority": "IMMEDIATE",
            "action": "Relocate to habitat polyethylene/water-wall storm shelter (ALARA SPE protocol).",
            "rationale": "High-flux Solar Particle Event protons increase acute radiation sickness risk and cumulative effective dose (mSv).",
            "procedure_code": "PROC-RAD-SPE-01",
            "citation": "NASA-HRP-RAD-01 / CSA-RAD-2026-01",
        })
    elif eq_rate >= rad_limits.daily_equivalent_warn_msv or cum_dose >= rad_limits.cumulative_mission_warn_msv:
        rad_status = RiskLevel.WARNING
        msg = (
            f"Elevated radiation exposure: Equivalent dose rate {eq_rate:.2f} mSv/day "
            f"(absorbed dose {abs_dose:.2f} mGy), cumulative mission effective dose {cum_dose:.1f} mSv "
            f"(warning threshold {rad_limits.daily_equivalent_warn_msv:.1f} mSv/day)."
        )
        findings.append({
            "hazard": "Space Radiation",
            "severity": "WARNING",
            "title": "Elevated Dosimetric Rate Above Routine GCR Background",
            "detail": msg,
            "rule_type": rad_limits.rule_classification,
            "ref_doc": "CSA-RAD-2026-01",
        })
        active_alerts.append({
            "id": "ALERT-RAD-WARN",
            "hazard": "Space Radiation",
            "severity": "WARNING",
            "message": msg,
            "action_required": "Review shielding posture and defer non-essential external surface activity during solar flux peak.",
        })
        recommendations.append({
            "hazard": "Space Radiation",
            "priority": "HIGH",
            "action": "Verify personal active dosimeter placement, minimize time in lightly shielded airlock modules, and reschedule non-urgent EVA.",
            "rationale": "Distinguish physical absorbed dose (mGy) from biologically weighted equivalent dose (mSv) driven by HZE GCR and solar proton enhancements.",
            "procedure_code": "PROC-RAD-ALARA-02",
            "citation": "NASA-HRP-RAD-01 / CSA-RAD-2026-01",
        })
    else:
        recommendations.append({
            "hazard": "Space Radiation",
            "priority": "ROUTINE",
            "action": "Continue nominal active dosimetry logging and sleeping-quarters polyethylene shielding utilization.",
            "rationale": f"Current rate ({eq_rate:.2f} mSv/day; {abs_dose:.2f} mGy) reflects expected Galactic Cosmic Ray (GCR) background.",
            "procedure_code": "PROC-RAD-NOM-01",
            "citation": "NASA-HRP-RAD-01",
        })

    # =========================================================================
    # MODULE 2 ASSESSMENT: ISOLATION AND CONFINEMENT
    # =========================================================================
    iso_status = RiskLevel.NORMAL
    sleep_hrs = float(latest["sleep_duration_hrs"])
    sleep_quality = float(latest.get("sleep_quality_pct", 85.0))
    stress = float(latest["stress_level"])
    mood = float(latest["mood_score"])
    fatigue = float(latest["fatigue_level"])
    workload = float(latest["workload_score"])
    social_score = float(latest.get("social_interaction_score", 8.0))
    sleep_irreg = int(latest.get("sleep_irregularities", 0))

    # Factor in any newer Behavioral & Sleep Check-In without mutating physiological telemetry
    psych_isolation_flag = bool(latest.get("feeling_isolated", False))
    if latest_psych and int(latest_psych.get("mission_day", 0)) >= int(latest.get("mission_day", 0)):
        mood = min(mood, float(latest_psych.get("emotional_condition_rating", mood)))
        stress = max(stress, float(latest_psych.get("psychological_stress_rating", stress)))
        fatigue = max(fatigue, float(latest_psych.get("fatigue_rating", fatigue)))
        workload = max(workload, float(latest_psych.get("concentration_workload_rating", workload)))
        if int(latest_psych.get("sleep_difficulty_rating", 0)) >= 7:
            sleep_irreg = max(sleep_irreg, 3)
            sleep_quality = min(sleep_quality, 50.0)
        if int(latest_psych.get("isolation_feeling_rating", 0)) >= 6:
            psych_isolation_flag = True
            social_score = min(social_score, 4.0)

    avg_recent_sleep = (
        sum(float(r["sleep_duration_hrs"]) for r in recent_window) / len(recent_window)
        if recent_window else sleep_hrs
    )

    persistent_short_sleep = (
        (baseline.baseline_sleep_hrs - avg_recent_sleep) >= 1.0
        and sleep_hrs < (baseline.baseline_sleep_hrs - 0.3)
    )

    if sleep_hrs < 4.5 or (sleep_hrs <= 4.5 and (stress >= 8.0 or fatigue >= 7.5)) or stress >= 8.5 or mood <= 3.0 or fatigue >= 8.5:
        iso_status = RiskLevel.CRITICAL
        msg = (
            f"Severe behavioural/circadian strain indicator: Sleep {sleep_hrs:.1f} hrs "
            f"(quality {sleep_quality:.0f}%, baseline {baseline.baseline_sleep_hrs:.1f} hrs), "
            f"Stress {stress:.1f}/10, Mood {mood:.1f}/10, Fatigue {fatigue:.1f}/10, "
            f"Social interaction {social_score:.1f}/10."
        )
        findings.append({
            "hazard": "Isolation and Confinement",
            "severity": "CRITICAL",
            "title": "Acute Sleep Deprivation & High Cognitive/Stress Load",
            "detail": msg + " Note: Non-diagnostic operational alert; does not constitute a psychiatric diagnosis.",
            "rule_type": "MISSION_CONFIGURED_BASELINE_RULE",
            "ref_doc": "NASA-HRP-ISO-01",
        })
        active_alerts.append({
            "id": "ALERT-ISO-CRIT",
            "hazard": "Isolation and Confinement",
            "severity": "CRITICAL",
            "message": msg,
            "action_required": "Mandatory safety stand-down from high-risk EVA/robotics operations; initiate protected 9-hour sleep recovery window and supportive CMO peer check-in.",
        })
        recommendations.append({
            "hazard": "Isolation and Confinement",
            "priority": "IMMEDIATE",
            "action": "Enforce operational workload stand-down, protected circadian sleep recovery block, and private supportive check-in with Crew Medical Officer.",
            "rationale": "Severe sleep restriction (≤4.5 hrs with high fatigue/stress) markedly elevates operational error risk during confined missions.",
            "procedure_code": "PROC-BEHAV-REST-01",
            "citation": "NASA-HRP-ISO-01",
        })
    elif (
        (baseline.baseline_sleep_hrs - sleep_hrs) >= 1.2
        or persistent_short_sleep
        or sleep_quality < 62.0
        or stress >= baseline.baseline_stress_score + 2.2
        or mood <= baseline.baseline_mood_score - 1.8
        or fatigue >= 6.5
        or social_score < 5.0
        or sleep_irreg >= 3
        or psych_isolation_flag
    ):
        iso_status = RiskLevel.WARNING
        msg = (
            f"Persistent circadian/workload drift vs. personal baseline: Sleep {sleep_hrs:.1f} hrs "
            f"(quality {sleep_quality:.0f}%, baseline {baseline.baseline_sleep_hrs:.1f} hrs, 4-sol avg {avg_recent_sleep:.1f} hrs), "
            f"Stress {stress:.1f}/10 (baseline {baseline.baseline_stress_score:.1f}), "
            f"Mood {mood:.1f}/10, Workload {workload:.1f}/10, Social interaction {social_score:.1f}/10."
        )
        findings.append({
            "hazard": "Isolation and Confinement",
            "severity": "WARNING",
            "title": "Circadian Sleep Reduction & Elevated Operational Stress Trend",
            "detail": msg + " Non-diagnostic behavioral risk indicator.",
            "rule_type": "MISSION_CONFIGURED_BASELINE_RULE",
            "ref_doc": "NASA-HRP-ISO-01",
        })
        active_alerts.append({
            "id": "ALERT-ISO-WARN",
            "hazard": "Isolation and Confinement",
            "severity": "WARNING",
            "message": msg,
            "action_required": "Apply blue-enriched morning light protocol, reduce evening screen/task load, and schedule structured crew decompression.",
        })
        recommendations.append({
            "hazard": "Isolation and Confinement",
            "priority": "HIGH",
            "action": "Execute 30-min high-melanopic blue-enriched light exposure at wake, dim habitat lighting 90 mins pre-sleep, reflective journaling, and shared crew meal.",
            "rationale": "Counteracts Martian sol / habitat circadian misalignment and confinement fatigue without pathologizing normal mission stress.",
            "procedure_code": "PROC-ISO-CIRC-02",
            "citation": "NASA-HRP-ISO-01",
        })
    else:
        recommendations.append({
            "hazard": "Isolation and Confinement",
            "priority": "ROUTINE",
            "action": "Maintain consistent sleep/wake schedule, daily crew social check-ins, and personal journaling routine.",
            "rationale": "Sleep duration, quality, mood, and stress remain within personal baseline bands.",
            "procedure_code": "PROC-ISO-NOM-01",
            "citation": "NASA-HRP-ISO-01",
        })

    # =========================================================================
    # MODULE 3 ASSESSMENT: DISTANCE FROM EARTH & AUTONOMOUS MEDICAL SUPPORT
    # =========================================================================
    dist_status = RiskLevel.NORMAL
    comm_mode = comm_state.get("earth_comm_status", "NOMINAL_DELAYED")
    delay_min = float(comm_state.get("one_way_delay_minutes", 14.2))
    pending_count = int(comm_state.get("pending_reports_count", 0))

    if comm_mode == "CONJUNCTION_BLACKOUT" or comm_state.get("offline_mode_forced", False):
        dist_status = RiskLevel.WARNING
        msg = (
            f"Earth telemetry link in {comm_mode} (One-way light time: {delay_min:.1f} min; "
            f"{pending_count} health reports queued in local store-and-forward buffer). "
            "Onboard TARSCARE AI operating in 100% autonomous offline mode."
        )
        findings.append({
            "hazard": "Distance from Earth",
            "severity": "WARNING",
            "title": "Autonomous Deep-Space Operations Mode (Store-and-Forward Active)",
            "detail": msg,
            "rule_type": "MISSION_CONFIGURED_PROTOTYPE_RULE",
            "ref_doc": "NASA-HRP-DIST-01",
        })
        recommendations.append({
            "hazard": "Distance from Earth",
            "priority": "HIGH",
            "action": "Rely on local onboard RAG medical library and autonomous CMO checklists; queue daily telemetry packets for post-blackout synchronization.",
            "rationale": f"With {delay_min:.1f} min one-way delay ({delay_min*2:.1f} min round-trip) or blackout, acute clinical decisions cannot wait for Earth Flight Surgeons.",
            "procedure_code": "PROC-DIST-AUTO-01",
            "citation": "NASA-HRP-DIST-01 / NASA-CSTARS-MED-01",
        })
    else:
        recommendations.append({
            "hazard": "Distance from Earth",
            "priority": "ROUTINE",
            "action": f"Continue store-and-forward telemetry packet synchronization (current one-way light delay: {delay_min:.1f} min).",
            "rationale": "Local SQLite database and offline RAG knowledge base verified ready for autonomous fallback.",
            "procedure_code": "PROC-DIST-SYNC-01",
            "citation": "NASA-HRP-DIST-01",
        })

    # =========================================================================
    # MODULE 4 ASSESSMENT: GRAVITY FIELDS, CARDIOPULMONARY & ADAPTATION
    # =========================================================================
    grav_status = RiskLevel.NORMAL
    hr = float(latest["heart_rate_bpm"])
    sys_bp = float(latest["systolic_bp_mmhg"])
    dia_bp = float(latest["diastolic_bp_mmhg"])
    spo2 = float(latest["spo2_pct"])
    resp_rate = float(latest.get("respiratory_rate_bpm", 16.0))
    body_temp = float(latest["body_temp_c"])
    co2_mmhg = float(latest["co2_mmhg"])
    dizz = int(latest.get("dizziness_severity", 0))
    faint = bool(latest.get("faintness_presyncope", False))
    strength = float(latest["muscle_strength_idx"])
    balance = float(latest["balance_score"])
    adherence = float(latest["exercise_adherence_pct"])
    ex_perf = float(latest.get("exercise_performance_pct", 100.0))
    sans_vis = bool(latest.get("visual_disturbance_sans", False))
    phase = latest.get("mission_phase", MissionPhase.MARS_SURFACE.value)
    grav_g = float(latest.get("gravity_g", 0.38))
    grav_label = _gravity_regime_label(grav_g)

    reported_symptoms = [str(s).strip() for s in (latest.get("reported_symptoms") or []) if str(s).strip()]
    symptoms_lower = " | ".join(reported_symptoms).lower()
    chest_discomfort = bool(latest.get("chest_discomfort", False)) or ("chest" in symptoms_lower)
    palpitations = bool(latest.get("palpitations", False)) or ("palpitation" in symptoms_lower)
    shortness_of_breath = bool(latest.get("shortness_of_breath", False)) or ("shortness of breath" in symptoms_lower) or ("dyspnea" in symptoms_lower)

    hr_delta = hr - baseline.baseline_hr_bpm
    sys_delta = sys_bp - baseline.baseline_systolic_mmhg
    dia_delta = dia_bp - baseline.baseline_diastolic_mmhg

    cardiopulmonary_red_flag = (
        chest_discomfort
        or (palpitations and (hr_delta >= 22.0 or dizz >= 1 or shortness_of_breath or hr >= 110.0))
        or (shortness_of_breath and (spo2 < 95.0 or resp_rate >= 22.0 or hr >= 110.0))
    )

    if (
        cardiopulmonary_red_flag
        or faint
        or dizz >= 3
        or hr_delta >= 32.0
        or hr >= 120.0
        or sys_bp <= 88.0
    ):
        grav_status = RiskLevel.CRITICAL
        sym_flags = [
            name for flag, name in [
                (chest_discomfort, "chest discomfort"),
                (palpitations, "palpitations"),
                (shortness_of_breath, "shortness of breath"),
                (faint, "faintness/presyncope"),
            ] if flag
        ]
        msg = (
            f"{'Cardiopulmonary red-flag triage' if cardiopulmonary_red_flag else 'Acute orthostatic / hemodynamic instability'} "
            f"in {phase} ({grav_label}): HR {hr:.0f} bpm ({hr_delta:+.0f} vs. baseline {baseline.baseline_hr_bpm:.0f}), "
            f"BP {sys_bp:.0f}/{dia_bp:.0f} mmHg ({sys_delta:+.0f} systolic vs. baseline), "
            f"SpO2 {spo2:.1f}%, RR {resp_rate:.0f}/min, "
            f"red-flag symptoms=[{', '.join(sym_flags) if sym_flags else 'None'}], dizziness severity={dizz}/3."
        )
        findings.append({
            "hazard": "Gravity Fields",
            "severity": "CRITICAL",
            "title": (
                "Cardiopulmonary Red-Flag Symptoms & Autonomic/Tachycardic Excursion"
                if cardiopulmonary_red_flag
                else "Acute Orthostatic Intolerance / Cardiovascular Instability"
            ),
            "detail": (
                msg
                + " Autonomous cardiac diagnostic instrumentation (12-lead ECG interpretation / troponin assay) is not built into TARSCARE; "
                "immediate Crew Medical Officer (CMO) hands-on evaluation and onboard ECG strip capture are required."
            ),
            "rule_type": "MISSION_CONFIGURED_BASELINE_RULE",
            "ref_doc": "CSA-CARDIO-CCISS-01",
        })
        active_alerts.append({
            "id": "ALERT-GRAV-CRIT",
            "hazard": "Gravity Fields",
            "severity": "CRITICAL",
            "message": msg,
            "action_required": (
                "STOP ALL EXERTION IMMEDIATELY. Alert Crew Medical Officer & Mission Commander, acquire 12-lead/3-lead ECG + repeated vitals, "
                "open Autonomous Emergency Triage Checklist, and hold all exercise."
                if cardiopulmonary_red_flag
                else "Assume supine/Trendelenburg posture immediately; administer oral isotonic fluid-loading protocol; don lower-body compression garment; cancel EVA and hold exercise."
            ),
        })
        recommendations.append({
            "hazard": "Gravity Fields",
            "priority": "IMMEDIATE",
            "action": (
                "Stop exertion immediately, rest in comfortable semi-Fowler or supported posture, alert onboard CMO & Commander, capture onboard ECG + BP/SpO2 every 2 mins, and open Emergency Checklist (Cardiopulmonary Triage)."
                if cardiopulmonary_red_flag
                else "Execute CCISS/CARDIOBREATH orthostatic rescue protocol: supine posture with leg elevation, oral salt/fluid loading, continuous ECG/BP monitoring."
            ),
            "rationale": (
                "Chest discomfort, palpitations, unexplained tachycardia, or dyspnea in deep space require immediate in-person CMO evaluation and ECG acquisition; automated diagnosis is not reliable."
                if cardiopulmonary_red_flag
                else "Transition between gravity regimes unmasks plasma volume reduction and blunted arterial baroreflex control."
            ),
            "procedure_code": "PROC-CARDIO-REDFLAG-01" if cardiopulmonary_red_flag else "PROC-GRAV-ORTHO-01",
            "citation": "NASA-HRP-GRAV-01 / CSA-CARDIO-CCISS-01 / NASA-CSTARS-MED-01",
        })
    elif (
        dizz >= 1
        or palpitations
        or shortness_of_breath
        or hr_delta >= 12.0
        or sys_delta <= -10.0
        or sys_delta >= 18.0
        or dia_delta >= 12.0
        or strength <= baseline.baseline_muscle_strength_idx - 7.0
        or balance <= baseline.baseline_balance_score - 10.0
        or adherence < 80.0
        or ex_perf <= 80.0
        or sans_vis
    ):
        grav_status = RiskLevel.WARNING
        msg = (
            f"Gravity adaptation & sensorimotor/cardiovascular drift in {phase} ({grav_label}): "
            f"HR {hr:.0f} bpm ({hr_delta:+.0f} vs. baseline), BP {sys_bp:.0f}/{dia_bp:.0f} mmHg ({sys_delta:+.0f}/{dia_delta:+.0f}), "
            f"Exercise Performance {ex_perf:.0f}%, Balance {balance:.0f}/100 (baseline {baseline.baseline_balance_score:.0f}), "
            f"Muscle Strength Index {strength:.1f} (baseline {baseline.baseline_muscle_strength_idx:.0f}), "
            f"Dizziness {dizz}/3, Visual/SANS symptoms={sans_vis}."
        )
        findings.append({
            "hazard": "Gravity Fields",
            "severity": "WARNING",
            "title": "Cardiovascular, Sensorimotor, or Musculoskeletal Adaptation Shift",
            "detail": msg,
            "rule_type": "MISSION_CONFIGURED_BASELINE_RULE",
            "ref_doc": "NASA-HRP-GRAV-01",
        })
        active_alerts.append({
            "id": "ALERT-GRAV-WARN",
            "hazard": "Gravity Fields",
            "severity": "WARNING",
            "message": msg,
            "action_required": "Perform seated/supervised orthostatic & neurovestibular check, avoid unmonitored high-strain exertion if dizzy or symptomatic, and perform fundus/visual acuity check if SANS flagged.",
        })
        gravity_drill = (
            "proprioceptive balance and gait drills appropriate for surface gravity"
            if grav_g >= 0.1
            else "harnessed ARED resistive loading and tethered sensorimotor stabilization in microgravity (0.00g)"
        )
        recommendations.append({
            "hazard": "Gravity Fields",
            "priority": "HIGH",
            "action": (
                f"Maintain supervised ARED resistive exercise (squats/heel raises/deadlifts if free of dizziness/chest pain), incorporate {gravity_drill}, and use pre-EVA fluid loading."
                if dizz == 0 and not palpitations and not shortness_of_breath
                else "Suspend high-strain EVA/exertion while dizziness, palpitations, or dyspnea persist; perform seated hydration, repeat supine/standing vitals, and check CMO neurovestibular protocol."
            ),
            "rationale": f"Mitigates lower-limb deconditioning, neurovestibular ataxia, and cardiovascular drift across {grav_label}.",
            "procedure_code": "PROC-GRAV-ARED-02" if (dizz == 0 and not palpitations and not shortness_of_breath) else "PROC-GRAV-SYM-HOLD",
            "citation": "NASA-HRP-GRAV-01 / CSA-CARDIO-CCISS-01",
        })
    else:
        recommendations.append({
            "hazard": "Gravity Fields",
            "priority": "ROUTINE",
            "action": "Continue scheduled 2-hour daily countermeasure block (ARED resistance + cycle/treadmill aerobic + balance drills).",
            "rationale": f"Cardiovascular and musculoskeletal indicators remain well adapted to {phase} ({grav_label}).",
            "procedure_code": "PROC-GRAV-NOM-01",
            "citation": "NASA-HRP-GRAV-01",
        })

    # =========================================================================
    # MODULE 5 ASSESSMENT: HOSTILE AND CLOSED ENVIRONMENTS
    # =========================================================================
    env_status = RiskLevel.NORMAL
    co2_ppm = float(latest["co2_ppm"])
    o2_pct = float(latest["oxygen_pct"])
    cabin_temp = float(latest["cabin_temp_c"])
    cabin_press = float(latest["cabin_pressure_kpa"])
    humidity = float(latest["humidity_pct"])
    aqi = float(latest["air_quality_index"])
    resp_sym = list(latest.get("respiratory_symptoms") or [])
    inf_sym = list(latest.get("infection_symptoms") or [])
    if shortness_of_breath and "Shortness of breath" not in resp_sym:
        resp_sym.append("Shortness of breath")
    for s in reported_symptoms:
        s_low = s.lower()
        if any(tok in s_low for tok in ("cough", "wheez", "throat", "congestion", "sinus")) and s not in resp_sym:
            resp_sym.append(s)
        elif any(tok in s_low for tok in ("fever", "chills", "rash")) and s not in inf_sym:
            inf_sym.append(s)

    if (
        co2_mmhg >= env_limits.co2_crit_mmhg
        or o2_pct < env_limits.o2_min_pct
        or aqi >= env_limits.aqi_crit
        or body_temp >= 38.3
        or spo2 < 93.0
        or resp_rate >= 26.0
    ):
        env_status = RiskLevel.CRITICAL
        msg = (
            f"Critical habitat environment or physiological excursion: Cabin CO2 {co2_mmhg:.2f} mmHg ({co2_ppm:.0f} ppm; "
            f"limit {env_limits.co2_crit_mmhg:.1f} mmHg), O2 {o2_pct:.1f}%, Cabin Temp {cabin_temp:.1f}°C, AQI {aqi:.0f}, "
            f"Crew Body Temp {body_temp:.1f}°C, SpO2 {spo2:.1f}%, RR {resp_rate:.0f} breaths/min."
        )
        findings.append({
            "hazard": "Hostile and Closed Environments",
            "severity": "CRITICAL",
            "title": "Critical ECLSS Atmospheric Excursion or Febrile/Hypoxic/Tachypneic Finding",
            "detail": msg + " Note: Environmental correlation does not automatically diagnose an infection.",
            "rule_type": env_limits.rule_classification,
            "ref_doc": "NASA-HRP-ENV-01",
        })
        active_alerts.append({
            "id": "ALERT-ENV-CRIT",
            "hazard": "Hostile and Closed Environments",
            "severity": "CRITICAL",
            "message": msg,
            "action_required": "Switch ECLSS CO2 scrubber to backup bed immediately; activate high-flow HEPA circulation; don portable breathing O2 mask if SpO2 < 94% or CO2 > 5 mmHg; initiate CMO exam.",
        })
        recommendations.append({
            "hazard": "Hostile and Closed Environments",
            "priority": "IMMEDIATE",
            "action": "Inspect ECLSS CDRA/amine CO2 scrubber & O2 supply loop, boost cabin fan ventilation to break CO2 pockets, assess portable O2 need, and perform immediate CMO exam.",
            "rationale": "Elevated spacecraft CO2 (>4.5 mmHg) impairs cognition and respiratory drive, while hypoxia (SpO2 <93%), tachypnea (RR >=26), or fever require immediate medical workup.",
            "procedure_code": "PROC-ENV-ECLSS-01",
            "citation": "NASA-HRP-ENV-01",
        })
    elif (
        co2_mmhg >= env_limits.co2_warn_mmhg
        or aqi >= env_limits.aqi_warn
        or humidity < env_limits.humidity_min_pct
        or humidity > env_limits.humidity_max_pct
        or cabin_temp < env_limits.cabin_temp_min_c
        or cabin_temp > env_limits.cabin_temp_max_c
        or resp_rate >= 22.0
        or shortness_of_breath
        or (body_temp - baseline.baseline_temp_c) >= 0.8
        or (baseline.baseline_spo2_pct - spo2) >= 2.5
        or len(resp_sym) > 0
        or len(inf_sym) > 0
    ):
        env_status = RiskLevel.WARNING
        msg = (
            f"Habitat environment / crew symptom correlation noted: Cabin CO2 {co2_mmhg:.2f} mmHg ({co2_ppm:.0f} ppm), "
            f"Cabin Temp {cabin_temp:.1f}°C, Humidity {humidity:.0f}%, AQI {aqi:.0f}, "
            f"Body Temp {body_temp:.1f}°C, SpO2 {spo2:.1f}%, RR {resp_rate:.0f}/min, "
            f"Respiratory symptoms={resp_sym or ['None']}, General symptoms={inf_sym or ['None']}."
        )
        findings.append({
            "hazard": "Hostile and Closed Environments",
            "severity": "WARNING",
            "title": "Elevated Cabin CO2 / Thermal / Particulate Load or Respiratory Symptom Correlation",
            "detail": msg + " Important: Correlating environmental readings with symptoms does not automatically diagnose an infection.",
            "rule_type": env_limits.rule_classification,
            "ref_doc": "NASA-HRP-ENV-01",
        })
        active_alerts.append({
            "id": "ALERT-ENV-WARN",
            "hazard": "Hostile and Closed Environments",
            "severity": "WARNING",
            "message": msg,
            "action_required": "Increase sleeping-quarters air circulation fan speed, inspect HEPA particulate filter for Martian regolith dust, verify thermal control loop, and repeat SpO2/RR/temp in 4 hours.",
        })
        recommendations.append({
            "hazard": "Hostile and Closed Environments",
            "priority": "HIGH",
            "action": "Verify local air duct flow (eliminate stagnant CO2 pockets), stabilize cabin temperature/humidity, clean airlock HEPA pre-filters, and maintain mucosal hydration.",
            "rationale": "Moderate CO2 accumulation (>=3.0 mmHg), thermal excursion, and low humidity/dust in closed habitats correlate with headache, fatigue, and upper-airway irritation.",
            "procedure_code": "PROC-ENV-VENT-02",
            "citation": "NASA-HRP-ENV-01",
        })
    else:
        recommendations.append({
            "hazard": "Hostile and Closed Environments",
            "priority": "ROUTINE",
            "action": "Continue routine ECLSS atmospheric logging, potable water microbial checks, and airlock dust mitigation.",
            "rationale": f"Cabin CO2 ({co2_mmhg:.2f} mmHg), O2 ({o2_pct:.1f}%), temp ({cabin_temp:.1f}°C), pressure ({cabin_press:.1f} kPa), and crew vitals are nominal.",
            "procedure_code": "PROC-ENV-NOM-01",
            "citation": "NASA-HRP-ENV-01",
        })

    # Overall Risk Level aggregation
    hazard_statuses = {
        "Space Radiation": rad_status.value,
        "Isolation and Confinement": iso_status.value,
        "Distance from Earth": dist_status.value,
        "Gravity Fields": grav_status.value,
        "Hostile and Closed Environments": env_status.value,
    }

    if RiskLevel.CRITICAL.value in hazard_statuses.values():
        overall_status = RiskLevel.CRITICAL
    elif RiskLevel.WARNING.value in hazard_statuses.values():
        overall_status = RiskLevel.WARNING
    else:
        overall_status = RiskLevel.NORMAL

    # FIX 2: Deterministic safety gating (exercise contraindication & priority sorting)
    exercise_contraindicated = (
        overall_status == RiskLevel.CRITICAL
        or chest_discomfort
        or palpitations
        or shortness_of_breath
        or faint
        or dizz >= 2
        or hr >= 115.0
        or hr_delta >= 30.0
        or sys_bp <= 90.0
        or spo2 < 94.0
        or resp_rate >= 24.0
        or body_temp >= 38.0
        or eq_rate >= rad_limits.daily_equivalent_crit_msv
        or co2_mmhg >= env_limits.co2_crit_mmhg
    )

    if exercise_contraindicated:
        recommendations = [
            r for r in recommendations
            if r.get("procedure_code") not in ("PROC-GRAV-NOM-01", "PROC-GRAV-ARED-02")
        ]
        if not any(r.get("procedure_code") in ("PROC-CARDIO-REDFLAG-01", "PROC-GRAV-ORTHO-01", "PROC-GRAV-SYM-HOLD", "PROC-GRAV-REST-HOLD") for r in recommendations):
            recommendations.append({
                "hazard": "Gravity Fields",
                "priority": "IMMEDIATE" if overall_status == RiskLevel.CRITICAL else "HIGH",
                "action": "CONTRAINDICATED / HOLD EXERCISE: Suspend scheduled ARED resistive and aerobic exercise until acute physiological vitals, cardiopulmonary symptoms, or hazard alerts stabilize under CMO review.",
                "rationale": "Routine or strenuous physical countermeasures are medically contraindicated during active critical instability, red-flag cardiopulmonary symptoms, acute hypoxia, or SPE storm shelter events.",
                "procedure_code": "PROC-GRAV-REST-HOLD",
                "citation": "NASA-CSTARS-MED-01 / NASA-HRP-GRAV-01",
            })

    if overall_status == RiskLevel.CRITICAL:
        # Never allow routine radiation logging or routine housekeeping recs to appear alongside an acute medical/hazard emergency
        recommendations = [r for r in recommendations if r.get("priority") != "ROUTINE"]

    priority_rank = {"IMMEDIATE": 0, "HIGH": 1, "DEFERRED": 2, "ROUTINE": 3}
    severity_rank = {"CRITICAL": 0, "WARNING": 1, "NORMAL": 2}
    recommendations.sort(key=lambda r: priority_rank.get(str(r.get("priority", "ROUTINE")).upper(), 9))
    findings.sort(key=lambda f: severity_rank.get(str(f.get("severity", "NORMAL")).upper(), 9))
    active_alerts.sort(key=lambda a: severity_rank.get(str(a.get("severity", "NORMAL")).upper(), 9))

    auto_emergency_recommended = overall_status == RiskLevel.CRITICAL or cardiopulmonary_red_flag
    recommended_emergency_hazard = None
    if auto_emergency_recommended:
        if cardiopulmonary_red_flag:
            recommended_emergency_hazard = "Cardiopulmonary & Chest Triage"
        elif rad_status == RiskLevel.CRITICAL:
            recommended_emergency_hazard = "Space Radiation"
        elif env_status == RiskLevel.CRITICAL:
            recommended_emergency_hazard = "Hostile and Closed Environments"
        elif grav_status == RiskLevel.CRITICAL:
            recommended_emergency_hazard = "Gravity Fields"
        elif iso_status == RiskLevel.CRITICAL:
            recommended_emergency_hazard = "Isolation and Confinement"
        else:
            recommended_emergency_hazard = "Primary Medical Triage"

    protocol_gap_notice = None
    if auto_emergency_recommended:
        protocol_gap_notice = (
            "Capability boundary: TARSCARE does not integrate continuous 12-lead ECG waveform interpretation, cardiac biomarker blood assays "
            "(troponin/D-dimer), or autonomous arrhythmia diagnosis. In-person Crew Medical Officer (CMO) examination and onboard medical kit equipment are mandatory."
        )

    # =========================================================================
    # ANATOMICAL BODY MAP REGIONS (SCREEN 2)
    # =========================================================================
    body_regions = [
        {
            "region_id": "brain_head",
            "label": "Brain, CNS & Circadian System",
            "status": (
                "CRITICAL" if (iso_status == RiskLevel.CRITICAL or rad_status == RiskLevel.CRITICAL)
                else "WARNING" if (iso_status == RiskLevel.WARNING or co2_mmhg >= env_limits.co2_warn_mmhg)
                else "NORMAL"
            ),
            "hazards": ["Isolation and Confinement", "Space Radiation", "Hostile and Closed Environments"],
            "metrics": [
                {"name": "Sleep Duration", "value": f"{sleep_hrs:.1f} hrs", "baseline": f"{baseline.baseline_sleep_hrs:.1f} hrs"},
                {"name": "Stress / Mood", "value": f"{stress:.1f}/10 · {mood:.1f}/10", "baseline": f"{baseline.baseline_stress_score:.1f} · {baseline.baseline_mood_score:.1f}"},
                {"name": "Cabin CO2 Partial Pressure", "value": f"{co2_mmhg:.2f} mmHg", "baseline": "< 3.0 mmHg"},
                {"name": "Equivalent Dose Rate", "value": f"{eq_rate:.2f} mSv/day", "baseline": "0.65 mSv/day (GCR ref)"},
            ],
            "summary": (
                "Monitors circadian alignment, sleep architecture, cognitive workload, CO2-associated headache risk, "
                "and HZE/proton CNS radiation exposure."
            ),
            "guidance": "Use morning blue-enriched light exposure, ensure sleeping-bunk airflow to prevent CO2 pockets, and protect 8-hour sleep blocks.",
            "citation": "NASA-HRP-ISO-01 / NASA-HRP-ENV-01 / NASA-HRP-RAD-01",
        },
        {
            "region_id": "eyes",
            "label": "Eyes & Optic Nerve (SANS)",
            "status": "WARNING" if (sans_vis or co2_mmhg >= 3.2) else "NORMAL",
            "hazards": ["Gravity Fields", "Hostile and Closed Environments", "Space Radiation"],
            "metrics": [
                {"name": "SANS Visual Disturbance", "value": "Reported" if sans_vis else "None", "baseline": "None"},
                {"name": "Gravity Regime", "value": f"{grav_g}g ({phase})", "baseline": "1.0g Earth"},
                {"name": "Cabin CO2 (SANS cofactor)", "value": f"{co2_mmhg:.2f} mmHg", "baseline": "< 3.0 mmHg"},
            ],
            "summary": (
                "Tracks Spaceflight-Associated Neuro-ocular Syndrome (SANS) driven by cephalad fluid shifts in microgravity "
                "and elevated cabin CO2, plus radiation cataract exposure."
            ),
            "guidance": "Perform scheduled onboard optical coherence tomography (OCT) / visual acuity checks and keep cabin CO2 below 3.0 mmHg.",
            "citation": "NASA-HRP-GRAV-01 / NASA-HRP-RAD-01",
        },
        {
            "region_id": "heart",
            "label": "Cardiovascular & Autonomic System",
            "status": (
                "CRITICAL" if (cardiopulmonary_red_flag or faint or hr_delta >= 30 or hr >= 120 or sys_bp <= 88)
                else "WARNING" if (palpitations or hr_delta >= 12 or sys_delta <= -10 or sys_delta >= 18 or dia_delta >= 12 or dizz >= 1)
                else "NORMAL"
            ),
            "hazards": ["Gravity Fields", "Space Radiation"],
            "metrics": [
                {"name": "Heart Rate", "value": f"{hr:.0f} bpm", "baseline": f"{baseline.baseline_hr_bpm:.0f} bpm ({hr_delta:+.0f})"},
                {"name": "Blood Pressure", "value": f"{sys_bp:.0f}/{dia_bp:.0f} mmHg", "baseline": f"{baseline.baseline_systolic_mmhg:.0f}/{baseline.baseline_diastolic_mmhg:.0f} mmHg"},
                {"name": "Chest Discomfort / Palpitations", "value": ", ".join([x for x, f in [("Chest discomfort", chest_discomfort), ("Palpitations", palpitations)] if f]) or "None", "baseline": "None"},
                {"name": "Orthostatic Dizziness / Presyncope", "value": f"Level {dizz}/3 · Faint: {'Yes' if faint else 'No'}", "baseline": "0/3 · No"},
            ],
            "summary": (
                f"Evaluates arterial baroreflex sensitivity, cardiopulmonary red-flag symptoms, and orthostatic adaptation across {grav_label} (CCISS / CARDIOBREATH), "
                "comparing HR and BP deviation against personal baseline."
            ),
            "guidance": (
                "STOP EXERTION immediately; notify onboard CMO & Commander, capture onboard 12-lead/3-lead ECG + BP/SpO2, and launch Cardiopulmonary Triage Checklist."
                if cardiopulmonary_red_flag
                else "Execute supine Trendelenburg leg elevation, oral isotonic fluids, continuous vitals, and hold exercise until CMO clearance."
                if exercise_contraindicated
                else "Perform pre-EVA isotonic fluid loading, wear lower-body compression garments during gravity transitions, and monitor standing BP."
            ),
            "citation": "CSA-CARDIO-CCISS-01 / NASA-HRP-GRAV-01",
        },
        {
            "region_id": "lungs",
            "label": "Respiratory & Pulmonary System",
            "status": (
                "CRITICAL" if (spo2 < 93.0 or o2_pct < 19.5 or co2_mmhg >= 4.5 or resp_rate >= 26.0 or (shortness_of_breath and spo2 < 95.0))
                else "WARNING" if (spo2 < 96.0 or resp_rate >= 22.0 or shortness_of_breath or len(resp_sym) > 0 or aqi >= 50.0 or humidity < 30.0)
                else "NORMAL"
            ),
            "hazards": ["Hostile and Closed Environments"],
            "metrics": [
                {"name": "SpO2 / Respiratory Rate", "value": f"{spo2:.1f}% · {resp_rate:.0f} breaths/min", "baseline": f"{baseline.baseline_spo2_pct:.1f}% · {getattr(baseline, 'baseline_resp_rate_bpm', 16.0):.0f}/min"},
                {"name": "Cabin O2 / Pressure", "value": f"{o2_pct:.1f}% · {cabin_press:.1f} kPa", "baseline": "21.0% · 70.3 kPa"},
                {"name": "Air Quality Index (AQI)", "value": f"{aqi:.0f}", "baseline": "< 35"},
                {"name": "Respiratory Symptoms", "value": ", ".join(resp_sym) if resp_sym else "None", "baseline": "None"},
            ],
            "summary": (
                "Monitors pulmonary oxygenation, respiratory rate, dust/particulate airway irritation, cabin humidity, "
                "and closed-loop ECLSS gas composition."
            ),
            "guidance": (
                "Initiate immediate CMO respiratory assessment, check cabin O2/CO2/HEPA loop, use supplemental O2 per CMO kit if SpO2 < 94%, and hold exercise."
                if (spo2 < 94.0 or resp_rate >= 24.0 or shortness_of_breath)
                else "Inspect airlock HEPA filtration after surface EVAs, maintain cabin humidity between 35–60%, and correlate symptoms before assuming infection."
            ),
            "citation": "NASA-HRP-ENV-01",
        },
        {
            "region_id": "muscles",
            "label": "Skeletal Muscle & Motor Conditioning",
            "status": "WARNING" if (strength <= baseline.baseline_muscle_strength_idx - 7.0 or adherence < 80.0 or ex_perf <= 80.0) else "NORMAL",
            "hazards": ["Gravity Fields"],
            "metrics": [
                {"name": "Muscle Strength Index", "value": f"{strength:.1f}", "baseline": f"{baseline.baseline_muscle_strength_idx:.0f}"},
                {"name": "Exercise Performance", "value": f"{ex_perf:.0f}%", "baseline": "100%"},
                {"name": "Countermeasure Adherence", "value": f"{adherence:.0f}%", "baseline": "≥ 90%"},
                {"name": "Physical Activity", "value": f"{latest['physical_activity_mins']:.0f} min/sol", "baseline": "110 min/sol"},
            ],
            "summary": (
                "Tracks antigravity muscle conditioning (soleus, quadriceps, paraspinal) and adherence to resistive "
                "and aerobic countermeasure prescriptions."
            ),
            "guidance": (
                "EXERCISE CONTRAINDICATED: Hold resistive and aerobic exercise until acute CRITICAL physiological or radiation/ECLSS alerts resolve under CMO review."
                if exercise_contraindicated
                else "Complete supervised ARED resistive loading blocks and interval cycle/treadmill sessions when free of dizziness or chest discomfort."
            ),
            "citation": "NASA-HRP-GRAV-01",
        },
        {
            "region_id": "bones",
            "label": "Skeletal & Bone Mineral System",
            "status": "WARNING" if (adherence < 82.0 or strength < 90.0) else "NORMAL",
            "hazards": ["Gravity Fields", "Space Radiation"],
            "metrics": [
                {"name": "Resistive Loading Adherence", "value": f"{adherence:.0f}%", "baseline": "≥ 90%"},
                {"name": "Cumulative Radiation (Marrow)", "value": f"{cum_dose:.1f} mSv", "baseline": f"< {rad_limits.cumulative_mission_warn_msv:.0f} mSv"},
                {"name": "Discomfort Score", "value": f"{latest['musculoskeletal_discomfort']}/3", "baseline": "0/3"},
            ],
            "summary": (
                "Evaluates axial and femoral bone unloading risk across microgravity (0g) and partial gravity alongside hematopoietic bone marrow "
                "radiation dose tracking."
            ),
            "guidance": (
                "Defer axial resistive loading during acute medical stand-down or storm shelter alerts; resume only after CMO clearance."
                if exercise_contraindicated
                else "Prioritize high-load axial resistance exercises (squats, deadlifts) and adequate Vitamin D / calcium intake."
            ),
            "citation": "NASA-HRP-GRAV-01 / NASA-HRP-RAD-01",
        },
        {
            "region_id": "vestibular_nervous",
            "label": "Vestibular & Sensorimotor System",
            "status": "CRITICAL" if dizz >= 3 else "WARNING" if (balance <= baseline.baseline_balance_score - 10.0 or dizz >= 1 or latest.get("spatial_disorientation", False)) else "NORMAL",
            "hazards": ["Gravity Fields"],
            "metrics": [
                {"name": "Balance Score", "value": f"{balance:.0f}/100", "baseline": f"{baseline.baseline_balance_score:.0f}/100"},
                {"name": "Coordination Score", "value": f"{latest['coordination_score']:.0f}/100", "baseline": "94/100"},
                {"name": "Spatial Disorientation", "value": "Present" if latest.get("spatial_disorientation") else "None", "baseline": "None"},
            ],
            "summary": (
                "Monitors otolith-canal sensory reweighting and postural stability during transitions between "
                "microgravity, Mars partial gravity, and Earth return."
            ),
            "guidance": (
                "Avoid unassisted standing/EVA while vestibular or cardiopulmonary red flags are active; remain seated/supine with CMO support."
                if exercise_contraindicated
                else "Perform graduated head-movement and proprioceptive balance exercises prior to autonomous surface locomotion."
            ),
            "citation": "NASA-HRP-GRAV-01",
        },
    ]

    # Retrieve RAG explanation for the active findings (skippable during context enrichment)
    if skip_rag:
        rag_summary = None
    else:
        query_terms = [f["title"] for f in findings] or ["nominal spaceflight health baseline countermeasure"]
        rag_summary = rag_engine.answer_question(
            question=" ".join(query_terms),
            astronaut_context={
                "mission_phase": phase,
                "overall_status": overall_status.value,
                "allow_llm": False,
            },
        )

    from database import fetch_system_state
    from marscare_enhancer import build_marscare_extensions
    active_comm = comm_state or fetch_system_state("comm_state") or {}
    baseline_dict = baseline if isinstance(baseline, dict) else (baseline.model_dump() if hasattr(baseline, "model_dump") else {})
    result = {
        "overall_status": overall_status.value,
        "mission_day": latest["mission_day"],
        "mission_phase": phase,
        "gravity_g": grav_g,
        "provenance": latest.get("provenance", "SYNTHETIC_DEMO"),
        "rule_disclaimer": (
            "Assessments compare longitudinal telemetry against the astronaut's individual pre-flight and early-transit baseline "
            "combined with mission-configured prototype guardrails. Avoid arbitrary thresholds or assuming that ordinary Earth-based "
            "clinical reference ranges automatically represent safe operating limits for astronauts in microgravity or partial gravity. "
            "Not clinically validated for medical diagnosis."
        ),
        "exercise_contraindicated": exercise_contraindicated,
        "auto_emergency_recommended": auto_emergency_recommended,
        "recommended_emergency_hazard": recommended_emergency_hazard,
        "protocol_gap_notice": protocol_gap_notice,
        "hazard_statuses": hazard_statuses,
        "baseline_comparisons": baseline_comparisons,
        "findings": findings,
        "recommendations": recommendations,
        "active_alerts": active_alerts,
        "body_regions": body_regions,
        "rag_analysis": rag_summary,
    }
    result.update(build_marscare_extensions(latest, history, baseline_dict, active_comm, result))
    return result


def generate_local_emergency_protocol(
    trigger_hazard: str,
    severity: str,
    reported_symptoms: List[str],
    vital_signs_summary: str,
    mission_phase: str,
    comm_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministic, zero-latency local emergency escalation workflow (Module 3D).
    Operates 100% locally without waiting for Earth communication or external LLM APIs.
    """
    hazard_key = (trigger_hazard or "Primary Medical Triage").lower()
    sym_joined = " ".join(reported_symptoms or []).lower()
    clean_vitals = (vital_signs_summary or "").strip() or (
        "Vital signs summary not pre-populated — measure HR, BP, SpO2, respiratory rate, and temperature using onboard CMO hardware immediately."
    )

    if any(k in hazard_key for k in ("cardiopulm", "chest", "palpitation", "cardiac")) or any(
        k in sym_joined for k in ("chest", "palpitation")
    ):
        protocol_id = "EMG-CMO-CARDIOPULM-01"
        protocol_title = "Autonomous Cardiopulmonary Red-Flag & Chest Discomfort Triage Protocol"
        immediate_steps = [
            "1. STOP EXERTION & REST POSITION: Immediately cease all physical activity, EVA, or exercise; rest in semi-Fowler's or comfortable supported posture.",
            "2. SERIAL VITALS & ONBOARD ECG ACQUISITION: Measure bilateral blood pressure, SpO2, respiratory rate, tympanic temp, and capture a 3-lead/12-lead ECG strip every 2–5 minutes.",
            "3. ONBOARD CMO & COMMANDER ALERT: Summon Crew Medical Officer (CMO) and Mission Commander; open the onboard Medical Operations Kit and locate emergency cardiac/respiratory checklist.",
            "4. ENVIRONMENTAL & HYPOXIA RULE-OUT: Verify cabin O2 (%), CO2 (mmHg), and pressure (kPa); administer supplemental oxygen per CMO medical-kit procedure only if SpO2 < 94%. Never auto-dose prescription cardiac drugs from software alone.",
            "5. CAPABILITY GAP & STORE-AND-FORWARD PACKET: Prototype software cannot interpret ECG rhythms or run serum cardiac biomarkers (troponin/D-dimer). Queue Priority-1 Cardiopulmonary & ECG Packet for delayed Earth Flight Surgeon review.",
        ]
        citation = "CSA-CARDIO-CCISS-01 / NASA-CSTARS-MED-01"
        protocol_gap_notice = (
            "TARSCARE has NO autonomous 12-lead ECG waveform analyzer, stethoscope audio classifier, or blood troponin/D-dimer assay. "
            "Human Crew Medical Officer physical exam and onboard medical-kit checklist are required."
        )
    elif "rad" in hazard_key:
        protocol_id = "EMG-RAD-SPE-SHELTER-01"
        protocol_title = "Autonomous Solar Particle Event (SPE) & High-Dose Radiation Escalation"
        immediate_steps = [
            "1. IMMEDIATE SHELTERING: Relocate all crew to habitat high-mass Storm Shelter (water-wall / polyethylene core) within < 5 minutes; hold all exercise/EVA.",
            "2. TERMINATE EVA: Abort any ongoing or planned Extravehicular Activity; verify airlock inner hatch seal.",
            "3. DOSIMETRY VERIFICATION: Cross-check personal active dosimeter (mGy absorbed & mSv equivalent rate) against static area tissue-equivalent proportional counter (TEPC).",
            "4. CMO ALERT & HEMATOLOGY LOG: Notify Crew Medical Officer; record prodromal nausea, fatigue, or headache and schedule baseline + 6-hour capillary leukocyte/lymphocyte count using onboard analyzer.",
            "5. STORE-AND-FORWARD PACKET: Queue Priority-1 Radiation Incident Packet for Earth Flight Surgeons & Space Radiation Analysis Group (SRAG).",
        ]
        citation = "NASA-HRP-RAD-01 / CSA-RAD-2026-01"
        protocol_gap_notice = (
            "TARSCARE tracks dosimeter readings and crew symptom logs but does not directly control spacecraft bulk-shielding doors or run onboard hematology assays; verify TEPC hardware and CMO lab kit directly."
        )
    elif "grav" in hazard_key or "cardio" in hazard_key or "ortho" in hazard_key:
        protocol_id = "EMG-GRAV-ORTHO-SYNC-02"
        protocol_title = "Autonomous Orthostatic Presyncope & Cardiovascular Instability Protocol"
        immediate_steps = [
            "1. POSTURAL RESCUE: Stop all exertion; place astronaut in supine position with lower extremities elevated 30 degrees (Trendelenburg posture).",
            "2. AIRWAY & CONTINUOUS VITALS: Summon Crew Medical Officer; attach local 3-lead ECG, cuff blood pressure (every 2 mins), and pulse oximeter.",
            "3. FLUID & COMPRESSION COUNTERMEASURE: Administer oral isotonic electrolyte bolus (500 mL) if alert and swallowing safely; engage lower-body gradient compression garment.",
            "4. NEUROVESTIBULAR & SANS CHECK: With CMO assistance, assess pupil reactivity, chest symptoms, visual fields, and focal neurological status.",
            "5. STORE-AND-FORWARD PACKET: Queue Priority-1 Cardiovascular Telemetry Strip for delayed Earth Flight Surgeon review.",
        ]
        citation = "CSA-CARDIO-CCISS-01 / NASA-HRP-GRAV-01"
        protocol_gap_notice = (
            "Requires hands-on CMO verification of orthostatic vital signs, ECG rhythm, and hydration tolerance; TARSCARE cannot evaluate structural cardiac pathology."
        )
    elif "env" in hazard_key or "co2" in hazard_key or "resp" in hazard_key:
        protocol_id = "EMG-ENV-ECLSS-ATMOS-03"
        protocol_title = "Autonomous Habitat Atmospheric Excursion & Respiratory Triage Protocol"
        immediate_steps = [
            "1. BREATHING SOURCE ISOLATION: If local CO2 > 4.5 mmHg or SpO2 < 94% or toxic VOC suspected, don portable O2 breathing mask and activate high-flow cabin circulation fans.",
            "2. ECLSS SCRUBBER SWITCHOVER: Transition Carbon Dioxide Removal Assembly (CDRA / amine bed) to secondary redundant channel and inspect HEPA particulate filters.",
            "3. CMO EXAM & CLINICAL VITALS: Summon Crew Medical Officer & medical kit; measure SpO2, respiratory rate, blood pressure, and tympanic body temperature every 15 minutes.",
            "4. ENVIRONMENTAL CORRELATION: Compare crew symptoms across all habitat modules before assuming infectious etiology.",
            "5. STORE-AND-FORWARD PACKET: Queue Priority-1 ECLSS + Crew Medical Triage Packet for Earth synchronization.",
        ]
        citation = "NASA-HRP-ENV-01 / NASA-CSTARS-MED-01"
        protocol_gap_notice = (
            "Environmental sensor correlation cannot diagnose pulmonary infection, pneumothorax, or pulmonary embolism; in-person CMO auscultation and SpO2/ECLSS verification are required."
        )
    elif "iso" in hazard_key or "psych" in hazard_key or "sleep" in hazard_key:
        protocol_id = "EMG-ISO-CREW-SAFE-04"
        protocol_title = "Autonomous Acute Fatigue & Behavioural Safety Stand-Down Protocol"
        immediate_steps = [
            "1. OPERATIONAL STAND-DOWN: Immediately pause high-criticality tasks (EVA, robotics, propulsion maneuvers) with Mission Commander concurrence.",
            "2. CMO PRIVATE CONSULTATION: Conduct supportive, non-judgmental Crew Medical Officer / Commander private peer check-in and open onboard behavioral support guide.",
            "3. PROTECTED SLEEP RECOVERY: Configure crew quarters for uninterrupted 9-hour dark/quiet sleep window with optimal CO2 airflow (< 2.5 mmHg).",
            "4. CIRCADIAN RESET: Schedule high-melanopic blue light block upon waking and redistribute crew workload for 48 hours.",
            "5. STORE-AND-FORWARD PACKET: Log confidential behavioural readiness summary for delayed Flight Surgeon transmission (non-diagnostic operational log).",
        ]
        citation = "NASA-HRP-ISO-01 / NASA-CSTARS-MED-01"
        protocol_gap_notice = (
            "TARSCARE does not perform psychiatric diagnosis or crisis clinical counseling; confidential CMO human support and Earth behavioral health consultation are essential."
        )
    else:
        protocol_id = "EMG-CSTARS-GEN-00"
        protocol_title = "Autonomous Deep-Space Crew Medical Officer (CMO) Primary Triage Protocol"
        immediate_steps = [
            "1. PRIMARY SURVEY (MARCH/ABCDE): Cease exertion; verify airway, breathing (SpO2 & respiratory rate), circulation (HR/BP vs. personal baseline), and neurological status.",
            "2. ONBOARD CMO & MEDICAL KIT CONTACT: Notify Crew Medical Officer and Mission Commander immediately; open onboard Medical Operations Kit checklist.",
            "3. ENVIRONMENTAL SAFETY CHECK: Confirm cabin pressure, O2, CO2, temperature, and radiation dosimetry are within safe limits.",
            "4. STABILIZE & ONBOARD REFERENCE: Rest in safe habitat module with continuous local telemetry recording and offline RAG procedure lookup.",
            "5. STORE-AND-FORWARD PACKET: Package vital signs and assessment snapshot into Priority-1 queue for Earth synchronization.",
        ]
        citation = "NASA-CSTARS-MED-01 / NASA-HRP-DIST-01"
        protocol_gap_notice = (
            "General triage checklist only; physical examination by the onboard Crew Medical Officer and hardware diagnostics are required for definitive clinical care."
        )

    return {
        "protocol_id": protocol_id,
        "protocol_title": protocol_title,
        "execution_mode": "LOCAL_DETERMINISTIC_ZERO_LATENCY",
        "earth_comm_status": comm_state.get("earth_comm_status", "NOMINAL_DELAYED"),
        "one_way_delay_minutes": comm_state.get("one_way_delay_minutes", 14.2),
        "round_trip_delay_minutes": round(float(comm_state.get("one_way_delay_minutes", 14.2)) * 2.0, 1),
        "severity": severity,
        "trigger_hazard": trigger_hazard,
        "mission_phase": mission_phase,
        "reported_symptoms": reported_symptoms,
        "vital_signs_summary": clean_vitals,
        "immediate_steps": immediate_steps,
        "supporting_citation": citation,
        "protocol_gap_notice": protocol_gap_notice,
        "safety_disclaimer": (
            "Executed autonomously onboard without waiting for Earth telemetry link. "
            "Follow onboard Crew Medical Officer checklist; prototype decision support only — not validated medical diagnosis."
        ),
    }

