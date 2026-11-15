"""
Modular Hardware Integration Layer & Medical Device Catalogue for TARS Care.
Grounded strictly in verified NASA HRP and Canadian Space Agency (CSA) research references.
Implements truthful connection classification, pluggable device adapters, strict unit/range
validation (including Gy vs. Sv protection), CSV/JSON import parsing, and labeled Simulation Mode.
"""

from __future__ import annotations
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from models import DeviceConnectionStatus, DeviceDataQuality, IntegrationClassification


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Strict measurement unit & plausibility validation registry.
# Preserves measurement definitions and prevents Gy vs. Sv or unit confusion.
MEASUREMENT_SPECS: Dict[str, Dict[str, Any]] = {
    "heart_rate": {
        "label": "Heart Rate",
        "allowed_units": {"BPM", "bpm"},
        "canonical_unit": "BPM",
        "min": 30.0,
        "max": 220.0,
        "telemetry_field": "heart_rate_bpm",
        "sample_key": "heart_rate_bpm",
    },
    "respiratory_rate": {
        "label": "Respiratory Rate",
        "allowed_units": {"/min", "breaths/min", "rpm"},
        "canonical_unit": "/min",
        "min": 6.0,
        "max": 50.0,
        "telemetry_field": "respiratory_rate_bpm",
        "sample_key": "respiratory_rate_bpm",
    },
    "spo2": {
        "label": "Blood Oxygen Saturation (SpO₂)",
        "allowed_units": {"%"},
        "canonical_unit": "%",
        "min": 60.0,
        "max": 100.0,
        "telemetry_field": "spo2_pct",
        "sample_key": "spo2_pct",
    },
    "skin_or_body_temp": {
        "label": "Body / Skin Temperature",
        "allowed_units": {"°C", "C", "degC"},
        "canonical_unit": "°C",
        "min": 32.0,
        "max": 42.5,
        "telemetry_field": "body_temp_c",
        "sample_key": "body_temp_c",
    },
    "systolic_bp": {
        "label": "Systolic Blood Pressure",
        "allowed_units": {"mmHg"},
        "canonical_unit": "mmHg",
        "min": 60.0,
        "max": 240.0,
        "telemetry_field": "systolic_bp_mmhg",
        "sample_key": "systolic_bp_mmhg",
    },
    "diastolic_bp": {
        "label": "Diastolic Blood Pressure",
        "allowed_units": {"mmHg"},
        "canonical_unit": "mmHg",
        "min": 35.0,
        "max": 150.0,
        "telemetry_field": "diastolic_bp_mmhg",
        "sample_key": "diastolic_bp_mmhg",
    },
    "sleep_duration": {
        "label": "Sleep Duration",
        "allowed_units": {"hrs", "hours", "h"},
        "canonical_unit": "hrs",
        "min": 0.5,
        "max": 16.0,
        "telemetry_field": "sleep_duration_hrs",
        "sample_key": "sleep_duration_hrs",
    },
    "sleep_quality": {
        "label": "Sleep Efficiency / Quality",
        "allowed_units": {"%"},
        "canonical_unit": "%",
        "min": 10.0,
        "max": 100.0,
        "telemetry_field": "sleep_quality_pct",
        "sample_key": "sleep_quality_pct",
    },
    "physical_activity": {
        "label": "Daily Physical Activity",
        "allowed_units": {"mins", "min"},
        "canonical_unit": "mins",
        "min": 0.0,
        "max": 480.0,
        "telemetry_field": "physical_activity_mins",
        "sample_key": "physical_activity_mins",
    },
    "absorbed_dose": {
        "label": "Physical Absorbed Radiation Dose",
        "allowed_units": {"mGy", "Gy", "mGy/day"},
        "canonical_unit": "mGy",
        "min": 0.0,
        "max": 1000.0,
        "telemetry_field": "absorbed_dose_mgy",
        "sample_key": "absorbed_dose_mgy",
    },
    "equivalent_dose_rate": {
        "label": "Biologically Weighted Equivalent Dose Rate",
        "allowed_units": {"mSv/day", "mSv/d", "Sv/day"},
        "canonical_unit": "mSv/day",
        "min": 0.0,
        "max": 500.0,
        "telemetry_field": "equivalent_dose_rate_msv_day",
        "sample_key": "equivalent_dose_rate_msv_day",
    },
    "cumulative_effective_dose": {
        "label": "Cumulative Mission Effective Dose",
        "allowed_units": {"mSv", "Sv"},
        "canonical_unit": "mSv",
        "min": 0.0,
        "max": 5000.0,
        "telemetry_field": "cumulative_effective_dose_msv",
        "sample_key": "cumulative_effective_dose_msv",
    },
    "neutron_bubble_count": {
        "label": "Neutron Detector Bubble Count",
        "allowed_units": {"bubbles", "counts"},
        "canonical_unit": "bubbles",
        "min": 0.0,
        "max": 10000.0,
        "telemetry_field": None,
        "sample_key": "neutron_bubble_count",
    },
    "intraocular_pressure_od": {
        "label": "Intraocular Pressure (Right Eye OD)",
        "allowed_units": {"mmHg"},
        "canonical_unit": "mmHg",
        "min": 5.0,
        "max": 45.0,
        "telemetry_field": None,
        "sample_key": "iop_od_mmhg",
    },
    "intraocular_pressure_os": {
        "label": "Intraocular Pressure (Left Eye OS)",
        "allowed_units": {"mmHg"},
        "canonical_unit": "mmHg",
        "min": 5.0,
        "max": 45.0,
        "telemetry_field": None,
        "sample_key": "iop_os_mmhg",
    },
    "balance_score": {
        "label": "Posturography Balance Stability",
        "allowed_units": {"/100", "score", "%"},
        "canonical_unit": "/100",
        "min": 0.0,
        "max": 100.0,
        "telemetry_field": "balance_score",
        "sample_key": "balance_score",
    },
    "exercise_performance": {
        "label": "Ergometer Exercise Performance",
        "allowed_units": {"%"},
        "canonical_unit": "%",
        "min": 0.0,
        "max": 120.0,
        "telemetry_field": "exercise_performance_pct",
        "sample_key": "exercise_performance_pct",
    },
    "ergometer_power": {
        "label": "Ergometer Mechanical Output",
        "allowed_units": {"W", "watts"},
        "canonical_unit": "W",
        "min": 0.0,
        "max": 1200.0,
        "telemetry_field": None,
        "sample_key": "ergometer_power_w",
    },
    "muscle_strength_index": {
        "label": "Musculoskeletal Strength Index",
        "allowed_units": {"index", "%"},
        "canonical_unit": "index",
        "min": 20.0,
        "max": 130.0,
        "telemetry_field": "muscle_strength_idx",
        "sample_key": "muscle_strength_idx",
    },
    "bone_mineral_density": {
        "label": "Trabecular Bone Volumetric Density (vBMD)",
        "allowed_units": {"mg HA/cm³", "mg/cm3"},
        "canonical_unit": "mg HA/cm³",
        "min": 50.0,
        "max": 900.0,
        "telemetry_field": None,
        "sample_key": "bone_mineral_density",
    },
    "activity_movement_index": {
        "label": "3-Axis Accelerometer Movement Index",
        "allowed_units": {"g-rms", "counts/min"},
        "canonical_unit": "counts/min",
        "min": 0.0,
        "max": 20000.0,
        "telemetry_field": None,
        "sample_key": "movement_counts",
    },
}


# Canonical catalogue of all 20 instruments across Categories A-F.
# Every research URL is verified against official NASA (.gov) or CSA (.asc-csa.gc.ca) publications.
HARDWARE_CATALOG: List[Dict[str, Any]] = [
    # --- CATEGORY A: WEARABLES AND CONTINUOUS PHYSIOLOGICAL SENSORS ---
    {
        "device_id": "ARCHER_ACTIGRAPHY",
        "code": "A1",
        "name": "Actigraphy Wrist & Activity Monitor",
        "category": "wearables",
        "category_label": "Category A · Wearables & Continuous Sensors",
        "illustration_type": "actigraphy_watch",
        "measures": ["Physical activity duration", "Movement intensity", "Sleep/wake timing", "Circadian rest-activity patterns"],
        "how_it_works": "Tri-axial wrist accelerometry samples limb motion epochs to track wake/rest cycles, sleep efficiency, and daily activity consistency without intrusive leads.",
        "body_systems": ["Brain & Circadian", "Muscles", "Whole Body"],
        "research_references": [
            {
                "label": "NASA Ongoing HRP Research (ARCHeR Study)",
                "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
                "agency": "NASA HRP",
            },
            {
                "label": "CSA Artemis II Scientific Research (ARCHeR Collaboration)",
                "url": "https://www.asc-csa.gc.ca/eng/missions/artemis-ii/scientific-research-during-mission.asp",
                "agency": "CSA / NASA",
            },
        ],
        "supported_outputs": ["Sleep Duration (hrs)", "Sleep Quality (%)", "Physical Activity (mins)", "Movement Counts"],
        "connection_methods": ["File-based CSV/JSON sleep & actigraphy export", "Simulated hardware demonstration adapter", "Documented USB/BLE bridge (requires host driver)"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Without physical USB/BLE wrist receiver paired via an approved spacecraft bridge, TARS Care uses CSV/JSON import or clearly labeled Simulated Demo readings.",
    },
    {
        "device_id": "CSA_BIO_MONITOR",
        "code": "A2",
        "name": "Bio-Monitor Smart Shirt",
        "category": "wearables",
        "category_label": "Category A · Wearables & Continuous Sensors",
        "illustration_type": "smart_shirt",
        "measures": ["Heart rate", "Respiratory rate", "Blood oxygen saturation (SpO₂)", "Skin temperature", "3-axis movement"],
        "how_it_works": "Sensor-integrated smart garment worn during daily work, exercise, and sleep captures continuous ECG-derived pulse, thoracic inductance respiration, finger/ear SpO₂, and accelerometry.",
        "body_systems": ["Heart", "Lungs", "Whole Body"],
        "research_references": [
            {
                "label": "CSA Bio-Monitor System",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/bio-monitor.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA CARDIOBREATH Investigation",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/cardiobreath.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA Space Health",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/space-flight-improve-monitor-health-earth.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA Vascular Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/vascular.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Heart Rate (BPM)", "Respiratory Rate (/min)", "SpO₂ (%)", "Body/Skin Temp (°C)", "Movement Index (counts/min)"],
        "connection_methods": ["CSA Bio-Monitor tablet CSV/JSON export import", "Simulated Bio-Monitor stream adapter", "Vendor SDK / Bluetooth bridge (when paired locally)"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "No live Bio-Monitor garment radio is attached in this environment. Use CSV/JSON file import for real exports or Simulation Mode for demonstration only.",
    },
    {
        "device_id": "BP_CUFF_CARDIOBREATH",
        "code": "A3",
        "name": "Inflatable Blood Pressure Cuff",
        "category": "wearables",
        "category_label": "Category A · Wearables & Continuous Sensors",
        "illustration_type": "bp_cuff",
        "measures": ["Systolic blood pressure (mmHg)", "Diastolic blood pressure (mmHg)", "Seated/post-exercise pulse rate"],
        "how_it_works": "Automated oscillometric brachial cuff inflates on initiation to capture arterial pressure waveform oscillations at rest and during CARDIOBREATH protocols.",
        "body_systems": ["Heart", "Whole Body"],
        "research_references": [
            {
                "label": "CSA CARDIOBREATH",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/cardiobreath.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA CCISS Experiment",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/cciss.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Systolic BP (mmHg)", "Diastolic BP (mmHg)", "Heart Rate (BPM)"],
        "connection_methods": ["Guided cuff capture / CSV/JSON import", "Simulated oscillometric demo reading", "Local BLE cuff bridge (when paired)"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value, IntegrationClassification.GUIDED_EXAMINATION.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Requires an oscillometric cuff reading; simulation readings are clearly labeled simulated and compared against your personal baseline.",
    },
    {
        "device_id": "THIGH_CUFFS_COUNTERMEASURE",
        "code": "A4",
        "name": "Tight Thigh Cuffs & Compression Garment",
        "category": "wearables",
        "category_label": "Category A · Wearables & Continuous Sensors",
        "illustration_type": "thigh_cuffs",
        "measures": ["Countermeasure session duration (mins)", "Applied cuff pressure setting (mmHg)", "Compression adherence log"],
        "how_it_works": "Mechanical thigh-compression cuffs (Chibis/Braslet-class countermeasures) sequester venous blood volume in the lower extremities to counter microgravity cephalad fluid shifts.",
        "body_systems": ["Heart", "Eyes", "Whole Body"],
        "research_references": [
            {
                "label": "NASA Ongoing HRP Research",
                "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
                "agency": "NASA HRP",
            },
            {
                "label": "NASA Cardiovascular Health in Microgravity",
                "url": "https://www.nasa.gov/missions/station/cardiovascular-health-in-microgravity/",
                "agency": "NASA",
            },
            {
                "label": "CSA Vascular Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/vascular.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Session Duration (mins)", "Target Cuff Pressure (mmHg)", "Adherence Compliance Log"],
        "connection_methods": ["Guided countermeasure session log (Manual confirmation)"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": False,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": True,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Countermeasure equipment only — NOT a vital-sign sensor. TARS Care strictly logs session usage and never fabricates heart rate or BP readings from thigh cuffs.",
    },

    # --- CATEGORY B: CLINICAL DIAGNOSTIC AND IMAGING EQUIPMENT ---
    {
        "device_id": "ULTRASOUND_VASCULAR",
        "code": "B1",
        "name": "Cardiac & Vascular Ultrasound Console",
        "category": "imaging",
        "category_label": "Category B · Clinical Diagnostic & Imaging",
        "illustration_type": "ultrasound_probe",
        "measures": ["Cardiac chamber / ejection notes", "Carotid / femoral arterial stiffness", "Jugular venous flow & vessel characteristics"],
        "how_it_works": "Crew Medical Officer performs guided echocardiography or vascular Doppler sweeps; examination findings, images, and structured notes are logged in TARS Care for cardiovascular follow-up and Flight Surgeon sync.",
        "body_systems": ["Heart", "Eyes", "Whole Body"],
        "research_references": [
            {
                "label": "CSA Vascular Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/vascular.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Gravity Fields Hazard (Cardiovascular Adaptation)",
                "url": "https://www.nasa.gov/hrp/hazard-gravity-fields/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Structured Ultrasound Findings", "Ultrasound Still Images / Reports", "Cardiovascular History Link"],
        "connection_methods": ["Guided ultrasound examination form + Medical image/report upload"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "TARS Care records CMO/crew ultrasound examination findings and uploaded image reports — it does NOT perform acoustic ultrasound beamforming or autonomous echo interpretation.",
    },
    {
        "device_id": "OCULAR_TONOMETER_SANS",
        "code": "B2",
        "name": "Eye-Pressure Tonometer & SANS Screening Kit",
        "category": "imaging",
        "category_label": "Category B · Clinical Diagnostic & Imaging",
        "illustration_type": "ocular_tonometer",
        "measures": ["Intraocular pressure OD/OS (mmHg)", "Amsler grid visual distortion", "Optic disc / retinal shift notes"],
        "how_it_works": "Handheld ocular tonometer and neuro-ocular visual screening monitor intraocular pressure and Spaceflight-Associated Neuro-ocular Syndrome (SANS) indicators caused by headward fluid redistribution.",
        "body_systems": ["Eyes", "Head and Brain"],
        "research_references": [
            {
                "label": "NASA Brain Fluid Pressure Research",
                "url": "https://www.nasa.gov/reference/brain-fluid-pressure/",
                "agency": "NASA HRP",
            },
            {
                "label": "NASA Gravity Fields Hazard (SANS)",
                "url": "https://www.nasa.gov/hrp/hazard-gravity-fields/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["IOP OD / OS (mmHg)", "Abnormal SANS Threshold Flags", "Visual Assessment History"],
        "connection_methods": ["Guided tonometry & visual exam workflow + JSON/CSV import"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Requires handheld tonometer measurement or interactive SANS Amsler check. Readings >21 mmHg or >4 mmHg asymmetry are flagged for CMO/Flight Surgeon review.",
    },
    {
        "device_id": "MRI_NEURO_OCULAR",
        "code": "B3",
        "name": "MRI Neurological & Ocular Imaging Record",
        "category": "imaging",
        "category_label": "Category B · Clinical Diagnostic & Imaging",
        "illustration_type": "mri_scanner",
        "measures": ["Pre/post-mission brain ventricular structure", "Optic nerve / globe flattening findings", "Spatial orientation MRI correlation"],
        "how_it_works": "Specialized clinical ground/medical facility MRI examination record. Tracks scan dates, radiology findings, and uploaded imaging summaries linked to Wayfinding and SANS neuro-ocular history.",
        "body_systems": ["Head and Brain", "Eyes"],
        "research_references": [
            {
                "label": "CSA Wayfinding Spatial Orientation Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/wayfinding.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Ongoing HRP Research (Standard Measures)",
                "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
                "agency": "NASA HRP",
            },
            {
                "label": "CSA Artemis II Scientific Research",
                "url": "https://www.asc-csa.gc.ca/eng/missions/artemis-ii/scientific-research-during-mission.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["MRI Scan Date & Study Type", "Neurological / Ocular Report Uploads", "Baseline Imaging Comparison"],
        "connection_methods": ["Specialized examination record + MRI report/image file upload"],
        "integration_classification": IntegrationClassification.IMPORT_SUPPORTED.value,
        "secondary_classifications": [IntegrationClassification.GUIDED_EXAMINATION.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Specialized ground/facility imaging archive ONLY — NOT an onboard wearable or continuous spacecraft sensor.",
    },
    {
        "device_id": "TBONE_3D_SCANNER",
        "code": "B4",
        "name": "High-Resolution 3D Bone Scanner (HR-pQCT)",
        "category": "imaging",
        "category_label": "Category B · Clinical Diagnostic & Imaging",
        "illustration_type": "bone_scanner",
        "measures": ["Volumetric bone mineral density (mg HA/cm³)", "Trabecular & cortical microarchitecture", "Longitudinal bone loss delta (%)"],
        "how_it_works": "Tracks high-resolution peripheral quantitative computed tomography (HR-pQCT) tibia/radius bone microarchitecture reports before and after long-duration unloading.",
        "body_systems": ["Bones", "Muscles"],
        "research_references": [
            {
                "label": "CSA TBone Study",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/tbone.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Life Sciences Portal (NLSP)",
                "url": "https://nlsp.nasa.gov/",
                "agency": "NASA",
            },
        ],
        "supported_outputs": ["vBMD (mg HA/cm³)", "Microarchitecture Comparison Report", "Skeletal History"],
        "connection_methods": ["3D bone scan report upload & CSV/JSON import"],
        "integration_classification": IntegrationClassification.IMPORT_SUPPORTED.value,
        "secondary_classifications": [IntegrationClassification.GUIDED_EXAMINATION.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Clinical HR-pQCT reports are imported post-scan; TARS Care tracks serial density shifts against personal skeletal baselines.",
    },

    # --- CATEGORY C: RADIATION DOSIMETRY HARDWARE ---
    {
        "device_id": "EVARM_MOSFET",
        "code": "C1",
        "name": "EVARM MOSFET Dosimeter Badges",
        "category": "dosimetry",
        "category_label": "Category C · Radiation Dosimetry Hardware",
        "illustration_type": "evarm_badge",
        "measures": ["EVA physical absorbed dose (mGy)", "Anatomical badge location (Skin / Eyes / BFO)", "Spacewalk exposure timestamps"],
        "how_it_works": "Miniature Metal-Oxide Semiconductor Field-Effect Transistor (MOSFET — 'little transistor') dosimeters worn inside spacesuits record voltage threshold shifts proportional to localized ionizing dose.",
        "body_systems": ["Whole Body", "Eyes", "Bones"],
        "research_references": [
            {
                "label": "CSA EVARM Project",
                "url": "https://www.asc-csa.gc.ca/eng/iss/evarm.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA Monitoring Radiation for Astronaut Health",
                "url": "https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Absorbed Dose (mGy)", "Body Location Tag", "Exposure Timestamp"],
        "connection_methods": ["EVARM badge readout CSV/JSON import", "Simulated EVA badge demonstration readout"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Preserves EVARM physical absorbed dose strictly in mGy (never relabeled as Sv) with anatomical badge placement metadata.",
    },
    {
        "device_id": "RADI_N2_BUBBLE",
        "code": "C2",
        "name": "Radi-N / Radi-N2 Neutron Bubble Detectors",
        "category": "dosimetry",
        "category_label": "Category C · Radiation Dosimetry Hardware",
        "illustration_type": "bubble_detector",
        "measures": ["Neutron bubble count", "Neutron equivalent dose estimate (mSv)", "Deployment & collection dates by module"],
        "how_it_works": "Polymer-gel neutron bubble detectors expand visible gas bubbles when struck by secondary neutrons across spacecraft modules; detectors require manual inspection or dedicated optical reading after deployment.",
        "body_systems": ["Whole Body", "Head and Brain"],
        "research_references": [
            {
                "label": "CSA Radi-N2 Experiment",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA Monitoring Radiation for Astronaut Health",
                "url": "https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Deployment & Read Dates", "Bubble Count (bubbles)", "Derived Equivalent Dose (mSv)"],
        "connection_methods": ["Guided deployment log + Manual / Optical bubble-reader import"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Passive threshold detectors requiring deployment and post-exposure optical/manual reading — NOT continuous digital streaming sensors.",
    },
    {
        "device_id": "AUTO_BUBBLE_READER",
        "code": "C3",
        "name": "Automatic Bubble Reader",
        "category": "dosimetry",
        "category_label": "Category C · Radiation Dosimetry Hardware",
        "illustration_type": "bubble_reader",
        "measures": ["Automated optical bubble count", "Detector serial & calibration factor", "Processed neutron exposure dose (mSv)"],
        "how_it_works": "Captures optical images of Radi-N/Radi-N2 polymer gel tubes to count neutron-induced bubbles automatically and log calibrated radiation history.",
        "body_systems": ["Whole Body"],
        "research_references": [
            {
                "label": "CSA Radi-N2 Bubble Detectors & Reader",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Space Radiation Hazard",
                "url": "https://www.nasa.gov/hrp/hazard-space-radiation/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Bubble Count (bubbles)", "Weighted Neutron Dose (mSv)"],
        "connection_methods": ["Bubble-reader CSV/JSON batch import", "Simulated optical reader scan"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Uses optical reader CSV/JSON import or labeled Simulation Mode when physical USB reader hardware is absent.",
    },
    {
        "device_id": "CANS_SPECTROMETER",
        "code": "C4",
        "name": "Canadian Active Neutron Spectrometer (CANS)",
        "category": "dosimetry",
        "category_label": "Category C · Radiation Dosimetry Hardware",
        "illustration_type": "cans_spectrometer",
        "measures": ["Active absorbed dose (mGy)", "Biologically weighted equivalent dose rate (mSv/day)", "Cumulative mission exposure (mSv)"],
        "how_it_works": "Autonomous multi-channel active spectrometer monitors ambient neutron and ionizing radiation spectrum continuously across spacecraft transit and surface operations without waiting for Earth processing.",
        "body_systems": ["Whole Body", "Head and Brain", "Bones"],
        "research_references": [
            {
                "label": "CSA Monitoring Radiation for Astronaut Health (CANS)",
                "url": "https://www.asc-csa.gc.ca/eng/news/articles/2026/2026-02-26-monitoring-radiation-astronaut-health.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Space Radiation Hazard",
                "url": "https://www.nasa.gov/hrp/hazard-space-radiation/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Absorbed Dose (mGy)", "Equivalent Dose Rate (mSv/day)", "Cumulative Dose (mSv)"],
        "connection_methods": ["Telemetry CSV/JSON ingestion", "Simulated CANS autonomous spectrometer stream"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Strictly separates physical absorbed energy (mGy) from weighted biological dose (mSv/day) and flags source provenance explicitly.",
    },

    # --- CATEGORY D: TELEMEDICINE AND INTEGRATED MEDICAL SYSTEMS ---
    {
        "device_id": "TEMPUS_PRO",
        "code": "D1",
        "name": "Tempus Pro Telemedicine Monitor",
        "category": "telemedicine",
        "category_label": "Category D · Telemedicine & Integrated Systems",
        "illustration_type": "tempus_pro",
        "measures": ["Heart rate / ECG summary", "Non-invasive BP (mmHg)", "SpO₂ (%)", "Respiratory rate (/min)", "Temperature (°C)"],
        "how_it_works": "Compact Crew Medical Officer multi-parameter clinical monitor consolidating vital signs and ECG capture during onboard medical evaluations and remote consultation.",
        "body_systems": ["Heart", "Lungs", "Whole Body"],
        "research_references": [
            {
                "label": "NASA Tempus Pro Medical Monitor Reference",
                "url": "https://www.nasa.gov/reference/tempus-pro/",
                "agency": "NASA HRP",
            },
            {
                "label": "NASA Ongoing HRP Research",
                "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Heart Rate (BPM)", "Systolic/Diastolic BP (mmHg)", "SpO₂ (%)", "Resp. Rate (/min)", "Body Temp (°C)"],
        "connection_methods": ["Authorized Tempus Pro JSON/CSV summary import", "Simulated multi-parameter triage packet"],
        "integration_classification": IntegrationClassification.IMPORT_SUPPORTED.value,
        "secondary_classifications": [IntegrationClassification.SIMULATION_AVAILABLE.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Proprietary vendor wire protocol is not exposed locally; supports authorized export import or labeled Simulation Mode without claiming live ECG waveform auto-diagnosis.",
    },
    {
        "device_id": "ARTEMIS_AI_CONCEPT",
        "code": "D2",
        "name": "Integrated AI Health Analysis Concept (CSA/Artemis)",
        "category": "telemedicine",
        "category_label": "Category D · Telemedicine & Integrated Systems",
        "illustration_type": "ai_platform",
        "measures": ["Personal baseline drift synthesis", "Cross-hazard clinical pattern flagging", "Source-attributed decision support"],
        "how_it_works": "Represents the CSA Space Health / Artemis deep-space medical data integration framework. Onboard TARS Care executes its own local deterministic assessment engine and offline RAG stack independently without calling external Artemis APIs.",
        "body_systems": ["Whole Body"],
        "research_references": [
            {
                "label": "CSA Space Health Initiative",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/space-flight-improve-monitor-health-earth.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA Artemis II Scientific Research",
                "url": "https://www.asc-csa.gc.ca/eng/missions/artemis-ii/scientific-research-during-mission.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Local Assessment Synthesis", "Multi-Device Source Attribution"],
        "connection_methods": ["Scientific architecture reference (Processed locally by TARS Care Engine)"],
        "integration_classification": IntegrationClassification.NOT_INTEGRATED.value,
        "secondary_classifications": [],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": False,
            "supports_guided_exam": False,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Conceptual CSA/Artemis research reference ONLY — not an external API that TARS Care queries. Confirmed hardware measurements are analyzed directly by TARS Care's onboard engine.",
    },

    # --- CATEGORY E: BIOLOGICAL SAMPLE COLLECTION TOOLS ---
    {
        "device_id": "SALIVA_BLOTTING_BOOKLET",
        "code": "E1",
        "name": "Saliva Blotting Booklets",
        "category": "biosamples",
        "category_label": "Category E · Biological Sample Collection",
        "illustration_type": "saliva_booklet",
        "measures": ["Collection sample ID & timestamp", "Sample processing status", "Imported cortisol / viral reactivation lab assays"],
        "how_it_works": "Dry filter-paper blotting strips collect crew saliva for longitudinal immune biomarker and stress hormone studies. Results arrive only when separate laboratory assay files are imported.",
        "body_systems": ["Whole Body", "Brain & Circadian"],
        "research_references": [
            {
                "label": "CSA / NASA Artemis II Scientific Research (Immune Biomarkers)",
                "url": "https://www.asc-csa.gc.ca/eng/missions/artemis-ii/scientific-research-during-mission.asp",
                "agency": "NASA / CSA",
            },
            {
                "label": "NASA Open Science Data Repository (OSDR)",
                "url": "https://osdr.nasa.gov/",
                "agency": "NASA",
            },
        ],
        "supported_outputs": ["Sample Collection Log (SAL-...)", "Imported Salivary Assay JSON/CSV"],
        "connection_methods": ["Guided collection workflow + Separate lab assay CSV/JSON import"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": True,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Collection booklet only — generates NO direct sensor metrics. Biomarker values appear strictly after importing verified lab assay results.",
    },
    {
        "device_id": "BIOLOGICAL_SAMPLING_KIT",
        "code": "E2",
        "name": "Multi-Specimen Biological Sampling Kits",
        "category": "biosamples",
        "category_label": "Category E · Biological Sample Collection",
        "illustration_type": "biosample_kit",
        "measures": ["Whole blood / plasma / PBMC / serum", "Urine / stool / skin biopsy / microbiome swab", "Cold-stowage metadata & imported lab results"],
        "how_it_works": "Logs crew biological specimen collection, unique sample barcodes, and MELFI/cold stowage metadata across NASA Standard Measures and Immune studies, keeping specimen logging cleanly separated from imported lab assays.",
        "body_systems": ["Whole Body"],
        "research_references": [
            {
                "label": "NASA Ongoing HRP Research (Standard Measures)",
                "url": "https://www.nasa.gov/hrp/ongoing-hrp-research/",
                "agency": "NASA HRP",
            },
            {
                "label": "NASA Open Science Data Repository (OSDR)",
                "url": "https://osdr.nasa.gov/",
                "agency": "NASA",
            },
        ],
        "supported_outputs": ["Sample ID & Cold-Stowage Metadata", "Separate Laboratory Assay Import"],
        "connection_methods": ["Guided biological specimen form + Lab assay JSON/CSV import"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": True,
            "supports_guided_exam": False,
            "supports_biosample": True,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Sample collection hardware does NOT generate live biomarkers directly. Laboratory assay files must be imported separately.",
    },

    # --- CATEGORY F: BEHAVIOURAL AND PHYSICAL PERFORMANCE TOOLS ---
    {
        "device_id": "BEHAVIORAL_SURVEY_SUITE",
        "code": "F1",
        "name": "Computerised Behavioural & Neuropsych Surveys",
        "category": "behavioral_perf",
        "category_label": "Category F · Behavioural & Performance Tools",
        "illustration_type": "behavioral_survey",
        "measures": ["Mood & wellbeing", "Cognitive workload & attention", "Stress & social isolation"],
        "how_it_works": "Digital longitudinal self-report battery modeled on ARCHeR and C-STARS monitoring stress trajectories without performing autonomous psychiatric diagnoses.",
        "body_systems": ["Brain & Circadian", "Whole Body"],
        "research_references": [
            {
                "label": "CSA C-STARS Mental Health Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/cstars.asp",
                "agency": "CSA",
            },
            {
                "label": "NASA Isolation & Confinement Hazard",
                "url": "https://www.nasa.gov/hrp/hazard-isolation-and-confinement/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Emotional Condition (/10)", "Stress Rating (/10)", "Cognitive Strain (/10)", "PIN-Protected Reflections"],
        "connection_methods": ["Onboard digital survey (Syncs to Isolation & Confinement module)"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": False,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Digital survey trends are compared strictly against personal baseline without diagnosing depressive or anxiety disorders.",
    },
    {
        "device_id": "POSTUROGRAPHY_BALANCE",
        "code": "F2",
        "name": "Posturography & Sensorimotor Balance System",
        "category": "behavioral_perf",
        "category_label": "Category F · Behavioural & Performance Tools",
        "illustration_type": "balance_plate",
        "measures": ["Postural stability balance score (/100)", "Orthostatic dizziness severity (0-3)", "Neurovestibular coordination notes"],
        "how_it_works": "Guided standing/tandem stance sensorimotor test evaluates vestibular adaptation and ataxia risk before EVA operations in 0.38g Mars or 1.0g Earth gravity transitions.",
        "body_systems": ["Brain & Circadian", "Muscles", "Whole Body"],
        "research_references": [
            {
                "label": "NASA Gravity Fields Hazard",
                "url": "https://www.nasa.gov/hrp/hazard-gravity-fields/",
                "agency": "NASA HRP",
            },
            {
                "label": "CSA Wayfinding Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/wayfinding.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Balance Score (/100)", "Dizziness Grade (0-3)", "Gravity Fields History"],
        "connection_methods": ["Guided sensorimotor exam + CSV/JSON force-plate import + Simulation demo"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [IntegrationClassification.SIMULATION_AVAILABLE.value, IntegrationClassification.IMPORT_SUPPORTED.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Do NOT perform standing balance testing if cardiopulmonary red flags, severe dizziness, or presyncope are active.",
    },
    {
        "device_id": "CYCLE_ERGOMETER_ASTROFIT",
        "code": "F3",
        "name": "Stationary Cycle Ergometer & AstroFit Countermeasure",
        "category": "behavioral_perf",
        "category_label": "Category F · Behavioural & Performance Tools",
        "illustration_type": "cycle_ergometer",
        "measures": ["Exercise session duration (mins)", "Mechanical power output (W)", "Performance (%) & Adherence (%)"],
        "how_it_works": "Microgravity-harnessed cycle ergometer tracks aerobic power output, workload tolerance, and countermeasure compliance for CSA AstroFit & CARDIOBREATH fitness tracking.",
        "body_systems": ["Heart", "Muscles", "Bones"],
        "research_references": [
            {
                "label": "CSA AstroFit Exercise Research",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/astrofit.asp",
                "agency": "CSA",
            },
            {
                "label": "CSA CARDIOBREATH",
                "url": "https://www.asc-csa.gc.ca/eng/sciences/cardiobreath.asp",
                "agency": "CSA",
            },
        ],
        "supported_outputs": ["Exercise Performance (%)", "Activity Duration (mins)", "Ergometer Output (W)"],
        "connection_methods": ["Ergometer CSV/JSON session import", "Guided exercise log / Simulation session"],
        "integration_classification": IntegrationClassification.SIMULATION_AVAILABLE.value,
        "secondary_classifications": [IntegrationClassification.IMPORT_SUPPORTED.value, IntegrationClassification.GUIDED_EXAMINATION.value],
        "capabilities": {
            "supports_simulation": True,
            "supports_import": True,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": False,
        },
        "limitations_notice": "Respects TARS Care Exercise Hold safety gates: automatically flagged contraindicated whenever CRITICAL vitals or cardiopulmonary symptoms are active.",
    },
    {
        "device_id": "VEGGIE_SPACE_GARDENING",
        "code": "F4",
        "name": "Space Gardening / Veggie Wellbeing System",
        "category": "behavioral_perf",
        "category_label": "Category F · Behavioural & Performance Tools",
        "illustration_type": "veggie_garden",
        "measures": ["Horticulture care duration (mins)", "Plant crop growth observation", "Subjective calm / wellbeing reflection"],
        "how_it_works": "Crew crop tending aboard habitat Veggie chambers counters sensory monotony during deep-space transit and confinement; logs session participation directly to behavioral wellbeing tracking.",
        "body_systems": ["Brain & Circadian", "Whole Body"],
        "research_references": [
            {
                "label": "NASA Veggie Plant Growth System",
                "url": "https://science.nasa.gov/mission/veggie/",
                "agency": "NASA",
            },
            {
                "label": "NASA Isolation & Confinement Hazard",
                "url": "https://www.nasa.gov/hrp/hazard-isolation-and-confinement/",
                "agency": "NASA HRP",
            },
        ],
        "supported_outputs": ["Horticulture Care Log", "Subjective Wellbeing Reflection"],
        "connection_methods": ["Guided behavioral wellbeing activity logger"],
        "integration_classification": IntegrationClassification.GUIDED_EXAMINATION.value,
        "secondary_classifications": [],
        "capabilities": {
            "supports_simulation": False,
            "supports_import": False,
            "supports_guided_exam": True,
            "supports_biosample": False,
            "is_countermeasure_only": False,
            "is_wellbeing_activity": True,
        },
        "limitations_notice": "Behavioral wellbeing & plant-care log ONLY — NOT a medical diagnostic instrument.",
    },
]

CATALOG_BY_ID: Dict[str, Dict[str, Any]] = {d["device_id"]: d for d in HARDWARE_CATALOG}


def validate_and_normalize_measurement(
    *,
    astronaut_id: str,
    device: Dict[str, Any],
    measurement_type: str,
    raw_value: Any,
    unit: str,
    recorded_at: Optional[str],
    connection_method: str,
    data_source: str,
    connection_status: str,
    confirmed: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validate unit compatibility, numeric plausibility, and Gy-vs-Sv separation.
    Never silently reinterprets missing/invalid values as normal.
    """
    mkey = measurement_type.strip().lower().replace(" ", "_")
    alias_map = {
        "hr": "heart_rate",
        "heart_rate_bpm": "heart_rate",
        "rr": "respiratory_rate",
        "respiratory_rate_bpm": "respiratory_rate",
        "spo2_pct": "spo2",
        "temp": "skin_or_body_temp",
        "body_temp_c": "skin_or_body_temp",
        "sbp": "systolic_bp",
        "systolic_bp_mmhg": "systolic_bp",
        "dbp": "diastolic_bp",
        "diastolic_bp_mmhg": "diastolic_bp",
        "sleep_duration_hrs": "sleep_duration",
        "sleep_quality_pct": "sleep_quality",
        "physical_activity_mins": "physical_activity",
        "absorbed_dose_mgy": "absorbed_dose",
        "equivalent_dose_rate_msv_day": "equivalent_dose_rate",
        "cumulative_effective_dose_msv": "cumulative_effective_dose",
        "iop_od": "intraocular_pressure_od",
        "iop_os": "intraocular_pressure_os",
        "exercise_performance_pct": "exercise_performance",
        "muscle_strength_idx": "muscle_strength_index",
    }
    mkey = alias_map.get(mkey, mkey)
    spec = MEASUREMENT_SPECS.get(mkey)

    ts = (recorded_at or "").strip() or _now_iso()
    meta = dict(metadata or {})
    unit_clean = (unit or "").strip()

    num_val: Optional[float] = None
    val_text: Optional[str] = None
    if raw_value is None or str(raw_value).strip() == "":
        quality_status = DeviceDataQuality.INCOMPLETE.value
        quality_note = "Missing measurement value."
    else:
        try:
            num_val = float(raw_value)
        except (TypeError, ValueError):
            num_val = None
            val_text = str(raw_value).strip()

        if num_val is None:
            quality_status = DeviceDataQuality.INCOMPLETE.value
            quality_note = "Non-numeric measurement value received."
        elif spec:
            # Explicit Gy vs. Sv radiation protection
            if mkey == "absorbed_dose" and unit_clean.lower() in {"msv", "sv", "msv/day", "sv/day"}:
                quality_status = DeviceDataQuality.INVALID_UNIT.value
                quality_note = "Unit safety error: Absorbed physical dose must use Gy/mGy, not Sieverts (Sv/mSv)."
            elif mkey in ("equivalent_dose_rate", "cumulative_effective_dose") and unit_clean.lower() in {"mgy", "gy", "mgy/day"}:
                quality_status = DeviceDataQuality.INVALID_UNIT.value
                quality_note = "Unit safety error: Equivalent/effective dose must use Sv/mSv, not physical Gray (Gy/mGy)."
            elif unit_clean not in spec["allowed_units"]:
                quality_status = DeviceDataQuality.INVALID_UNIT.value
                quality_note = f"Expected unit in {sorted(spec['allowed_units'])}, got '{unit_clean or 'empty'}'."
            elif num_val < spec["min"] or num_val > spec["max"]:
                quality_status = DeviceDataQuality.OUT_OF_RANGE.value
                quality_note = f"Reading {num_val} {unit_clean} outside plausible instrument range ({spec['min']}..{spec['max']})."
            else:
                quality_status = DeviceDataQuality.VALID.value
                quality_note = "Units and physiological/instrument bounds verified."
                if unit_clean in {"bpm", "degC", "C", "hours", "h", "min", "mSv/d", "watts", "counts", "score", "mg/cm3"}:
                    unit_clean = spec["canonical_unit"]
        else:
            quality_status = DeviceDataQuality.VALID.value if unit_clean else DeviceDataQuality.INCOMPLETE.value
            quality_note = "Custom measurement preserved with source unit." if unit_clean else "Missing measurement unit."

    return {
        "record_uid": f"DEV-{uuid.uuid4().hex[:10].upper()}",
        "astronaut_id": astronaut_id,
        "device_id": device["device_id"],
        "device_name": device["name"],
        "measurement_category": device["category"],
        "measurement_type": mkey,
        "value": round(num_val, 3) if num_val is not None else None,
        "value_text": val_text,
        "unit": unit_clean,
        "recorded_at": ts,
        "connection_method": connection_method,
        "data_source": data_source,
        "connection_status": connection_status,
        "quality_status": quality_status,
        "quality_note": quality_note,
        "confirmed": bool(confirmed and quality_status in (DeviceDataQuality.VALID.value, DeviceDataQuality.WARNING.value)),
        "telemetry_field": spec["telemetry_field"] if (spec and quality_status == DeviceDataQuality.VALID.value) else None,
        "metadata": meta,
    }


class BaseDeviceAdapter:
    """Modular adapter interface separating hardware probing, simulation, and import parsing."""

    def __init__(self, device: Dict[str, Any]) -> None:
        self.device = device

    def probe_live_interface(self) -> Tuple[bool, str]:
        """Truthfully report whether a documented physical hardware transport is present locally."""
        cls = self.device["integration_classification"]
        if cls == IntegrationClassification.NOT_INTEGRATED.value:
            return (
                False,
                f"{self.device['name']} is a scientific reference platform with no external API endpoint; local TARS Care evaluation handles analysis.",
            )
        return (
            False,
            f"No physical {self.device['name']} hardware or vendor serial/BLE bridge detected on this workstation. "
            f"TARS Care will never fabricate a live 'Connected' hardware state — use File Import or explicitly labeled Simulation Mode.",
        )

    def build_simulation_readings(
        self,
        astronaut_id: str,
        baseline: Dict[str, Any],
        mission_day: int,
    ) -> List[Dict[str, Any]]:
        return []

    def parse_import(
        self,
        raw_text: str,
        fmt: str,
        filename: str,
        astronaut_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parse CSV or JSON telemetry export rows with strict unit & schema validation."""
        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        text = raw_text.strip()
        if not text:
            return [], ["Uploaded file is empty."]

        raw_items: List[Dict[str, Any]] = []
        if fmt == "json":
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as exc:
                return [], [f"Invalid JSON syntax in {filename}: {exc}"]
            if isinstance(loaded, dict):
                if isinstance(loaded.get("measurements"), list):
                    raw_items = loaded["measurements"]
                else:
                    raw_items = [loaded]
            elif isinstance(loaded, list):
                raw_items = loaded
            else:
                return [], ["JSON payload must be an object or array of measurement objects."]
        else:
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                return [], ["CSV header row missing."]
            raw_items = list(reader)

        if not raw_items:
            return [], ["No data rows found in uploaded file."]

        # Map column-oriented single-row exports OR tidy (measurement_type, value, unit) rows
        wide_column_units = {
            "heart_rate_bpm": ("heart_rate", "BPM"),
            "respiratory_rate_bpm": ("respiratory_rate", "/min"),
            "spo2_pct": ("spo2", "%"),
            "body_temp_c": ("skin_or_body_temp", "°C"),
            "systolic_bp_mmhg": ("systolic_bp", "mmHg"),
            "diastolic_bp_mmhg": ("diastolic_bp", "mmHg"),
            "sleep_duration_hrs": ("sleep_duration", "hrs"),
            "sleep_quality_pct": ("sleep_quality", "%"),
            "physical_activity_mins": ("physical_activity", "mins"),
            "absorbed_dose_mgy": ("absorbed_dose", "mGy"),
            "equivalent_dose_rate_msv_day": ("equivalent_dose_rate", "mSv/day"),
            "cumulative_effective_dose_msv": ("cumulative_effective_dose", "mSv"),
            "neutron_bubble_count": ("neutron_bubble_count", "bubbles"),
            "balance_score": ("balance_score", "/100"),
            "exercise_performance_pct": ("exercise_performance", "%"),
            "ergometer_power_w": ("ergometer_power", "W"),
            "muscle_strength_idx": ("muscle_strength_index", "index"),
        }

        for idx, item in enumerate(raw_items[:40]):
            if not isinstance(item, dict):
                errors.append(f"Row {idx + 1}: expected object, got {type(item).__name__}")
                continue
            ts = str(item.get("recorded_at") or item.get("timestamp") or _now_iso())
            if "measurement_type" in item and "value" in item:
                m_item = validate_and_normalize_measurement(
                    astronaut_id=astronaut_id,
                    device=self.device,
                    measurement_type=str(item.get("measurement_type") or ""),
                    raw_value=item.get("value"),
                    unit=str(item.get("unit") or ""),
                    recorded_at=ts,
                    connection_method=f"File Import ({fmt.upper()}: {filename})",
                    data_source="imported_file",
                    connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                    confirmed=False,
                    metadata={"filename": filename, "row_index": idx + 1, "location": item.get("location")},
                )
                rows.append(m_item)
                if m_item["quality_status"] != DeviceDataQuality.VALID.value:
                    errors.append(f"Row {idx + 1} ({m_item['measurement_type']}): {m_item['quality_note']}")
            else:
                matched_any = False
                for col, (mtype, default_unit) in wide_column_units.items():
                    if col in item and str(item[col]).strip() != "":
                        matched_any = True
                        unit_override = str(item.get(f"{col}_unit") or default_unit)
                        m_item = validate_and_normalize_measurement(
                            astronaut_id=astronaut_id,
                            device=self.device,
                            measurement_type=mtype,
                            raw_value=item[col],
                            unit=unit_override,
                            recorded_at=ts,
                            connection_method=f"File Import ({fmt.upper()}: {filename})",
                            data_source="imported_file",
                            connection_status=DeviceConnectionStatus.DISCONNECTED.value,
                            confirmed=False,
                            metadata={"filename": filename, "row_index": idx + 1},
                        )
                        rows.append(m_item)
                        if m_item["quality_status"] != DeviceDataQuality.VALID.value:
                            errors.append(f"Row {idx + 1} ({col}): {m_item['quality_note']}")
                if not matched_any:
                    errors.append(
                        f"Row {idx + 1}: unrecognized schema. Include 'measurement_type,value,unit' columns or standard TARS Care column names."
                    )

        return rows, errors


class WearableSensorAdapter(BaseDeviceAdapter):
    """Generates calibrated simulation readings anchored around individual crew baselines."""

    def build_simulation_readings(
        self,
        astronaut_id: str,
        baseline: Dict[str, Any],
        mission_day: int,
    ) -> List[Dict[str, Any]]:
        now = _now_iso()
        did = self.device["device_id"]
        hr_base = float(baseline.get("baseline_hr_bpm", 60.0))
        sbp_base = float(baseline.get("baseline_systolic_mmhg", 112.0))
        dbp_base = float(baseline.get("baseline_diastolic_mmhg", 71.0))
        spo2_base = float(baseline.get("baseline_spo2_pct", 98.5))
        temp_base = float(baseline.get("baseline_temp_c", 36.6))
        sleep_base = float(baseline.get("baseline_sleep_hrs", 7.5))

        samples: List[Tuple[str, float, str, Dict[str, Any]]] = []
        if did == "ARCHER_ACTIGRAPHY":
            samples = [
                ("sleep_duration", round(max(4.5, sleep_base - 0.6), 1), "hrs", {"epoch_window": "Sol night cycle"}),
                ("sleep_quality", 81.0, "%", {"fragmentations": 2}),
                ("physical_activity", 68.0, "mins", {"intensity": "moderate_to_vigorous"}),
                ("activity_movement_index", 1420.0, "counts/min", {"axis": "3D vector"}),
            ]
        elif did == "CSA_BIO_MONITOR":
            samples = [
                ("heart_rate", round(hr_base + 5.0, 0), "BPM", {"channel": "CSA 1-lead Smart Shirt"}),
                ("respiratory_rate", 16.0, "/min", {"channel": "Thoracic RIP band"}),
                ("spo2", round(min(99.5, spo2_base - 0.3), 1), "%", {"channel": "Optical finger/headband"}),
                ("skin_or_body_temp", round(temp_base + 0.1, 1), "°C", {"channel": "Surface thermistor"}),
                ("activity_movement_index", 980.0, "counts/min", {"channel": "3-axis torso accelerometer"}),
            ]
        elif did == "BP_CUFF_CARDIOBREATH":
            samples = [
                ("systolic_bp", round(sbp_base + 4.0, 0), "mmHg", {"protocol": "CARDIOBREATH Seated Rest"}),
                ("diastolic_bp", round(dbp_base + 3.0, 0), "mmHg", {"protocol": "CARDIOBREATH Seated Rest"}),
                ("heart_rate", round(hr_base + 4.0, 0), "BPM", {"protocol": "Oscillometric pulse"}),
            ]

        return [
            validate_and_normalize_measurement(
                astronaut_id=astronaut_id,
                device=self.device,
                measurement_type=mtype,
                raw_value=val,
                unit=unit,
                recorded_at=now,
                connection_method=f"Simulated Hardware Demo · Sol {mission_day}",
                data_source="simulated",
                connection_status=DeviceConnectionStatus.SIMULATION.value,
                confirmed=False,
                metadata=meta,
            )
            for mtype, val, unit, meta in samples
        ]


class DosimetryInstrumentAdapter(BaseDeviceAdapter):
    """Radiation instrument adapter strictly preserving mGy vs. mSv units."""

    def build_simulation_readings(
        self,
        astronaut_id: str,
        baseline: Dict[str, Any],
        mission_day: int,
    ) -> List[Dict[str, Any]]:
        now = _now_iso()
        did = self.device["device_id"]
        samples: List[Tuple[str, float, str, Dict[str, Any]]] = []
        if did == "EVARM_MOSFET":
            samples = [
                ("absorbed_dose", 0.62, "mGy", {"body_location": "Eye Lens / Helmet Visor (EVA)"}),
                ("absorbed_dose", 0.54, "mGy", {"body_location": "Torso Skin / Blood-Forming Organ"}),
            ]
        elif did == "AUTO_BUBBLE_READER":
            samples = [
                ("neutron_bubble_count", 42.0, "bubbles", {"detector_serial": "RN2-MARS-08", "location": "Crew Quarters Rack 2"}),
                ("equivalent_dose_rate", 1.38, "mSv/day", {"radiation_type": "Secondary neutrons (quality weighted)"}),
            ]
        elif did == "CANS_SPECTROMETER":
            samples = [
                ("absorbed_dose", 0.51, "mGy", {"channel": "CANS Silicon/Plastic Tissue-Equivalent"}),
                ("equivalent_dose_rate", 1.44, "mSv/day", {"channel": "CANS Quality-Weighted Rate"}),
                ("cumulative_effective_dose", 169.2, "mSv", {"channel": "Mission Total Accumulated"}),
            ]
        return [
            validate_and_normalize_measurement(
                astronaut_id=astronaut_id,
                device=self.device,
                measurement_type=mtype,
                raw_value=val,
                unit=unit,
                recorded_at=now,
                connection_method=f"Simulated Dosimetry Adapter · Sol {mission_day}",
                data_source="simulated",
                connection_status=DeviceConnectionStatus.SIMULATION.value,
                confirmed=False,
                metadata=meta,
            )
            for mtype, val, unit, meta in samples
        ]


class TelemedicineMonitorAdapter(BaseDeviceAdapter):
    """Tempus Pro consolidated telemedicine triage packet simulator."""

    def build_simulation_readings(
        self,
        astronaut_id: str,
        baseline: Dict[str, Any],
        mission_day: int,
    ) -> List[Dict[str, Any]]:
        now = _now_iso()
        hr = float(baseline.get("baseline_hr_bpm", 60.0)) + 6.0
        sbp = float(baseline.get("baseline_systolic_mmhg", 112.0)) + 2.0
        dbp = float(baseline.get("baseline_diastolic_mmhg", 71.0)) + 2.0
        samples = [
            ("heart_rate", round(hr, 0), "BPM", {"ecg_summary": "Normal sinus rhythm (manual CMO verification required)"}),
            ("systolic_bp", round(sbp, 0), "mmHg", {"cuff_site": "Left Brachial"}),
            ("diastolic_bp", round(dbp, 0), "mmHg", {"cuff_site": "Left Brachial"}),
            ("spo2", 98.1, "%", {"perfusion_index": "nominal"}),
            ("respiratory_rate", 16.0, "/min", {"channel": "Impedance pneumography"}),
            ("skin_or_body_temp", 36.7, "°C", {"site": "Tympanic/oral probe"}),
        ]
        return [
            validate_and_normalize_measurement(
                astronaut_id=astronaut_id,
                device=self.device,
                measurement_type=mtype,
                raw_value=val,
                unit=unit,
                recorded_at=now,
                connection_method=f"Simulated Tempus Pro Bundle · Sol {mission_day}",
                data_source="simulated",
                connection_status=DeviceConnectionStatus.SIMULATION.value,
                confirmed=False,
                metadata=meta,
            )
            for mtype, val, unit, meta in samples
        ]


class GuidedPerformanceSimulationAdapter(BaseDeviceAdapter):
    """Optional simulation support ONLY for F2 Posturography & F3 Cycle Ergometer."""

    def build_simulation_readings(
        self,
        astronaut_id: str,
        baseline: Dict[str, Any],
        mission_day: int,
    ) -> List[Dict[str, Any]]:
        now = _now_iso()
        did = self.device["device_id"]
        samples: List[Tuple[str, float, str, Dict[str, Any]]] = []
        if did == "POSTUROGRAPHY_BALANCE":
            bal = max(55.0, float(baseline.get("baseline_balance_score", 94.0)) - 4.0)
            samples = [
                ("balance_score", round(bal, 1), "/100", {"protocol": "Tandem Stance Eyes Closed"}),
            ]
        elif did == "CYCLE_ERGOMETER_ASTROFIT":
            samples = [
                ("exercise_performance", 91.0, "%", {"protocol": "AstroFit Interval Set 35 mins"}),
                ("ergometer_power", 175.0, "W", {"cadence_rpm": 78}),
                ("physical_activity", 35.0, "mins", {"session_type": "CEVIS/Cycle Countermeasure"}),
            ]
        return [
            validate_and_normalize_measurement(
                astronaut_id=astronaut_id,
                device=self.device,
                measurement_type=mtype,
                raw_value=val,
                unit=unit,
                recorded_at=now,
                connection_method=f"Simulated Performance Hardware · Sol {mission_day}",
                data_source="simulated",
                connection_status=DeviceConnectionStatus.SIMULATION.value,
                confirmed=False,
                metadata=meta,
            )
            for mtype, val, unit, meta in samples
        ]


def get_device_adapter(device_id: str) -> BaseDeviceAdapter:
    """Resolve pluggable hardware adapter instance for the given device ID."""
    device = CATALOG_BY_ID.get(device_id)
    if not device:
        raise ValueError(f"Unknown medical device '{device_id}'")
    if device_id in ("ARCHER_ACTIGRAPHY", "CSA_BIO_MONITOR", "BP_CUFF_CARDIOBREATH"):
        return WearableSensorAdapter(device)
    if device_id in ("EVARM_MOSFET", "AUTO_BUBBLE_READER", "CANS_SPECTROMETER", "RADI_N2_BUBBLE"):
        return DosimetryInstrumentAdapter(device)
    if device_id == "TEMPUS_PRO":
        return TelemedicineMonitorAdapter(device)
    if device_id in ("POSTUROGRAPHY_BALANCE", "CYCLE_ERGOMETER_ASTROFIT"):
        return GuidedPerformanceSimulationAdapter(device)
    return BaseDeviceAdapter(device)
