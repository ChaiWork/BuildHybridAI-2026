"""
MarsCare AI Assessment & Companion Shaping Layer.
Builds the 3-question Health Glance, 7 Section-4 Interactive Human Body regions with 7-day trends,
the 4-section Spaceflight Hazard modules, structured assessment explanation, and 4-tier Health Guidance.
"""

from __future__ import annotations
from typing import Any, Dict, List
from mission_ops import recommendation_sort_key


def normalize_comm_mode(comm_state: Dict[str, Any]) -> Dict[str, Any]:
    raw = str(comm_state.get("earth_comm_status", "NOMINAL_DELAYED")).upper()
    forced = bool(comm_state.get("offline_mode_forced", False))
    if forced or "BLACKOUT" in raw or "OFFLINE" in raw:
        mode = "OFFLINE"
        label = "Offline"
        summary = "Solar conjunction or local isolation — all health checks and guidance run 100% autonomously onboard."
    elif "DIRECT" in raw or "CONNECTED" in raw or float(comm_state.get("one_way_delay_minutes", 14.2)) <= 0.1:
        mode = "CONNECTED"
        label = "Connected"
        summary = "Low-latency Earth ground link active; local assessments sync automatically."
    else:
        mode = "DELAYED"
        label = "Delayed"
        delay = comm_state.get("one_way_delay_minutes", 14.2)
        summary = f"Earth link delayed ({delay} min one-way); onboard assessment operates independently with queued sync."
    return {
        "mode": mode,
        "label": label,
        "summary": summary,
    }


def _provenance_label(raw: str) -> str:
    r = str(raw or "").upper()
    if "USER" in r:
        return "User-Entered Data"
    if "REAL" in r:
        return "Real Research Data"
    return "Simulated Data"


def _grav_label(grav_g: float) -> str:
    if grav_g <= 0.05:
        return "microgravity (0.00g)"
    if grav_g < 0.8:
        return f"partial gravity ({grav_g:.2f}g)"
    return f"Earth gravity ({grav_g:.2f}g)"


def build_marscare_extensions(
    latest: Dict[str, Any],
    history: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    comm_state: Dict[str, Any],
    base_assessment: Dict[str, Any],
) -> Dict[str, Any]:
    recent_7 = history[-7:] if len(history) >= 7 else history
    hazard_statuses = base_assessment.get("hazard_statuses", {})
    overall = base_assessment.get("overall_status", "NORMAL")
    exercise_contraindicated = bool(base_assessment.get("exercise_contraindicated", False))
    auto_emergency = bool(base_assessment.get("auto_emergency_recommended", False))
    prov_text = _provenance_label(latest.get("provenance", "SYNTHETIC_DEMO"))
    comm_norm = normalize_comm_mode(comm_state)

    hr = float(latest.get("heart_rate_bpm", 68.0))
    hr_base = float(baseline.get("baseline_hr_bpm", 58.0))
    hr_delta = round(hr - hr_base, 1)

    sys_bp = float(latest.get("systolic_bp_mmhg", 105.0))
    dia_bp = float(latest.get("diastolic_bp_mmhg", 68.0))
    sys_base = float(baseline.get("baseline_systolic_mmhg", baseline.get("baseline_systolic_bp", 112.0)))
    dia_base = float(baseline.get("baseline_diastolic_mmhg", baseline.get("baseline_diastolic_bp", 72.0)))

    spo2 = float(latest.get("spo2_pct", 97.5))
    spo2_base = float(baseline.get("baseline_spo2_pct", 98.4))

    resp_rate = float(latest.get("respiratory_rate_bpm", 16.0))
    resp_base = float(baseline.get("baseline_resp_rate_bpm", 15.0))

    sleep_h = float(latest.get("sleep_duration_hrs", 6.5))
    sleep_base = float(baseline.get("baseline_sleep_hrs", 7.4))
    sleep_delta = round(sleep_h - sleep_base, 1)

    mood = float(latest.get("mood_score", 7.0))
    mood_base = float(baseline.get("baseline_mood_score", 8.2))
    stress = float(latest.get("stress_level", 4.0))
    fatigue = float(latest.get("fatigue_level", 4.0))
    temp_c = float(latest.get("body_temp_c", 36.7))
    temp_base = float(baseline.get("baseline_temp_c", 36.6))

    eq_rate = float(latest.get("equivalent_dose_rate_msv_day", 0.9))
    abs_dose = float(latest.get("absorbed_dose_mgy", 0.4))
    cum_msv = float(latest.get("cumulative_effective_dose_msv", 150.0))
    co2 = float(latest.get("co2_mmhg", 2.5))
    o2_pct = float(latest.get("oxygen_pct", 21.1))
    cabin_temp = float(latest.get("cabin_temp_c", 21.6))
    strength = float(latest.get("muscle_strength_idx", 94.0))
    ex_adherence = float(latest.get("exercise_adherence_pct", 90.0))
    grav_g = float(latest.get("gravity_g", 0.38))
    grav_text = _grav_label(grav_g)

    reported_symptoms = [str(s).strip() for s in (latest.get("reported_symptoms") or []) if str(s).strip()]
    sym_low = " | ".join(reported_symptoms).lower()
    chest_discomfort = bool(latest.get("chest_discomfort", False)) or ("chest" in sym_low)
    palpitations = bool(latest.get("palpitations", False)) or ("palpitation" in sym_low)
    shortness_of_breath = bool(latest.get("shortness_of_breath", False)) or ("shortness of breath" in sym_low) or ("dyspnea" in sym_low)
    resp_list = list(latest.get("respiratory_symptoms") or [])
    if shortness_of_breath and "Shortness of breath" not in resp_list:
        resp_list.append("Shortness of breath")

    # 1. Three immediate questions
    if overall == "CRITICAL":
        how_text = "Immediate attention needed: critical health or habitat excursions detected outside safe personal baseline limits."
    elif overall == "WARNING":
        how_text = "Monitoring required: one or more measurements drifted outside your personal baseline and benefit from timely countermeasures."
    else:
        how_text = "You are doing well. Vital signs and hazard indicators are aligned with your personal baseline."

    changes: List[str] = []
    if chest_discomfort or palpitations or shortness_of_breath:
        active_cp = [lbl for lbl, flg in [("chest discomfort", chest_discomfort), ("palpitations", palpitations), ("shortness of breath", shortness_of_breath)] if flg]
        changes.append(f"Red-flag cardiopulmonary symptoms reported ({', '.join(active_cp)})")
    if spo2 < 94.0:
        changes.append(f"Oxygen saturation dropped to {spo2:.1f}% (baseline {spo2_base:.1f}%)")
    if resp_rate >= 22.0:
        changes.append(f"Respiratory rate elevated to {resp_rate:.0f} breaths/min (baseline {resp_base:.0f}/min)")
    if sys_bp <= 90.0:
        changes.append(f"Blood pressure dropped to {round(sys_bp)}/{round(dia_bp)} mmHg (baseline {round(sys_base)}/{round(dia_base)})")
    elif sys_bp - sys_base >= 18.0:
        changes.append(f"Blood pressure rose to {round(sys_bp)}/{round(dia_bp)} mmHg vs. {round(sys_base)}/{round(dia_base)} baseline")
    if hr_delta >= 8.0:
        changes.append(f"Resting heart rate rose +{hr_delta} BPM over your {hr_base:.0f} BPM baseline")
    if temp_c >= 37.8:
        changes.append(f"Body temperature elevated to {temp_c:.1f}°C")
    if sleep_delta <= -0.7 or mood <= mood_base - 1.8 or stress >= 7.0:
        changes.append(f"Sleep {sleep_h:.1f}h (baseline {sleep_base:.1f}h), Stress {stress:.1f}/10, Mood {mood:.1f}/10")
    if co2 >= 3.0:
        changes.append(f"Cabin CO2 climbed to {co2:.1f} mmHg")
    if eq_rate >= 1.4:
        changes.append(f"Radiation rate increased to {eq_rate:.2f} mSv/day")
    if not changes:
        changes.append("Minor day-to-day variation only; heart rate, oxygenation, and sleep remain steady.")
    what_changed_text = "; ".join(changes) + "."

    recs = sorted(
        list(base_assessment.get("recommendations", [])),
        key=recommendation_sort_key,
    )
    if recs:
        should_act = recs[0].get("action") or recs[0].get("guidance") or "Follow routine onboard hydration, sleep hygiene, and countermeasure schedule."
    elif overall == "CRITICAL":
        should_act = "Stop exertion immediately, notify onboard Crew Medical Officer, and launch the Autonomous Emergency Escalation Checklist."
    else:
        should_act = "No urgent intervention required; continue routine exercise and sleep schedule."

    glance_summary = {
        "overall_status": overall,
        "how_am_i_doing": how_text,
        "what_has_changed": what_changed_text,
        "should_i_take_action": should_act,
        "provenance_label": prov_text,
    }

    # 2. Seven exact Interactive Human Body regions
    head_status = hazard_statuses.get("Isolation and Confinement", "NORMAL")
    if int(latest.get("concentration_difficulty", 0)) == 1 or fatigue >= 6.0:
        head_status = "WARNING" if head_status == "NORMAL" else head_status
    latest_sans = base_assessment.get("latest_sans")
    sans_abnormal = bool(
        latest_sans
        and int(latest_sans.get("mission_day", 0)) >= int(latest.get("mission_day", 0))
        and (
            latest_sans.get("wavy_lines_detected")
            or len(latest_sans.get("scotoma_cells") or []) > 0
            or latest_sans.get("near_acuity_shift")
        )
    )
    eyes_status = "WARNING" if (latest.get("visual_disturbance_sans") or sans_abnormal) else "NORMAL"
    heart_status = (
        "CRITICAL"
        if (
            chest_discomfort
            or (palpitations and (hr_delta >= 22 or hr >= 110 or latest.get("dizziness_severity", 0) >= 1))
            or latest.get("faintness_presyncope")
            or hr_delta >= 30
            or hr >= 120
            or sys_bp <= 88
        )
        else (
            "WARNING"
            if (palpitations or hr_delta >= 12 or sys_bp - sys_base <= -10 or sys_bp - sys_base >= 18 or latest.get("dizziness_severity", 0) >= 1)
            else "NORMAL"
        )
    )
    lungs_status = (
        "CRITICAL"
        if (spo2 < 93.0 or o2_pct < 19.5 or co2 >= 4.5 or resp_rate >= 26.0 or (shortness_of_breath and spo2 < 95.0))
        else (
            "WARNING"
            if (spo2 < 96.0 or resp_rate >= 22.0 or shortness_of_breath or co2 >= 3.2 or bool(resp_list))
            else "NORMAL"
        )
    )
    muscles_status = "WARNING" if strength < 92.0 or ex_adherence < 85.0 or latest.get("musculoskeletal_discomfort", 0) >= 2 else "NORMAL"
    bones_status = "WARNING" if grav_g <= 0.45 and ex_adherence < 85.0 else "NORMAL"
    whole_status = overall

    def _trend(field: str, fallback: float = 0.0) -> List[Dict[str, Any]]:
        return [{"sol": r["mission_day"], "value": round(float(r.get(field, fallback)), 2)} for r in recent_7]

    ts_rec = latest.get("timestamp", "")

    marscare_body_regions = [
        {
            "id": "head_and_brain",
            "name": "Head and Brain",
            "status": head_status,
            "summary": "Mood, stress, fatigue, sleep recovery & cognitive clarity",
            "measurements": [
                {"label": "Mood Score", "value": f"{mood:.1f}", "unit": "/10", "baseline": f"{mood_base:.1f}", "recorded_at": ts_rec},
                {"label": "Stress & Fatigue", "value": f"{stress:.1f} / {fatigue:.1f}", "unit": "/10", "baseline": f"{baseline.get('baseline_stress_score', 2.6):.1f} / 3.0", "recorded_at": ts_rec},
                {"label": "Sleep Duration", "value": f"{sleep_h:.1f}", "unit": "hrs", "baseline": f"{sleep_base:.1f} hrs", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("sleep_duration_hrs", sleep_h),
            "trend_label": "Sleep duration (hrs)",
            "spaceflight_risk": "Isolation, circadian misalignment, and cabin CO2 build-up elevate cognitive fatigue and reduce deep sleep architecture (NASA HRP Isolation).",
            "action_label": "Start Health Assessment",
        },
        {
            "id": "eyes",
            "name": "Eyes",
            "status": eyes_status,
            "summary": "Visual symptoms & Spaceflight Associated Neuro-ocular Syndrome (SANS)",
            "measurements": [
                {"label": "Near-Vision / SANS Shift", "value": "Amsler Flag" if sans_abnormal else ("Symptom Reported" if latest.get("visual_disturbance_sans") else "Clear"), "unit": "Check", "baseline": "Clear", "recorded_at": ts_rec},
                {"label": "Gravity Regime", "value": f"{grav_g}g", "unit": "Field", "baseline": "1.0g Earth", "recorded_at": ts_rec},
                {"label": "Fluid-Shift Pressure Proxy", "value": f"{round(sys_bp)}/{round(dia_bp)}", "unit": "mmHg", "baseline": f"{round(sys_base)}/{round(dia_base)}", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("balance_score", 88.0),
            "trend_label": "Neuro-vestibular stability (%)",
            "spaceflight_risk": f"Headward fluid shifts in {grav_text} can subtly alter optic nerve sheath pressure and refractive focusing (SANS).",
            "action_label": "Start Health Assessment",
        },
        {
            "id": "heart",
            "name": "Heart",
            "status": heart_status,
            "summary": "Heart rate, arterial blood pressure, chest symptoms & orthostatic tolerance",
            "measurements": [
                {"label": "Heart Rate", "value": f"{round(hr)}", "unit": "BPM", "baseline": f"{round(hr_base)} BPM ({hr_delta:+.0f})", "recorded_at": ts_rec},
                {"label": "Blood Pressure", "value": f"{round(sys_bp)}/{round(dia_bp)}", "unit": "mmHg", "baseline": f"{round(sys_base)}/{round(dia_base)} mmHg", "recorded_at": ts_rec},
                {"label": "Chest / Palpitations / Dizziness", "value": ", ".join([s for s, f in [("Chest discomfort", chest_discomfort), ("Palpitations", palpitations)] if f]) or f"Dizzy {latest.get('dizziness_severity', 0)}/3", "unit": "Flags", "baseline": "None · 0/3", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("heart_rate_bpm", hr),
            "trend_label": "Heart rate (BPM)",
            "spaceflight_risk": f"CSA CCISS and Vascular studies document reduced plasma volume and baroreflex drift across {grav_text}; chest discomfort or palpitations require immediate CMO ECG capture.",
            "action_label": "Open Emergency Triage" if heart_status == "CRITICAL" else "Start Health Assessment",
        },
        {
            "id": "lungs",
            "name": "Lungs",
            "status": lungs_status,
            "summary": "Oxygen saturation, respiratory rate & closed-cabin air quality",
            "measurements": [
                {"label": "Oxygen Saturation (SpO2)", "value": f"{spo2:.1f}", "unit": "%", "baseline": f"{spo2_base:.1f}%", "recorded_at": ts_rec},
                {"label": "Respiratory Rate", "value": f"{resp_rate:.0f}", "unit": "breaths/min", "baseline": f"{resp_base:.0f} /min", "recorded_at": ts_rec},
                {"label": "Cabin CO2 / O2", "value": f"{co2:.1f} mmHg · {o2_pct:.1f}%", "unit": "ECLSS", "baseline": "< 3.0 mmHg · 21%", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("spo2_pct", spo2),
            "trend_label": "SpO2 (%)",
            "spaceflight_risk": "CSA CARDIOBREATH and NASA EDA research highlight how stagnant cabin airflow, elevated CO2, hypoxia, or dust trigger airway irritation.",
            "action_label": "Open Emergency Triage" if lungs_status == "CRITICAL" else "Start Health Assessment",
        },
        {
            "id": "muscles",
            "name": "Muscles",
            "status": muscles_status,
            "summary": "Physical activity, strength retention & countermeasure adherence",
            "measurements": [
                {"label": "Strength Index", "value": f"{strength:.1f}", "unit": "%", "baseline": f"{baseline.get('baseline_muscle_strength_idx', 98.0):.1f}%", "recorded_at": ts_rec},
                {"label": "Daily Exercise", "value": f"{latest.get('physical_activity_mins', 90):.0f}", "unit": "mins", "baseline": "105 mins", "recorded_at": ts_rec},
                {"label": "Exercise Safety Status", "value": "HOLD / CONTRAINDICATED" if exercise_contraindicated else f"{ex_adherence:.0f}%", "unit": "Status" if exercise_contraindicated else "%", "baseline": ">= 90%", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("muscle_strength_idx", strength),
            "trend_label": "Muscle strength index (%)",
            "spaceflight_risk": "Postural muscles atrophy rapidly without high-load resistance in 0g and 0.38g, though exercise must be held during acute critical instability.",
            "action_label": "Start Health Assessment",
        },
        {
            "id": "bones",
            "name": "Bones",
            "status": bones_status,
            "summary": "Skeletal loading status & CSA TBone trabecular integrity",
            "measurements": [
                {"label": "Gravitational Load", "value": f"{grav_g}", "unit": "g", "baseline": "1.0 g Earth", "recorded_at": ts_rec},
                {"label": "Resistive Adherence", "value": f"{ex_adherence:.0f}", "unit": "%", "baseline": ">= 90%", "recorded_at": ts_rec},
                {"label": "Musculoskeletal Comfort", "value": f"Grade {latest.get('musculoskeletal_discomfort', 0)}", "unit": "/3", "baseline": "Grade 0", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("exercise_adherence_pct", ex_adherence),
            "trend_label": "Resistive loading adherence (%)",
            "spaceflight_risk": f"CSA TBone shows incomplete trabecular recovery after prolonged unloading; {grav_text} still requires full axial loading when medically cleared.",
            "action_label": "Start Health Assessment",
        },
        {
            "id": "whole_body",
            "name": "Whole Body",
            "status": whole_status,
            "summary": "Cumulative radiation dose, core temperature & systemic mission readiness",
            "measurements": [
                {"label": "Cumulative Effective Dose", "value": f"{cum_msv:.1f}", "unit": "mSv", "baseline": "Tracked per Sol", "recorded_at": ts_rec},
                {"label": "Today Absorbed / Equiv", "value": f"{abs_dose:.2f} mGy / {eq_rate:.2f} mSv", "unit": "Day", "baseline": "~0.44 mGy / 1.07 mSv", "recorded_at": ts_rec},
                {"label": "Body Temperature", "value": f"{temp_c:.1f}", "unit": "°C", "baseline": f"{temp_base:.1f} °C", "recorded_at": ts_rec},
            ],
            "recent_trend": _trend("equivalent_dose_rate_msv_day", eq_rate),
            "trend_label": "Equivalent dose rate (mSv/day)",
            "spaceflight_risk": "All five spaceflight hazards interact systemically — elevated radiation, sleep loss, CO2, and gravity unloading compound overall fatigue.",
            "action_label": "Start Health Assessment",
        },
    ]

    # 3. Four-section Spaceflight Hazard Modules
    hazard_modules_4step = [
        {
            "id": "radiation",
            "title": "Space Radiation",
            "status": hazard_statuses.get("Space Radiation", "NORMAL"),
            "provenance": "Simulated Data + NASA RadLab & RDP References",
            "what_are_we_monitoring": f"Absorbed dose {abs_dose:.2f} mGy/day vs. biologically weighted equivalent dose {eq_rate:.2f} mSv/day (cumulative {cum_msv:.1f} mSv) via habitat TEPC and crew badge.",
            "what_has_changed": f"Latest event tag: {latest.get('radiation_event_type', 'GCR_BACKGROUND')}. Daily equivalent rate {eq_rate:.2f} mSv/day vs. 0.76 mSv/day nominal GCR reference.",
            "why_it_matters_in_space": "Beyond Earth's magnetic field, continuous Galactic Cosmic Rays (GCR) and sudden Solar Particle Events (SPE) damage DNA and cardiovascular tissue. Note: Gy measures physical energy deposited while Sv reflects biological risk; RadLab/RDP datasets are empirical analogs, not unapproved NASA flight limits.",
            "what_should_i_do_next": (
                "ENTER STORM SHELTER IMMEDIATELY (water-wall / polyethylene core), abort all EVAs, and cross-verify TEPC + personal dosimetry."
                if hazard_statuses.get("Space Radiation") == "CRITICAL"
                else "Remain inside high-hydrogen water-wall or regolith-shielded sleeping quarters during elevated solar flux, verify dosimeter calibration, and queue dosimetry packets for ground review."
            ),
        },
        {
            "id": "isolation",
            "title": "Isolation and Confinement",
            "status": hazard_statuses.get("Isolation and Confinement", "NORMAL"),
            "provenance": "Simulated Data + User Check-Ins (NASA HRP / CSA C-STARS)",
            "what_are_we_monitoring": f"Mood ({mood:.1f}/10), stress ({stress:.1f}/10), fatigue ({fatigue:.1f}/10), workload ({latest.get('workload_score', 6):.1f}/10), sleep duration ({sleep_h:.1f}h), and self-reported isolation check-ins.",
            "what_has_changed": f"Sleep is {sleep_delta:+.1f} hrs vs. personal baseline ({sleep_base:.1f}h) with quality at {latest.get('sleep_quality_pct', 80):.0f}%.",
            "why_it_matters_in_space": "Monotony, delayed Earth contact, and high workload in small habitats can erode sleep architecture and crew cohesion over months. This system monitors wellness trends without making psychiatric diagnoses.",
            "what_should_i_do_next": (
                "Stand down from high-criticality tasks, prioritize a protected 9-hour dark/quiet recovery sleep window, and arrange a private supportive CMO peer check-in."
                if hazard_statuses.get("Isolation and Confinement") in ("CRITICAL", "WARNING")
                else "Protect a consistent 7.5-hour sleep window, use scheduled morning blue light / evening dim-amber lighting, journal privately, and share workload transparently during crew huddle."
            ),
        },
        {
            "id": "distance",
            "title": "Distance from Earth",
            "status": hazard_statuses.get("Distance from Earth", "NORMAL"),
            "provenance": "Simulated Link Mode + Local Offline Queue",
            "what_are_we_monitoring": f"Communication link state ({comm_norm['label']}), {comm_state.get('one_way_delay_minutes', 14.2)} min one-way signal latency, local RAG availability, and queued telemetry packets.",
            "what_has_changed": comm_norm["summary"],
            "why_it_matters_in_space": "Round-trip delays up to 44 minutes or solar blackouts make real-time tele-consultation impossible. Crew must evaluate physiological changes, interpret procedures via local RAG, and escalate emergencies onboard.",
            "what_should_i_do_next": "Keep autonomous medical assessments running locally, review priority store-and-forward packets, and sync queued records whenever Earth bandwidth opens.",
        },
        {
            "id": "gravity",
            "title": "Gravity Fields",
            "status": hazard_statuses.get("Gravity Fields", "NORMAL"),
            "provenance": "Simulated Telemetry + CSA CCISS, CARDIOBREATH, TBone & Vascular",
            "what_are_we_monitoring": f"Current regime ({grav_text}), resting HR ({round(hr)} BPM vs {round(hr_base)}), BP ({round(sys_bp)}/{round(dia_bp)} mmHg), dizziness grade ({latest.get('dizziness_severity', 0)}/3), cardiopulmonary symptoms, muscle strength ({strength:.1f}%), and balance ({latest.get('balance_score', 88):.1f}%).",
            "what_has_changed": f"Resting HR shifted {hr_delta:+.0f} BPM and strength sits at {strength:.1f}% under {grav_text}.",
            "why_it_matters_in_space": "Transitioning across 1g, 0g, and ~0.38g alters blood pressure regulation, arterial stiffness (CSA Vascular), trabecular bone mineral (CSA TBone), and inner-ear balance.",
            "what_should_i_do_next": (
                "EXERCISE CONTRAINDICATED: Stop physical exertion immediately, rest in supported or supine Trendelenburg posture as indicated, notify CMO & capture continuous ECG/BP/SpO2, and launch Autonomous Emergency Checklist."
                if exercise_contraindicated
                else "Maintain daily ARED resistive loading, aerobic cycling, fluid-electrolyte pre-hydration prior to upright tasks, and balance progression drills."
            ),
        },
        {
            "id": "environment",
            "title": "Hostile and Closed Environments",
            "status": hazard_statuses.get("Hostile and Closed Environments", "NORMAL"),
            "provenance": "Simulated ECLSS Sensors + NASA EDA & OSDR References",
            "what_are_we_monitoring": f"Cabin CO2 ({co2:.1f} mmHg), O2 ({o2_pct:.1f}%), pressure ({latest.get('cabin_pressure_kpa', 70.3):.1f} kPa), temp ({cabin_temp:.1f}°C), humidity ({latest.get('humidity_pct', 42):.0f}%), AQI ({latest.get('air_quality_index', 30):.0f}), SpO2 ({spo2:.1f}%), and RR ({resp_rate:.0f}/min).",
            "what_has_changed": f"CO2 is {co2:.1f} mmHg, Cabin Temp {cabin_temp:.1f}°C, SpO2 {spo2:.1f}%, and active respiratory/symptom log: {', '.join(resp_list) if resp_list else 'None'}.",
            "why_it_matters_in_space": "Sealed habitats accumulate CO2 pockets, airborne regolith dust, and surface microbes (NASA OSDR / EDA). Environmental irritants must be separated from infectious illness carefully — never auto-diagnosing infection.",
            "what_should_i_do_next": (
                "Verify portable O2 / backup CDRA scrubber bed, check SpO2 & respiratory rate with CMO hardware, and evacuate stagnant air pockets immediately."
                if hazard_statuses.get("Hostile and Closed Environments") == "CRITICAL"
                else "Ensure portable bunk circulation fans run continuously, switch CDRA scrubber beds if CO2 > 3.0 mmHg, inspect HEPA seals, and monitor SpO2 plus temperature."
            ),
        },
    ]

    # 4. Structured Assessment Explanation (NO SILENT [:4] TRUNCATION)
    findings = base_assessment.get("findings", [])
    detected = [f.get("title", "") for f in findings] or ["Physiological telemetry within personal mission baseline."]
    contributing: List[str] = []
    for c in base_assessment.get("baseline_comparisons", []):
        try:
            delta_pct = abs(float(c.get("delta_pct", 0.0)))
            delta_abs = abs(float(c.get("delta", 0.0)))
        except (TypeError, ValueError):
            delta_pct, delta_abs = 0.0, 0.0
        if delta_pct >= 8.0 or delta_abs >= 1.5:
            contributing.append(f"{c.get('metric')}: {c.get('current')} {c.get('unit', '')} (baseline {c.get('baseline')})".strip())
    if spo2 < 95.0:
        contributing.append(f"SpO2: {spo2:.1f}% (baseline {spo2_base:.1f}%)")
    if resp_rate >= 22.0:
        contributing.append(f"Respiratory Rate: {resp_rate:.0f} breaths/min (baseline {resp_base:.0f}/min)")
    if co2 >= 3.0:
        contributing.append(f"Cabin CO2: {co2:.2f} mmHg")
    if eq_rate >= 1.4:
        contributing.append(f"Equivalent Dose Rate: {eq_rate:.2f} mSv/day ({abs_dose:.2f} mGy)")
    if chest_discomfort or palpitations or shortness_of_breath:
        contributing.append(
            "Red-flag symptoms: "
            + ", ".join([s for s, f in [("Chest discomfort", chest_discomfort), ("Palpitations", palpitations), ("Shortness of breath", shortness_of_breath)] if f])
        )
    if not contributing:
        contributing = [f"Heart Rate {round(hr)} BPM", f"SpO2 {spo2:.1f}%", f"Sleep {sleep_h:.1f} hrs", f"CO2 {co2:.1f} mmHg"]
    rel_hazards = sorted({f.get("hazard", "") for f in findings if f.get("hazard")}) or ["All Five Spaceflight Hazards Nominal"]

    structured_explanation = {
        "what_was_detected": detected,
        "contributing_measurements": contributing,
        "associated_factors": [
            f"Gravity regime: {grav_text} ({latest.get('mission_phase', 'MARS_SURFACE').replace('_', ' ').title()})",
            f"Earth link: {comm_norm['label']} ({comm_state.get('one_way_delay_minutes', 14.2)} min one-way)",
            f"Habitat ECLSS: CO2 {co2:.1f} mmHg · O2 {o2_pct:.1f}% · Temp {cabin_temp:.1f}°C · Humidity {latest.get('humidity_pct', 40):.0f}%",
        ],
        "relevant_hazard": rel_hazards,
        "next_steps": [
            (r.get("action") or r.get("title") or "")
            for r in recs
            if (r.get("action") or r.get("title"))
        ]
        or ["Continue routine daily autonomous check-ins."],
    }

    # 5. Four-Category Dynamic & Critical-Safe Health Guidance
    immediate_items: List[Dict[str, str]] = []
    for r in recs:
        if str(r.get("priority", "")).upper() == "IMMEDIATE":
            immediate_items.append({
                "action": r.get("action", ""),
                "rationale": r.get("rationale", "Immediate deterministic safety action triggered by current telemetry."),
                "source": r.get("citation", "TARS Care Safety Engine"),
            })
    if not immediate_items:
        for r in recs:
            if str(r.get("priority", "")).upper() == "HIGH":
                immediate_items.append({
                    "action": r.get("action", ""),
                    "rationale": r.get("rationale", "High-priority action for active hazard warning."),
                    "source": r.get("citation", "TARS Care Safety Engine"),
                })
    if not immediate_items:
        immediate_items.append({
            "action": "Verify cabin CO2 scrubber (CDRA) airflow & maintain standard isotonic hydration when free of acute symptoms.",
            "rationale": "Routine baseline maintenance while all 5 spaceflight hazards remain nominal.",
            "source": "NASA EDA / CSA CCISS",
        })

    if exercise_contraindicated or overall == "CRITICAL":
        preventive_items = [
            {
                "action": "HOLD / SUSPEND SCHEDULED EXERCISE: Do not perform ARED resistive loading or aerobic workouts while CRITICAL vitals, cardiopulmonary symptoms, hypoxia, or storm-shelter alerts remain active.",
                "rationale": "Exertion during acute physiological instability, presyncope, chest discomfort, or acute SPE radiation events is medically unsafe.",
                "source": "NASA-CSTARS-MED-01 / Safety Contraindication Guard",
            },
            {
                "action": "Cross-check neighboring habitat ECLSS sensors (O2, CO2, pressure, AQI) and remain with another crewmember or Crew Medical Officer.",
                "rationale": "Prevents isolated unmonitored deterioration in deep-space blackout/delayed communication phases.",
                "source": "NASA HRP Environment & Distance Protocols",
            },
        ]
    else:
        preventive_items = [
            {
                "action": "Anchor a 7.5-hour protected sleep window with evening amber/dim lighting and pre-sleep cognitive decompression.",
                "rationale": "Multi-day sleep deficits degrade situational awareness and amplify stress responses under confined isolation.",
                "source": "NASA HRP Isolation & Confinement",
            },
            {
                "action": f"Follow supervised ARED resistive bone-loading sets (appropriate for {grav_text}) plus HEPA airlock dust wipe-down after EVA shifts.",
                "rationale": f"Sustains trabecular bone turnover in {grav_text} and limits closed-loop particulate airway irritation.",
                "source": "CSA TBone / NASA OSDR",
            },
        ]

    further_items = (
        [
            {
                "action": "Repeat bilateral BP, HR, SpO2, respiratory rate, tympanic temp, and capture 3-lead/12-lead ECG every 2–15 mins until CMO stabilization.",
                "rationale": "Serial trend tracking during acute distress reveals progression before Earth Flight Surgeons can respond across 14+ min light-time.",
                "source": "NASA C-STARS / CSA CCISS",
            },
            {
                "action": "Document exact onset, severity, and character of all active symptoms for Priority-1 Store-and-Forward Flight Surgeon handoff.",
                "rationale": "Hardware diagnostics and blood assays require explicit CMO documentation onboard.",
                "source": "NASA Distance from Earth Medical Ops",
            },
        ]
        if overall == "CRITICAL" or auto_emergency
        else [
            {
                "action": "Complete the 7-item Behavioral & Sleep Check-In and repeat seated/standing HR & BP check in 4 hours.",
                "rationale": "Longitudinal trend deltas against personal baseline reveal early trajectory shifts far better than single readings.",
                "source": "NASA Life Sciences Portal (NLSP)",
            },
            {
                "action": "Ask the TARS Care Health Assistant to cross-check symptoms against habitat ECLSS logs.",
                "rationale": "Separates environmental CO2/humidity effects from physiological changes cleanly offline.",
                "source": "NASA HRP / CSA C-STARS",
            },
        ]
    )

    escalation_items = [
        {
            "action": (
                "ACTIVE EMERGENCY ESCALATION REQUIRED NOW: Launch Autonomous Emergency Triage Checklist, summon onboard Crew Medical Officer & Commander, and queue a Priority-1 Store-and-Forward Earth packet."
                if (overall == "CRITICAL" or auto_emergency)
                else "Initiate Crew Medical Officer (CMO) autonomous checklist and generate a Priority Store-and-Forward Earth packet if SpO2 < 93%, chest pain/palpitations, fever >= 38.3°C, syncope, or acute neurological symptoms develop."
            ),
            "rationale": "Preserves immediate onboard safety under delayed/offline communications while queuing full context for Flight Surgeons.",
            "source": "NASA Distance from Earth Autonomous Medical Support",
        },
    ]

    guidance_tiers = {
        "Immediate action": immediate_items,
        "Preventive action": preventive_items,
        "Further assessment": further_items,
        "Medical escalation": escalation_items,
    }

    return {
        "comm_mode": comm_norm,
        "glance_summary": glance_summary,
        "marscare_body_regions": marscare_body_regions,
        "hazard_modules_4step": hazard_modules_4step,
        "structured_explanation": structured_explanation,
        "guidance_tiers": guidance_tiers,
    }
