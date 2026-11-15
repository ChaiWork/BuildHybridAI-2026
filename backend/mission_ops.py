"""
Deep-Space Mission Operations, Predictive Runways, SANS Ocular Screening,
Onboard Medical Kit Inventory, and Multi-Crew Privacy Utilities for TARS Care.
100% deterministic and offline-first; never prescribes medications or auto-diagnoses.
"""

from __future__ import annotations
import hashlib
import hmac
from typing import Any, Dict, List, Optional, Tuple
from models import AstronautBaseline, DataProvenance, MissionPhase

DEFAULT_DEMO_PIN = "2026"
_PIN_SALT = "TARSCARE_DEEP_SPACE_LOCAL_SALT_2026"

CREW_ORDER = [
    "ARES-IV-SUCHAI",
    "ARES-IV-VANCE",
    "ARES-IV-CHEN",
    "ARES-IV-OKAFOR",
]


def hash_privacy_pin(pin: str) -> str:
    """Hash a local behavioral-journal PIN cleanly with SHA-256."""
    return hashlib.sha256(f"{_PIN_SALT}:{pin.strip()}".encode("utf-8")).hexdigest()


def verify_privacy_pin(pin: str, stored_hash: str) -> bool:
    """Constant-time comparison for local privacy PIN verification."""
    candidate = hash_privacy_pin(pin)
    return hmac.compare_digest(candidate, stored_hash or "")


def default_crew_baselines() -> Dict[str, Dict[str, Any]]:
    """Return baseline profiles for all four Ares-Horizon IV crew members."""
    return {
        "ARES-IV-SUCHAI": AstronautBaseline(
            astronaut_id="ARES-IV-SUCHAI",
            name="SuChai",
            role="Mission Commander · Surface & EVA Lead",
            age=41,
            baseline_hr_bpm=58.0,
            baseline_systolic_mmhg=112.0,
            baseline_diastolic_mmhg=71.0,
            baseline_spo2_pct=98.5,
            baseline_temp_c=36.6,
            baseline_sleep_hrs=7.6,
            baseline_mood_score=8.2,
            baseline_stress_score=2.4,
            baseline_muscle_strength_idx=100.0,
            baseline_balance_score=95.0,
        ).model_dump(),
        "ARES-IV-VANCE": AstronautBaseline(
            astronaut_id="ARES-IV-VANCE",
            name="Dr. Elena Vance",
            role="Crew Medical Officer (CMO) · Biomedical Lead",
            age=38,
            baseline_hr_bpm=62.0,
            baseline_systolic_mmhg=108.0,
            baseline_diastolic_mmhg=69.0,
            baseline_spo2_pct=98.8,
            baseline_temp_c=36.6,
            baseline_sleep_hrs=7.4,
            baseline_mood_score=8.0,
            baseline_stress_score=2.6,
            baseline_muscle_strength_idx=97.0,
            baseline_balance_score=94.0,
        ).model_dump(),
        "ARES-IV-CHEN": AstronautBaseline(
            astronaut_id="ARES-IV-CHEN",
            name="Marcus Chen",
            role="Flight Engineer · ECLSS & EVA Specialist",
            age=36,
            baseline_hr_bpm=55.0,
            baseline_systolic_mmhg=116.0,
            baseline_diastolic_mmhg=74.0,
            baseline_spo2_pct=98.2,
            baseline_temp_c=36.7,
            baseline_sleep_hrs=7.5,
            baseline_mood_score=8.1,
            baseline_stress_score=2.5,
            baseline_muscle_strength_idx=102.0,
            baseline_balance_score=95.0,
        ).model_dump(),
        "ARES-IV-OKAFOR": AstronautBaseline(
            astronaut_id="ARES-IV-OKAFOR",
            name="Dr. Amina Okafor",
            role="Planetary Astrobiologist · Habitat Lab Lead",
            age=34,
            baseline_hr_bpm=64.0,
            baseline_systolic_mmhg=106.0,
            baseline_diastolic_mmhg=68.0,
            baseline_spo2_pct=98.6,
            baseline_temp_c=36.6,
            baseline_sleep_hrs=7.7,
            baseline_mood_score=8.3,
            baseline_stress_score=2.3,
            baseline_muscle_strength_idx=96.0,
            baseline_balance_score=94.0,
        ).model_dump(),
    }


def crew_synthetic_profiles() -> List[Dict[str, Any]]:
    """Synthetic recent Sol profiles for additional crew members (excluding default SuChai)."""
    return [
        {
            "crew_id": "ARES-IV-VANCE",
            "days": [
                (178, 0.72, 1.56, 152.1, 63, 109, 70, 98.7, 15, 36.6, 7.3, 8.0, 2.7, 3.0, 2.5, 96.5, 93.0, 0, False, "CMO biomedical rounds & onboard ultrasound calibration nominal."),
                (179, 2.65, 1.10, 154.7, 65, 110, 71, 98.6, 15, 36.6, 7.1, 7.9, 2.9, 3.3, 2.6, 96.2, 93.0, 0, False, "Conducted post-SPE dosimetry check across water-wall shelter."),
                (180, 1.15, 0.48, 155.9, 64, 108, 70, 98.7, 15, 36.6, 7.4, 8.0, 2.6, 3.1, 2.5, 96.4, 93.5, 0, False, "Nominal CMO rest cycle and baseline physical checks."),
                (181, 0.80, 0.33, 156.7, 63, 108, 69, 98.8, 15, 36.6, 7.5, 8.1, 2.5, 2.9, 2.4, 96.6, 94.0, 0, False, "Supervised ARED conditioning; all vitals within baseline."),
                (182, 0.82, 0.34, 157.5, 64, 109, 69, 98.6, 15, 36.6, 7.2, 8.0, 2.8, 3.2, 2.7, 96.4, 93.5, 0, False, "Prepared delayed Earth flight-surgeon telemetry review."),
                (183, 1.32, 0.54, 158.8, 65, 110, 70, 98.5, 16, 36.7, 7.1, 7.8, 3.0, 3.5, 3.1, 96.2, 93.0, 0, False, "Monitored crew hydration during CO2 scrubber switchover."),
                (184, 1.44, 0.58, 160.2, 64, 109, 70, 98.6, 15, 36.6, 7.2, 7.9, 2.9, 3.4, 3.1, 96.3, 93.2, 0, False, "CMO baseline stable on Sol 184; cleared for full mission support."),
            ],
            "psych": (184, 8, 3, 8, 3, 3, 2, 6, "Crew morale steady; monitoring SuChai's mild CO2/sleep drift during Sol 184."),
        },
        {
            "crew_id": "ARES-IV-CHEN",
            "days": [
                (178, 0.78, 0.32, 160.4, 59, 118, 75, 98.1, 15, 36.6, 7.2, 7.9, 3.1, 3.8, 2.6, 99.5, 92.0, 0, False, "Surface EVA suit leak-check and airlock dust sweep."),
                (179, 2.88, 1.12, 163.3, 62, 120, 76, 98.0, 16, 36.7, 6.8, 7.6, 3.6, 4.2, 2.9, 98.8, 91.5, 0, False, "Storm-shelter rack maintenance during proton flux."),
                (180, 1.24, 0.50, 164.5, 60, 119, 75, 98.1, 15, 36.6, 7.1, 7.8, 3.3, 3.9, 2.7, 99.0, 92.0, 0, False, "Replaced CDRA blower bearing housing."),
                (181, 0.85, 0.35, 165.4, 63, 121, 76, 97.9, 16, 36.7, 6.6, 7.5, 3.9, 4.5, 2.6, 98.4, 90.5, 0, False, "Dual-EVA equipment haul; mild shoulder fatigue."),
                (182, 0.90, 0.36, 166.3, 66, 124, 78, 97.6, 17, 36.7, 6.1, 7.0, 4.7, 5.4, 3.1, 96.5, 88.0, 1, False, "CDRA regeneration work; mild dizziness upon standing rapidly."),
                (183, 1.48, 0.60, 167.8, 70, 126, 80, 97.2, 18, 36.8, 5.8, 6.6, 5.5, 6.2, 3.4, 94.2, 85.0, 1, False, "Orthostatic +15 bpm delta and moderate muscular fatigue after extended airlock shift."),
                (184, 1.62, 0.65, 169.4, 72, 128, 81, 97.1, 18, 36.8, 5.6, 6.3, 5.9, 6.5, 3.5, 93.0, 82.5, 2, False, "Elevated resting HR (+17 vs baseline) and Grade 2 dizziness; EVA Caution recommended."),
            ],
            "psych": (184, 6, 6, 7, 7, 6, 4, 7, "Back-to-back CDRA & airlock repairs left legs heavy and sleep fragmented."),
        },
        {
            "crew_id": "ARES-IV-OKAFOR",
            "days": [
                (178, 0.74, 0.30, 154.0, 65, 107, 68, 98.5, 15, 36.6, 7.6, 8.2, 2.5, 2.9, 2.5, 95.8, 93.5, 0, False, "Core regolith spectrometry analysis nominal."),
                (179, 2.75, 1.09, 156.8, 67, 108, 69, 98.4, 15, 36.6, 7.3, 8.0, 2.9, 3.2, 2.8, 95.5, 93.0, 0, False, "Storm-shelter calibration check complete."),
                (180, 1.18, 0.48, 157.9, 66, 107, 68, 98.5, 15, 36.6, 7.4, 8.1, 2.8, 3.1, 2.7, 95.6, 93.2, 0, False, "Greenhouse lighting timing test nominal."),
                (181, 0.82, 0.33, 158.8, 65, 106, 68, 98.5, 15, 36.6, 7.2, 7.9, 3.1, 3.4, 2.6, 95.4, 93.0, 0, True, "Mild near-vision blur noted during fine microscope pipette task."),
                (182, 0.84, 0.34, 159.6, 67, 108, 69, 98.4, 16, 36.6, 6.8, 7.6, 3.6, 4.0, 2.9, 95.0, 92.5, 0, True, "Repeated near-acuity check prior to OCT screening."),
                (183, 1.38, 0.56, 161.0, 68, 109, 70, 98.3, 16, 36.7, 6.5, 7.4, 4.1, 4.4, 3.2, 94.8, 92.0, 0, True, "Mild headache near lab glovebox + near-vision accommodation shift."),
                (184, 1.46, 0.59, 162.4, 68, 109, 70, 98.2, 16, 36.7, 6.4, 7.2, 4.3, 4.7, 3.3, 94.5, 91.5, 0, True, "Persisting SANS near-acuity check flag; advise handheld OCT & Amsler grid check."),
            ],
            "psych": (184, 7, 4, 8, 5, 4, 3, 6, "Glovebox work strain near eyes; scheduling ophthalmologic Amsler grid self-check today."),
        },
    ]


def default_medical_kit_items() -> List[Dict[str, Any]]:
    """Return initial offline onboard Medical Operations Kit hardware & consumables."""
    return [
        {
            "item_code": "MED-ECG-12L",
            "name": "Portable 12-Lead / 3-Lead ECG Holter Unit",
            "bay_location": "Med Bay B2 · Drawer 1",
            "category": "Diagnostic Hardware",
            "quantity": 2,
            "unit": "units + 18 lead packs",
            "min_threshold": 1,
            "expiry_date": "2028-09-30",
            "cmo_auth_required": False,
            "notes": "Requires manual CMO or Earth Flight Surgeon rhythm interpretation (no autonomous AI diagnosis).",
            "last_inspected": "2026-11-12T08:00:00Z",
        },
        {
            "item_code": "MED-SPO2-CLIP",
            "name": "Flight Pulse Oximeter & Capnography Sensor",
            "bay_location": "Med Bay B1 · Quick-Grab Pouch",
            "category": "Monitoring Hardware",
            "quantity": 3,
            "unit": "sensors",
            "min_threshold": 1,
            "expiry_date": "2029-01-15",
            "cmo_auth_required": False,
            "notes": "Optical finger/ear SpO2 + mainstream ETCO2 verification.",
            "last_inspected": "2026-11-13T10:00:00Z",
        },
        {
            "item_code": "MED-O2-PORT",
            "name": "Portable Emergency O2 Cylinder & Non-Rebreather Mask",
            "bay_location": "Airlock Locker A1 & Med Bay B1",
            "category": "Respiratory Support",
            "quantity": 4,
            "unit": "cylinders (425 L each)",
            "min_threshold": 2,
            "expiry_date": "2027-12-31",
            "cmo_auth_required": False,
            "notes": "Indicated only under CMO checklist for SpO2 < 94% or toxic cabin gas exposure.",
            "last_inspected": "2026-11-14T06:00:00Z",
        },
        {
            "item_code": "MED-IV-ISOTONIC",
            "name": "Oral Electrolyte Pouches & Sterile Isotonic Saline",
            "bay_location": "Med Bay B3 · Hydration Pack",
            "category": "Orthostatic Support",
            "quantity": 16,
            "unit": "hydration kits",
            "min_threshold": 6,
            "expiry_date": "2027-08-20",
            "cmo_auth_required": False,
            "notes": "First-line oral fluid loading prior to gravity transitions; IV access restricted to CMO.",
            "last_inspected": "2026-11-11T09:00:00Z",
        },
        {
            "item_code": "MED-OCT-SANS",
            "name": "Handheld OCT Scanner & Ocular Tonometer",
            "bay_location": "Med Bay C1 · Vision Case",
            "category": "SANS Screening",
            "quantity": 1,
            "unit": "diagnostic kit",
            "min_threshold": 1,
            "expiry_date": "2029-06-01",
            "cmo_auth_required": False,
            "notes": "Pairs with TARS Care Amsler Grid self-test to monitor optic disc / retinal folds.",
            "last_inspected": "2026-11-10T14:00:00Z",
        },
        {
            "item_code": "MED-DOSIMETER",
            "name": "Personal Active TEPC & Optical Radiation Dosimeters",
            "bay_location": "Storm Shelter Core · Rack S1",
            "category": "Radiation Monitoring",
            "quantity": 6,
            "unit": "calibrated badges",
            "min_threshold": 4,
            "expiry_date": "2028-04-01",
            "cmo_auth_required": False,
            "notes": "Cross-check physical mGy absorbed dose vs. weighted mSv before/after EVA.",
            "last_inspected": "2026-11-14T07:00:00Z",
        },
        {
            "item_code": "MED-CMO-LOCKED",
            "name": "Locked CMO Contingency Pharmacopoeia Kit",
            "bay_location": "Med Bay B4 · Dual-Key Locker",
            "category": "CMO / Flight Surgeon Rx Only",
            "quantity": 1,
            "unit": "sealed medical locker",
            "min_threshold": 1,
            "expiry_date": "2027-05-15",
            "cmo_auth_required": True,
            "notes": "CMO & Earth Flight Surgeon authorization required. TARS Care never selects, calculates, or prescribes medication dosages.",
            "last_inspected": "2026-11-14T08:00:00Z",
        },
    ]


def recommendation_sort_key(rec: Dict[str, Any]) -> Tuple[int, int]:
    """
    Deterministic sorting key enforcing strict severity order (IMMEDIATE > HIGH > DEFERRED > ROUTINE)
    plus sub-priority ordering so acute cardiopulmonary/life-safety/radiation actions ALWAYS outrank
    behavioral stand-down recommendations of the same priority tier.
    """
    priority_rank = {"IMMEDIATE": 0, "HIGH": 1, "DEFERRED": 2, "ROUTINE": 3}
    prio = priority_rank.get(str(rec.get("priority", "ROUTINE")).upper(), 9)
    code = str(rec.get("procedure_code", "")).upper()
    hazard = str(rec.get("hazard", "")).lower()
    citation = str(rec.get("citation", "")).upper()

    if "CARDIO-REDFLAG" in code or "cardiopulm" in hazard:
        sub = 0
    elif "SPE" in code or "RAD" in code or "radiation" in hazard:
        sub = 1
    elif "ENV-CRIT" in code or "GRAV-ORTHO" in code or "hostile" in hazard:
        sub = 2
    elif "HOLD" in code or "gravity" in hazard:
        sub = 3
    elif "ISO" in code or "NASA-HRP-ISO" in citation or "isolation" in hazard:
        sub = 4
    else:
        sub = 5
    return (prio, sub)


def _linear_slope(values: List[float]) -> float:
    """Least-squares slope per sample index; returns 0.0 when fewer than 2 points exist."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    numer = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    return numer / denom


def compute_eva_readiness(
    latest: Dict[str, Any],
    baseline: AstronautBaseline,
    rad_limits: Any,
    env_limits: Any,
    assessment_summary: Dict[str, Any],
    latest_sans: Optional[Dict[str, Any]] = None,
    donki_advisory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute deterministic GO / CAUTION / HOLD readiness for surface or microgravity EVA."""
    overall = str(assessment_summary.get("overall_status", "NORMAL")).upper()
    ex_hold = bool(assessment_summary.get("exercise_contraindicated", False))
    hr = float(latest.get("heart_rate_bpm", 68.0))
    hr_delta = hr - baseline.baseline_hr_bpm
    spo2 = float(latest.get("spo2_pct", 98.0))
    co2 = float(latest.get("co2_mmhg", 2.2))
    eq_rate = float(latest.get("equivalent_dose_rate_msv_day", 1.0))
    cum_rad = float(latest.get("cumulative_effective_dose_msv", 150.0))
    sleep_h = float(latest.get("sleep_duration_hrs", 7.4))
    dizz = int(latest.get("dizziness_severity", 0))
    faint = bool(latest.get("faintness_presyncope", False))
    bal = float(latest.get("balance_score", 90.0))
    chest = bool(latest.get("chest_discomfort", False))
    palp = bool(latest.get("palpitations", False))
    sob = bool(latest.get("shortness_of_breath", False))

    sans_distorted = bool(
        latest_sans
        and (latest_sans.get("wavy_lines_detected") or len(latest_sans.get("scotoma_cells") or []) > 0)
    ) or bool(latest.get("visual_disturbance_sans", False))

    blocking: List[str] = []
    advisories: List[str] = []

    if overall == "CRITICAL" or ex_hold:
        blocking.append("Active CRITICAL safety state / Exercise Hold is enforced")
    if chest or palp or sob or faint:
        blocking.append("Cardiopulmonary or presyncope red-flag symptoms active")
    if spo2 < 94.0:
        blocking.append(f"Resting SpO2 depressed ({spo2:.1f}% < 94%)")
    if eq_rate >= float(getattr(rad_limits, "daily_equivalent_crit_msv", 5.0)):
        blocking.append(f"SPE storm radiation threshold exceeded ({eq_rate:.2f} mSv/day)")
    elif cum_rad >= float(getattr(rad_limits, "cumulative_mission_warn_msv", 350.0)):
        advisories.append(f"Cumulative effective dose elevated ({cum_rad:.1f} mSv)")
    if co2 >= float(getattr(env_limits, "co2_crit_mmhg", 4.5)):
        blocking.append(f"Habitat CO2 critical ({co2:.1f} mmHg)")
    elif co2 >= float(getattr(env_limits, "co2_warn_mmhg", 3.0)):
        advisories.append(f"Cabin CO2 elevated prior to EVA suit purge ({co2:.1f} mmHg)")
    if dizz >= 2 or bal <= baseline.baseline_balance_score - 12.0:
        blocking.append(f"Neuro-vestibular instability (Dizziness {dizz}/3, Balance {bal:.0f}%)")
    elif dizz == 1 or bal <= baseline.baseline_balance_score - 6.0:
        advisories.append(f"Mild balance/orthostatic shift (Dizziness {dizz}/3, Balance {bal:.0f}%)")

    if sans_distorted:
        advisories.append("SANS visual / Amsler distortion flagged — verify CMO ocular clearance before EVA")

    if hr_delta >= 20.0:
        advisories.append(f"Resting HR +{hr_delta:.0f} BPM above personal baseline")
    if sleep_h <= baseline.baseline_sleep_hrs - 1.5:
        advisories.append(f"Recent sleep contraction ({sleep_h:.1f} hrs vs. {baseline.baseline_sleep_hrs:.1f}h baseline)")
    if eq_rate >= float(getattr(rad_limits, "daily_equivalent_warn_msv", 1.5)) and eq_rate < float(getattr(rad_limits, "daily_equivalent_crit_msv", 5.0)):
        advisories.append(f"Elevated solar proton flux ({eq_rate:.2f} mSv/day)")

    donki_items = list((donki_advisory or {}).get("advisories") or [])
    for item in donki_items[:2]:
        advisories.append(item)
    donki_watch = bool(donki_items)

    score = 100
    score -= len(blocking) * 35
    score -= len(advisories) * 12
    score = max(5, min(100, score))

    if blocking:
        status = "HOLD"
        summary = "EVA HOLD: Unsuited physiological, radiation, or cabin environmental excursion requires stabilization and CMO clearance."
    elif advisories or overall == "WARNING":
        status = "CAUTION"
        summary = "EVA CAUTION: Non-critical baseline drift detected. Buddy-system pairing, oral electrolyte pre-hydration, and shortened EVA window advised."
    else:
        status = "GO"
        summary = "EVA GO: Cardiopulmonary, radiation, vestibular, and sleep markers align with personal mission baseline."

    dosimetry_ok = eq_rate < float(getattr(rad_limits, "daily_equivalent_warn_msv", 1.5)) and not donki_watch
    dosimetry_detail = f"{eq_rate:.2f} mSv/d · Cum {cum_rad:.1f} mSv" + (" · DONKI Watch" if donki_watch else "")

    checklist = [
        {"item": "Cardiopulmonary & SpO2 Stability", "ok": not (chest or palp or sob or spo2 < 94.0), "detail": f"HR {round(hr)} bpm · SpO2 {spo2:.1f}%"},
        {"item": "Dosimetry & Solar Weather", "ok": dosimetry_ok, "detail": dosimetry_detail},
        {"item": "Vestibular & SANS Vision Screening", "ok": dizz == 0 and not sans_distorted, "detail": "Clear" if (dizz == 0 and not sans_distorted) else "Review Flag"},
        {"item": "Cabin Pre-Breathe & Recovery Sleep", "ok": sleep_h >= baseline.baseline_sleep_hrs - 1.0 and co2 < 3.5, "detail": f"Sleep {sleep_h:.1f}h · CO2 {co2:.1f} mmHg"},
    ]

    return {
        "status": status,
        "score_pct": score,
        "summary": summary,
        "blocking_factors": blocking,
        "advisory_factors": advisories,
        "pre_eva_checklist": checklist,
        "donki_watch_active": donki_watch,
    }


def compute_predictive_runways(
    latest: Dict[str, Any],
    history: List[Dict[str, Any]],
    baseline: AstronautBaseline,
    rad_limits: Any,
    env_limits: Any,
) -> Dict[str, Any]:
    """Compute deterministic linear-trend threshold runways (no LLM prediction guesses)."""
    recent_5 = history[-5:] if len(history) >= 5 else history
    recent_7 = history[-7:] if len(history) >= 7 else history
    recent_14 = history[-14:] if len(history) >= 14 else history

    # 1. CO2 Scrubber Runway
    co2_vals = [float(r.get("co2_mmhg", 2.2)) for r in recent_5]
    co2_curr = float(latest.get("co2_mmhg", 2.2))
    co2_slope = _linear_slope(co2_vals)
    co2_warn = float(getattr(env_limits, "co2_warn_mmhg", 3.0))
    co2_crit = float(getattr(env_limits, "co2_crit_mmhg", 4.5))
    co2_days_to_crit = None
    if co2_curr >= co2_crit:
        co2_msg = "Critical CO2 threshold reached — switch CDRA scrubber bed immediately."
        co2_days_to_crit = 0.0
    elif co2_slope > 0.03:
        days_rem = max(0.2, (co2_crit - co2_curr) / co2_slope)
        co2_days_to_crit = round(days_rem, 1)
        co2_msg = f"Rising (+{co2_slope:.2f} mmHg/sol): ~{co2_days_to_crit} sols (~{round(days_rem * 24)} hrs) to {co2_crit:.1f} mmHg critical ceiling."
    else:
        co2_msg = f"Stable or declining ({co2_slope:+.2f} mmHg/sol) below {co2_warn:.1f} mmHg warn / {co2_crit:.1f} mmHg critical."

    co2_projection = [
        {"step": f"+{i} Sol", "value": round(max(0.5, co2_curr + co2_slope * i), 2)}
        for i in range(1, 5)
    ]

    # 2. Cumulative Radiation Budget Runway
    cum_curr = float(latest.get("cumulative_effective_dose_msv", 150.0))
    rad_rates = [float(r.get("equivalent_dose_rate_msv_day", 1.0)) for r in recent_7]
    avg_msv_day = sum(rad_rates) / max(1, len(rad_rates))
    cum_warn = float(getattr(rad_limits, "cumulative_mission_warn_msv", 350.0))
    cum_limit = float(getattr(rad_limits, "cumulative_mission_limit_msv", 600.0))
    sols_to_warn = round(max(0.0, (cum_warn - cum_curr) / max(0.1, avg_msv_day)), 0)
    sols_to_limit = round(max(0.0, (cum_limit - cum_curr) / max(0.1, avg_msv_day)), 0)
    rad_projection = [
        {"step": f"+{i * 15} Sols", "value": round(cum_curr + avg_msv_day * (i * 15), 1)}
        for i in range(1, 5)
    ]

    # 3. Sleep Debt & Recovery Forecast
    sleep_vals = [float(r.get("sleep_duration_hrs", baseline.baseline_sleep_hrs)) for r in recent_7]
    debt_hrs = round(sum(max(0.0, baseline.baseline_sleep_hrs - s) for s in sleep_vals), 1)
    recovery_nights = int((debt_hrs + 0.99) // 1.0) if debt_hrs > 0 else 0
    if debt_hrs >= 4.0:
        sleep_msg = f"{debt_hrs:.1f}h cumulative 7-sol sleep debt — requires ~{max(2, min(6, recovery_nights))} protected 8.5h sleep nights."
    elif debt_hrs > 0:
        sleep_msg = f"Mild {debt_hrs:.1f}h 7-sol deficit — 1–2 regular {baseline.baseline_sleep_hrs:.1f}h+ windows restore baseline."
    else:
        sleep_msg = "Zero recent sleep debt relative to personal baseline."

    # 4. Musculoskeletal Conditioning Runway
    str_vals = [float(r.get("muscle_strength_idx", 95.0)) for r in recent_14]
    str_curr = float(latest.get("muscle_strength_idx", 95.0))
    str_slope = _linear_slope(str_vals)

    return {
        "disclaimer": "Deterministic linear projections from onboard SQLite trends; operational planning aid only — not NASA-approved flight limit validation.",
        "co2": {
            "current_mmhg": round(co2_curr, 2),
            "slope_per_sol": round(co2_slope, 3),
            "days_to_critical": co2_days_to_crit,
            "warn_limit_mmhg": co2_warn,
            "crit_limit_mmhg": co2_crit,
            "summary": co2_msg,
            "projected": co2_projection,
        },
        "radiation_budget": {
            "cumulative_msv": round(cum_curr, 1),
            "rolling_avg_msv_day": round(avg_msv_day, 2),
            "warn_threshold_msv": cum_warn,
            "reference_limit_msv": cum_limit,
            "est_sols_to_warn": int(sols_to_warn),
            "est_sols_to_limit": int(sols_to_limit),
            "summary": f"At recent {avg_msv_day:.2f} mSv/day pace: ~{int(sols_to_warn)} sols to {cum_warn:.0f} mSv mission warn threshold (~{int(sols_to_limit)} sols to {cum_limit:.0f} mSv NASA HRP ref).",
            "projected": rad_projection,
        },
        "sleep_debt": {
            "debt_7sol_hrs": debt_hrs,
            "estimated_recovery_nights": max(0, min(6, recovery_nights)) if debt_hrs > 0 else 0,
            "summary": sleep_msg,
        },
        "musculoskeletal": {
            "current_strength_idx": round(str_curr, 1),
            "slope_per_sol": round(str_slope, 3),
            "summary": (
                f"Gradual unloading trend ({str_slope:+.2f}/sol) — sustain ARED axial loads once cleared."
                if str_slope < -0.15
                else f"Strength trajectory stable ({str_slope:+.2f}/sol) at {str_curr:.1f}%."
            ),
        },
    }


def build_flight_surgeon_consult_packet(
    astronaut: Dict[str, Any],
    baseline_history: List[Dict[str, Any]],
    latest: Dict[str, Any],
    assessment: Dict[str, Any],
    comm_state: Dict[str, Any],
    med_kit: List[Dict[str, Any]],
    latest_sans: Optional[Dict[str, Any]],
    cmo_notes: str = "",
) -> Dict[str, Any]:
    """Assemble an Earth Flight Surgeon async consultation summary (no automated prescriptions)."""
    symptoms = []
    for flag, label in [
        (latest.get("chest_discomfort"), "Chest pain / discomfort"),
        (latest.get("palpitations"), "Palpitations"),
        (latest.get("shortness_of_breath"), "Shortness of breath"),
        (latest.get("faintness_presyncope"), "Faintness / presyncope"),
        (latest.get("visual_disturbance_sans"), "SANS visual disturbance"),
    ]:
        if flag:
            symptoms.append(label)
    for item in latest.get("reported_symptoms") or []:
        if item and item not in symptoms:
            symptoms.append(item)

    alerts = assessment.get("active_alerts") or []
    recs = assessment.get("recommendations") or []
    eva = assessment.get("eva_readiness") or {}
    delay = comm_state.get("one_way_delay_minutes", 14.2)

    low_kit = [k["name"] for k in med_kit if int(k.get("quantity", 0)) <= int(k.get("min_threshold", 0))]
    sans_line = (
        f"Sol {latest_sans['mission_day']} ({latest_sans['eye_tested']}): "
        f"Wavy={'Yes' if latest_sans.get('wavy_lines_detected') else 'No'}, "
        f"Scotoma Cells={len(latest_sans.get('scotoma_cells') or [])}, "
        f"Near Shift={'Yes' if latest_sans.get('near_acuity_shift') else 'No'}"
        if latest_sans
        else "No Amsler Grid screening logged yet."
    )

    md_lines = [
        f"# Earth Flight Surgeon Asynchronous Consultation — Sol {latest['mission_day']}",
        f"**Crew Member:** {astronaut.get('name')} ({astronaut.get('astronaut_id')}) · {astronaut.get('role')}",
        f"**Comm Link:** {comm_state.get('earth_comm_status')} ({delay} min one-way light-time)",
        f"**Overall Triage Status:** {assessment.get('overall_status')} | **EVA Readiness:** {eva.get('status', 'N/A')} ({eva.get('score_pct', '--')}%)",
        "",
        "## Vital Signs & Personal Baseline Comparison",
        f"- **Heart Rate:** {latest.get('heart_rate_bpm')} bpm (Baseline {astronaut.get('baseline_hr_bpm')} bpm)",
        f"- **Blood Pressure:** {latest.get('systolic_bp_mmhg')}/{latest.get('diastolic_bp_mmhg')} mmHg (Baseline {astronaut.get('baseline_systolic_mmhg')}/{astronaut.get('baseline_diastolic_mmhg')} mmHg)",
        f"- **SpO2 / RR / Temp:** {latest.get('spo2_pct')}% | {latest.get('respiratory_rate_bpm', 16)}/min | {latest.get('body_temp_c')} °C",
        f"- **Radiation:** {latest.get('absorbed_dose_mgy')} mGy absorbed | {latest.get('equivalent_dose_rate_msv_day')} mSv/day | Cumulative {latest.get('cumulative_effective_dose_msv')} mSv",
        f"- **ECLSS:** CO2 {latest.get('co2_mmhg')} mmHg | O2 {latest.get('oxygen_pct')}% | Cabin {latest.get('cabin_temp_c')} °C",
        f"- **Active Symptoms:** {', '.join(symptoms) if symptoms else 'None reported'}",
        f"- **Latest SANS Amsler Screening:** {sans_line}",
        "",
        "## Active Alerts & Deterministic Actions",
        *(
            [f"- [{a.get('severity')}] {a.get('hazard')}: {a.get('message')}" for a in alerts]
            if alerts
            else ["- No active alerts."]
        ),
        *(
            [f"- Priority [{r.get('priority')}]: {r.get('action')}" for r in recs[:6]]
        ),
        "",
        "## Onboard Medical Kit & Calibration Audit",
        f"- **Baseline Calibration Entries Recorded:** {len(baseline_history)}",
        f"- **Low-Stock / Alert Kit Items:** {', '.join(low_kit) if low_kit else 'All monitored kit items at or above reserve minimum.'}",
        f"- **CMO / Crew Notes:** {cmo_notes.strip() or 'None added.'}",
        "",
        "*Note: Private behavioral journal reflections are excluded by default for crew privacy. TARS Care does not prescribe medications or replace Flight Surgeon authorization.*",
    ]

    summary = (
        f"Async Consult for {astronaut.get('name')} (Sol {latest['mission_day']}): "
        f"Status {assessment.get('overall_status')}, EVA {eva.get('status', 'GO')}, "
        f"HR {round(float(latest.get('heart_rate_bpm', 0)))} bpm, SpO2 {latest.get('spo2_pct')}%, "
        f"Symptoms: {', '.join(symptoms) if symptoms else 'None'}."
    )
    return {
        "title": f"Sol {latest['mission_day']} Earth Flight Surgeon Consult — {astronaut.get('name')}",
        "summary": summary,
        "markdown_preview": "\n".join(md_lines),
        "payload": {
            "crew_id": astronaut.get("astronaut_id"),
            "mission_day": latest["mission_day"],
            "symptoms": symptoms,
            "sans_latest": latest_sans,
            "cmo_notes": cmo_notes.strip(),
            "eva_status": eva.get("status"),
            "markdown_preview": "\n".join(md_lines),
            "medication_policy": "NON_PRESCRIBING_CMO_AUTH_REQUIRED",
        },
        "hazard_triggers": list({a.get("hazard", "Primary Medical Triage") for a in alerts}) or ["Distance from Earth"],
    }
