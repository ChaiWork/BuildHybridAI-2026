"""
Pydantic models and data schemas for TARS Care AI.
Enforces strict unit preservation (Gy vs. Sv, mmHg, kPa, ppm, °C),
explicit data provenance tags, configurable thresholds, and non-diagnostic safety metadata.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class DataProvenance(str, Enum):
    REAL_RESEARCH_REF = "REAL_RESEARCH_REF"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    USER_ENTERED = "USER_ENTERED"
    SIMULATED_ENV = "SIMULATED_ENV"


class MissionPhase(str, Enum):
    MICROGRAVITY_TRANSIT = "MICROGRAVITY_TRANSIT"
    MARS_SURFACE = "MARS_SURFACE"
    EARTH_RETURN = "EARTH_RETURN"


class RiskLevel(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AstronautBaseline(BaseModel):
    astronaut_id: str = "ARES-IV-SUCHAI"
    name: str = "SuChai"
    role: str = "Mission Commander & Crew Medical Officer"
    age: int = 41
    mission_name: str = "Ares-Horizon IV Deep Space Mars Expedition"
    mission_day: int = 184
    current_phase: MissionPhase = MissionPhase.MARS_SURFACE
    gravity_g: float = 0.38
    # Individual physiological baseline established pre-flight & early nominal transit
    baseline_hr_bpm: float = 58.0
    baseline_systolic_mmhg: float = 112.0
    baseline_diastolic_mmhg: float = 71.0
    baseline_spo2_pct: float = 98.5
    baseline_temp_c: float = 36.6
    baseline_sleep_hrs: float = 7.6
    baseline_sleep_quality_pct: float = 88.0
    baseline_mood_score: float = 8.2
    baseline_stress_score: float = 2.4
    baseline_muscle_strength_idx: float = 100.0
    baseline_balance_score: float = 95.0
    provenance: DataProvenance = DataProvenance.SYNTHETIC_DEMO


class BaselineUpdateInput(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    role: Optional[str] = Field(default=None, min_length=1, max_length=120)
    mission_day: Optional[int] = Field(default=None, ge=1, le=2000)
    current_phase: Optional[MissionPhase] = None
    gravity_g: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    baseline_hr_bpm: Optional[float] = Field(default=None, ge=35.0, le=140.0)
    baseline_systolic_mmhg: Optional[float] = Field(default=None, ge=75.0, le=180.0)
    baseline_diastolic_mmhg: Optional[float] = Field(default=None, ge=45.0, le=120.0)
    baseline_spo2_pct: Optional[float] = Field(default=None, ge=85.0, le=100.0)
    baseline_temp_c: Optional[float] = Field(default=None, ge=35.0, le=38.5)
    baseline_sleep_hrs: Optional[float] = Field(default=None, ge=3.0, le=12.0)
    baseline_mood_score: Optional[float] = Field(default=None, ge=1.0, le=10.0)
    baseline_stress_score: Optional[float] = Field(default=None, ge=1.0, le=10.0)
    baseline_muscle_strength_idx: Optional[float] = Field(default=None, ge=40.0, le=130.0)
    baseline_balance_score: Optional[float] = Field(default=None, ge=30.0, le=100.0)
    reason: Optional[str] = Field(default="Crew profile calibration", max_length=240)


class RadiationConfigLimits(BaseModel):
    daily_equivalent_warn_msv: float = Field(
        default=1.5,
        description="Mission-configured prototype daily warning threshold (mSv/day). Illustrative prototype rule, not a newly invented NASA legal standard.",
    )
    daily_equivalent_crit_msv: float = Field(
        default=5.0,
        description="Mission-configured prototype acute SPE daily threshold (mSv/day) triggering storm shelter protocol.",
    )
    cumulative_mission_warn_msv: float = Field(
        default=350.0,
        description="Mission-configured prototype cumulative warning threshold (mSv).",
    )
    cumulative_mission_limit_msv: float = Field(
        default=600.0,
        description="Reference career/mission effective dose ceiling (600 mSv NASA HRP reference benchmark).",
    )
    rule_classification: str = "MISSION_CONFIGURED_PROTOTYPE_RULE"


class EnvironmentalConfigLimits(BaseModel):
    cabin_temp_min_c: float = 18.5
    cabin_temp_max_c: float = 26.5
    cabin_pressure_min_kpa: float = 54.0
    cabin_pressure_max_kpa: float = 102.5
    o2_min_pct: float = 19.5
    o2_max_pct: float = 23.1
    co2_warn_mmhg: float = 3.0
    co2_crit_mmhg: float = 4.5
    humidity_min_pct: float = 30.0
    humidity_max_pct: float = 70.0
    aqi_warn: float = 50.0
    aqi_crit: float = 100.0
    rule_classification: str = "MISSION_CONFIGURED_PROTOTYPE_RULE"


class HealthMeasurementSubmission(BaseModel):
    mission_day: int = 184
    mission_phase: MissionPhase = MissionPhase.MARS_SURFACE
    gravity_g: float = 0.38
    provenance: DataProvenance = DataProvenance.USER_ENTERED

    # Module 1: Space Radiation
    absorbed_dose_mgy: float = Field(default=0.48, description="Absorbed physical dose in milliGray (mGy)")
    absorbed_dose_rate_mgy_hr: float = Field(default=0.020, description="Absorbed dose rate in mGy/hr")
    equivalent_dose_msv: float = Field(default=1.18, description="Biologically weighted equivalent dose in milliSievert (mSv)")
    equivalent_dose_rate_msv_day: float = Field(default=1.18, description="Equivalent dose rate in mSv/day")
    cumulative_effective_dose_msv: float = Field(default=168.4, description="Cumulative mission effective dose in mSv")
    radiation_source: str = Field(default="CREW_ACTIVE_DOSIMETER_BAND", description="Dosimeter source identifier")
    radiation_event_type: str = Field(default="GCR_BACKGROUND", description="GCR_BACKGROUND or SPE_SOLAR_STORM")

    # Module 2: Isolation & Confinement
    mood_score: float = Field(default=7.2, ge=1.0, le=10.0)
    stress_level: float = Field(default=4.1, ge=1.0, le=10.0)
    emotional_wellbeing: float = Field(default=7.4, ge=1.0, le=10.0)
    fatigue_level: float = Field(default=4.5, ge=1.0, le=10.0)
    workload_score: float = Field(default=6.5, ge=1.0, le=10.0)
    social_interaction_score: float = Field(default=7.5, ge=1.0, le=10.0)
    sleep_duration_hrs: float = Field(default=6.8, ge=0.0, le=16.0)
    sleep_quality_pct: float = Field(default=81.0, ge=0.0, le=100.0)
    sleep_schedule_window: str = Field(default="22:30 - 05:20 UTC-MARS")
    sleep_irregularities: int = Field(default=1, description="Number of awakenings or schedule shifts")
    feeling_isolated: bool = False
    concentration_difficulty: bool = False
    motivation_level: float = Field(default=7.8, ge=1.0, le=10.0)

    # Module 4: Gravity Fields & Physiological Adaptation
    heart_rate_bpm: float = Field(default=68.0, ge=30.0, le=220.0)
    systolic_bp_mmhg: float = Field(default=105.0, ge=60.0, le=220.0)
    diastolic_bp_mmhg: float = Field(default=68.0, ge=40.0, le=140.0)
    spo2_pct: float = Field(default=97.8, ge=70.0, le=100.0)
    respiratory_rate_bpm: float = Field(default=16.0, ge=6.0, le=45.0)
    body_temp_c: float = Field(default=36.7, ge=34.0, le=42.0)
    dizziness_severity: int = Field(default=1, ge=0, le=3, description="0=None, 1=Mild, 2=Moderate, 3=Severe")
    faintness_presyncope: bool = False
    chest_discomfort: bool = False
    palpitations: bool = False
    shortness_of_breath: bool = False
    physical_activity_mins: float = Field(default=95.0, ge=0.0, le=300.0)
    exercise_performance_pct: float = Field(default=91.0, ge=0.0, le=150.0)
    muscle_strength_idx: float = Field(default=93.5, ge=0.0, le=150.0)
    exercise_adherence_pct: float = Field(default=92.0, ge=0.0, le=100.0)
    musculoskeletal_discomfort: int = Field(default=1, ge=0, le=3)
    balance_score: float = Field(default=84.0, ge=0.0, le=100.0)
    coordination_score: float = Field(default=88.0, ge=0.0, le=100.0)
    spatial_disorientation: bool = False
    visual_disturbance_sans: bool = False

    # Module 5: Hostile & Closed Environments
    cabin_temp_c: float = Field(default=21.8)
    cabin_pressure_kpa: float = Field(default=70.3)
    oxygen_pct: float = Field(default=21.2)
    co2_mmhg: float = Field(default=2.8)
    co2_ppm: float = Field(default=3680.0)
    humidity_pct: float = Field(default=44.0)
    air_quality_index: float = Field(default=24.0)
    env_warning_event: str = Field(default="NONE")
    respiratory_symptoms: List[str] = Field(default_factory=list)
    infection_symptoms: List[str] = Field(default_factory=list)
    reported_symptoms: List[str] = Field(default_factory=list)
    hygiene_adherence_pct: float = Field(default=96.0)
    notes: str = Field(default="Routine Sol check-in following Martian surface EVA preparation.")


class PsychQuestionnaireInput(BaseModel):
    mission_day: int = 184
    emotional_condition_rating: int = Field(default=7, ge=1, le=10)
    psychological_stress_rating: int = Field(default=4, ge=1, le=10)
    motivation_rating: int = Field(default=8, ge=1, le=10)
    fatigue_rating: int = Field(default=5, ge=1, le=10)
    sleep_difficulty_rating: int = Field(default=3, ge=1, le=10)
    isolation_feeling_rating: int = Field(default=3, ge=1, le=10)
    concentration_workload_rating: int = Field(default=6, ge=1, le=10)
    journal_reflection: str = Field(default="")
    provenance: DataProvenance = DataProvenance.USER_ENTERED


class CommStatusUpdate(BaseModel):
    earth_comm_status: str = Field(
        default="NOMINAL_DELAYED",
        description="NOMINAL_DELAYED, HIGH_LATENCY_DEGRADED, or CONJUNCTION_BLACKOUT",
    )
    one_way_delay_minutes: float = Field(default=14.2)
    offline_mode_forced: bool = Field(default=False)


class StoreForwardReportCreate(BaseModel):
    title: str
    summary: str
    risk_level: RiskLevel
    hazard_triggers: List[str]
    payload_snapshot: Dict[str, Any]
    provenance: DataProvenance = DataProvenance.USER_ENTERED


class EmergencyEscalationInput(BaseModel):
    trigger_hazard: str = "Primary Medical Triage"
    severity: RiskLevel = RiskLevel.CRITICAL
    reported_symptoms: List[str] = Field(default_factory=list)
    vital_signs_summary: str = ""
    mission_phase: MissionPhase = MissionPhase.MARS_SURFACE


class RAGChatMessage(BaseModel):
    role: str
    content: str


class RAGQueryInput(BaseModel):
    question: str
    hazard_filter: Optional[str] = None
    include_astronaut_context: bool = True
    history: List[RAGChatMessage] = Field(default_factory=list)
    retrieval_only: bool = False


class SansAssessmentInput(BaseModel):
    mission_day: int = Field(default=184, ge=1, le=2000)
    eye_tested: str = Field(default="BOTH", pattern="^(LEFT|RIGHT|BOTH)$")
    wavy_lines_detected: bool = False
    scotoma_cells: List[str] = Field(default_factory=list)
    near_acuity_shift: bool = False
    notes: str = Field(default="", max_length=400)
    provenance: DataProvenance = DataProvenance.USER_ENTERED


class MedKitAdjustInput(BaseModel):
    item_code: str = Field(min_length=2, max_length=40)
    quantity_delta: Optional[int] = Field(default=None, ge=-20, le=20)
    set_quantity: Optional[int] = Field(default=None, ge=0, le=500)
    notes: Optional[str] = Field(default=None, max_length=240)
    mark_inspected: bool = False


class FlightSurgeonConsultInput(BaseModel):
    cmo_notes: str = Field(default="", max_length=1000)
    urgency: RiskLevel = RiskLevel.WARNING
    include_sans: bool = True


class CrewSelectInput(BaseModel):
    crew_id: str = Field(min_length=3, max_length=40)


class CrewPinVerifyInput(BaseModel):
    crew_id: str = Field(min_length=3, max_length=40)
    pin: str = Field(min_length=4, max_length=16)


class CrewPinUpdateInput(BaseModel):
    crew_id: str = Field(min_length=3, max_length=40)
    current_pin: str = Field(min_length=4, max_length=16)
    new_pin: str = Field(min_length=4, max_length=16)


class IntegrationClassification(str, Enum):
    SUPPORTED_CONNECTION = "SUPPORTED_CONNECTION"
    IMPORT_SUPPORTED = "IMPORT_SUPPORTED"
    GUIDED_EXAMINATION = "GUIDED_EXAMINATION"
    SIMULATION_AVAILABLE = "SIMULATION_AVAILABLE"
    NOT_INTEGRATED = "NOT_INTEGRATED"


class DeviceConnectionStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    SIMULATION = "simulation"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class DeviceDataQuality(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    INVALID_UNIT = "invalid_unit"
    OUT_OF_RANGE = "out_of_range"
    INCOMPLETE = "incomplete"


class DeviceConnectRequest(BaseModel):
    mode: str = Field(default="simulation", pattern="^(hardware|simulation)$")
    interface_hint: Optional[str] = Field(default=None, max_length=120)


class DeviceMeasurementReading(BaseModel):
    record_uid: Optional[str] = None
    astronaut_id: str = "ARES-IV-SUCHAI"
    device_id: str
    device_name: str
    measurement_category: str
    measurement_type: str
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: str
    recorded_at: str
    connection_method: str
    data_source: str = Field(
        default="simulated",
        description="simulated | imported_file | guided_examination | documented_adapter",
    )
    connection_status: DeviceConnectionStatus = DeviceConnectionStatus.SIMULATION
    quality_status: DeviceDataQuality = DeviceDataQuality.VALID
    quality_note: str = ""
    confirmed: bool = False
    telemetry_field: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryImportParseInput(BaseModel):
    format: str = Field(default="csv", pattern="^(csv|json)$")
    filename: str = Field(default="device_export.csv", max_length=160)
    raw_text: str = Field(min_length=2, max_length=250000)


class DeviceConfirmInput(BaseModel):
    measurements: List[DeviceMeasurementReading] = Field(default_factory=list, min_length=1, max_length=100)
    evaluate_health_assessment: bool = True
    notes: str = Field(default="", max_length=500)


class HardwareAttachmentItem(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    mime_type: str = Field(default="text/plain", max_length=80)
    size_bytes: int = Field(default=0, ge=0, le=2_500_000)
    summary: str = Field(default="", max_length=300)
    content_preview: str = Field(default="", max_length=120000)


class HardwareExamInput(BaseModel):
    mission_day: int = Field(default=184, ge=1, le=2000)
    summary: str = Field(default="", max_length=600)
    findings: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[HardwareAttachmentItem] = Field(default_factory=list, max_length=5)
    data_source: str = Field(default="guided_examination", max_length=40)
    confirmed: bool = True
    update_telemetry: bool = False


class BiosampleCreateInput(BaseModel):
    sample_type: str = Field(min_length=2, max_length=80)
    mission_day: int = Field(default=184, ge=1, le=2000)
    collected_at: Optional[str] = None
    storage_location: str = Field(default="Cold Stowage MELFI-B · Tray 2", max_length=120)
    notes: str = Field(default="", max_length=500)
    provenance: DataProvenance = DataProvenance.USER_ENTERED


class BiosampleAssayImportInput(BaseModel):
    raw_text: str = Field(min_length=2, max_length=150000)
    format: str = Field(default="json", pattern="^(csv|json)$")
    filename: str = Field(default="assay_results.json", max_length=160)
    notes: str = Field(default="", max_length=400)


class DonkiSyncRequest(BaseModel):
    start_date: Optional[str] = Field(default=None, max_length=20)
    end_date: Optional[str] = Field(default=None, max_length=20)
    services: Optional[List[str]] = None
    most_accurate_only: bool = True
    cme_speed: int = Field(default=500, ge=0, le=5000)
    cme_half_angle: int = Field(default=30, ge=0, le=180)
    catalog: str = Field(default="ALL", max_length=40)
    ips_location: str = Field(default="ALL", max_length=40)
    notification_type: str = Field(default="all", max_length=30)


class DonkiConfigInput(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=128)
    clear_api_key: bool = False
    auto_advisory_in_eva: Optional[bool] = None


class InsightSyncRequest(BaseModel):
    feedtype: str = Field(default="json", pattern="^json$")
    version: str = Field(default="1.0", max_length=12)



