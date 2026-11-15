export type RiskLevel = 'NORMAL' | 'WARNING' | 'CRITICAL';
export type MissionPhase = 'MICROGRAVITY_TRANSIT' | 'MARS_SURFACE' | 'EARTH_RETURN';
export type DataProvenance = 'REAL_RESEARCH_REF' | 'SYNTHETIC_DEMO' | 'USER_ENTERED' | 'SIMULATED_ENV';

export interface AstronautProfile {
  astronaut_id: string;
  name: string;
  role: string;
  age: number;
  mission_name: string;
  mission_day: number;
  current_phase: MissionPhase;
  gravity_g: number;
  baseline_hr_bpm: number;
  baseline_systolic_mmhg: number;
  baseline_diastolic_mmhg: number;
  baseline_spo2_pct: number;
  baseline_temp_c: number;
  baseline_sleep_hrs: number;
  baseline_sleep_quality_pct: number;
  baseline_mood_score: number;
  baseline_stress_score: number;
  baseline_muscle_strength_idx: number;
  baseline_balance_score: number;
  provenance: DataProvenance;
}

export interface TelemetryRecord {
  id?: number;
  timestamp: string;
  mission_day: number;
  mission_phase: MissionPhase;
  gravity_g: number;
  provenance: DataProvenance;
  absorbed_dose_mgy: number;
  absorbed_dose_rate_mgy_hr: number;
  equivalent_dose_msv: number;
  equivalent_dose_rate_msv_day: number;
  cumulative_effective_dose_msv: number;
  radiation_source: string;
  radiation_event_type: string;
  mood_score: number;
  stress_level: number;
  emotional_wellbeing: number;
  fatigue_level: number;
  workload_score: number;
  social_interaction_score: number;
  sleep_duration_hrs: number;
  sleep_quality_pct: number;
  sleep_schedule_window: string;
  sleep_irregularities: number;
  feeling_isolated: boolean;
  concentration_difficulty: boolean;
  motivation_level: number;
  heart_rate_bpm: number;
  systolic_bp_mmhg: number;
  diastolic_bp_mmhg: number;
  spo2_pct: number;
  respiratory_rate_bpm?: number;
  body_temp_c: number;
  dizziness_severity: number;
  faintness_presyncope: boolean;
  chest_discomfort?: boolean;
  palpitations?: boolean;
  shortness_of_breath?: boolean;
  reported_symptoms?: string[];
  physical_activity_mins: number;
  exercise_performance_pct: number;
  muscle_strength_idx: number;
  exercise_adherence_pct: number;
  musculoskeletal_discomfort: number;
  balance_score: number;
  coordination_score: number;
  spatial_disorientation: boolean;
  visual_disturbance_sans: boolean;
  cabin_temp_c: number;
  cabin_pressure_kpa: number;
  oxygen_pct: number;
  co2_mmhg: number;
  co2_ppm: number;
  humidity_pct: number;
  air_quality_index: number;
  env_warning_event: string;
  respiratory_symptoms: string[];
  infection_symptoms: string[];
  hygiene_adherence_pct: number;
  notes: string;
}

export interface BaselineComparison {
  metric: string;
  key: string;
  current: number;
  baseline: number;
  unit: string;
  delta: number;
  delta_pct: number;
  hazard: string;
}

export interface AssessmentFinding {
  hazard: string;
  severity: RiskLevel;
  title: string;
  detail: string;
  rule_type: string;
  ref_doc: string;
}

export interface RecommendationItem {
  hazard: string;
  priority: string;
  action: string;
  rationale: string;
  procedure_code: string;
  citation: string;
}

export interface ActiveAlert {
  id: string;
  hazard: string;
  severity: RiskLevel;
  message: string;
  action_required: string;
}

export interface BodyRegionMetric {
  name: string;
  value: string;
  baseline: string;
}

export interface BodyRegionAssessment {
  region_id: string;
  label: string;
  status: RiskLevel;
  hazards: string[];
  metrics: BodyRegionMetric[];
  summary: string;
  guidance: string;
  citation: string;
}

export interface RAGCitation {
  chunk_id: string;
  doc_id: string;
  title: string;
  agency: string;
  year: string;
  url: string;
  hazard_category: string;
  provenance: string;
  excerpt: string;
  relevance_score: number;
}

export interface RAGSectionItem {
  doc_id: string;
  title: string;
  agency: string;
  year: string;
  excerpt: string;
  provenance: string;
}

export interface RAGAnalysisResponse {
  query: string;
  engine_mode: string;
  model_used?: string | null;
  latency_ms?: number;
  sufficient_evidence: boolean;
  conflict_notice?: string | null;
  scientific_evidence?: RAGSectionItem[];
  operational_procedures?: RAGSectionItem[];
  answer: string;
  safety_notice: string;
  citations: RAGCitation[];
}

export interface GlanceSummary {
  overall_status: RiskLevel;
  how_am_i_doing: string;
  what_has_changed: string;
  should_i_take_action: string;
  provenance_label: string;
}

export interface MarsCareBodyRegionMeasurement {
  label: string;
  value: string;
  unit: string;
  baseline: string;
  recorded_at: string;
}

export interface MarsCareBodyRegion {
  id: string;
  name: string;
  status: RiskLevel;
  summary: string;
  measurements: MarsCareBodyRegionMeasurement[];
  recent_trend: { sol: number; value: number }[];
  trend_label: string;
  spaceflight_risk: string;
  action_label: string;
}

export interface HazardModule4Step {
  id: string;
  title: string;
  status: RiskLevel;
  provenance: string;
  what_are_we_monitoring: string;
  what_has_changed: string;
  why_it_matters_in_space: string;
  what_should_i_do_next: string;
}

export interface StructuredExplanation {
  what_was_detected: string[];
  contributing_measurements: string[];
  associated_factors: string[];
  relevant_hazard: string[];
  next_steps: string[];
}

export interface GuidanceTierItem {
  action: string;
  rationale: string;
  source: string;
}

export interface LocalAIStatus {
  ollama_available: boolean;
  ollama_reachable?: boolean;
  ollama_model: string | null;
  installed_chat_models?: string[];
  installed_embed_models?: string[];
  llm_enabled?: boolean;
  llm_active?: boolean;
  sentence_transformers_installed: boolean;
  sentence_transformers_cached: boolean;
  embeddings_loaded?: boolean;
  active_engine_mode: string;
  offline_guaranteed: boolean;
}

export interface CommModeInfo {
  mode: 'CONNECTED' | 'DELAYED' | 'OFFLINE';
  label: string;
  summary: string;
}

export interface EvaReadiness {
  status: 'GO' | 'CAUTION' | 'HOLD';
  score_pct: number;
  summary: string;
  blocking_factors: string[];
  advisory_factors: string[];
  pre_eva_checklist: { item: string; ok: boolean; detail: string }[];
}

export interface PredictiveRunways {
  disclaimer: string;
  co2: {
    current_mmhg: number;
    slope_per_sol: number;
    days_to_critical: number | null;
    warn_limit_mmhg: number;
    crit_limit_mmhg: number;
    summary: string;
    projected: { step: string; value: number }[];
  };
  radiation_budget: {
    cumulative_msv: number;
    rolling_avg_msv_day: number;
    warn_threshold_msv: number;
    reference_limit_msv: number;
    est_sols_to_warn: number;
    est_sols_to_limit: number;
    summary: string;
    projected: { step: string; value: number }[];
  };
  sleep_debt: {
    debt_7sol_hrs: number;
    estimated_recovery_nights: number;
    summary: string;
  };
  musculoskeletal: {
    current_strength_idx: number;
    slope_per_sol: number;
    summary: string;
  };
}

export interface SansAssessmentRecord {
  id?: number;
  crew_id?: string;
  timestamp: string;
  mission_day: number;
  eye_tested: 'LEFT' | 'RIGHT' | 'BOTH' | string;
  wavy_lines_detected: boolean;
  scotoma_cells: string[];
  near_acuity_shift: boolean;
  notes: string;
  provenance: DataProvenance;
}

export interface MedicalKitItem {
  id?: number;
  item_code: string;
  name: string;
  bay_location: string;
  category: string;
  quantity: number;
  unit: string;
  min_threshold: number;
  expiry_date: string;
  cmo_auth_required: boolean;
  notes: string;
  last_inspected: string;
}

export interface CrewFleetMember {
  crew_id: string;
  name: string;
  role: string;
  mission_day: number;
  overall_status: RiskLevel;
  eva_status: 'GO' | 'CAUTION' | 'HOLD';
  eva_score_pct: number;
  exercise_contraindicated: boolean;
  heart_rate_bpm: number;
  baseline_hr_bpm: number;
  hr_delta: number;
  bp_summary: string;
  spo2_pct: number;
  cumulative_dose_msv: number;
  sleep_duration_hrs: number;
  dizziness_severity: number;
  sans_flagged: boolean;
  flagged_hazards: string[];
  priority_headline: string;
  behavioral_checkins_count: number;
  private_reflections_redacted: boolean;
}

export interface IntegratedAssessment {
  overall_status: RiskLevel;
  mission_day: number;
  mission_phase: MissionPhase;
  gravity_g: number;
  provenance: DataProvenance;
  rule_disclaimer: string;
  exercise_contraindicated?: boolean;
  auto_emergency_recommended?: boolean;
  recommended_emergency_hazard?: string | null;
  protocol_gap_notice?: string | null;
  hazard_statuses: Record<string, RiskLevel>;
  baseline_comparisons: BaselineComparison[];
  findings: AssessmentFinding[];
  recommendations: RecommendationItem[];
  active_alerts: ActiveAlert[];
  body_regions: BodyRegionAssessment[];
  rag_analysis: RAGAnalysisResponse;
  comm_mode?: CommModeInfo;
  glance_summary?: GlanceSummary;
  marscare_body_regions?: MarsCareBodyRegion[];
  hazard_modules_4step?: HazardModule4Step[];
  structured_explanation?: StructuredExplanation;
  guidance_tiers?: Record<string, GuidanceTierItem[]>;
  eva_readiness?: EvaReadiness;
  predictive_runways?: PredictiveRunways;
  latest_sans?: SansAssessmentRecord | null;
  food_alerts?: FoodAlertItem[];
  nutrition_overview?: NutritionOverview;
  five_hazard_support_integration?: Record<string, { connected_modules: string[]; summary: string }>;
}

export interface BaselineHistoryItem {
  timestamp: string;
  reason: string;
  changed_fields: Record<string, { from: any; to: any }>;
}

export interface StoreForwardReport {
  id?: number;
  report_uid: string;
  created_at: string;
  synced_at: string | null;
  mission_day: number;
  title: string;
  summary: string;
  risk_level: RiskLevel;
  hazard_triggers: string[];
  transmission_status: string;
  provenance: DataProvenance;
  payload_json?: Record<string, any>;
}

export interface PsychQuestionnaireRecord {
  id?: number;
  timestamp: string;
  mission_day: number;
  emotional_condition_rating: number;
  psychological_stress_rating: number;
  motivation_rating: number;
  fatigue_rating: number;
  sleep_difficulty_rating: number;
  isolation_feeling_rating: number;
  concentration_workload_rating: number;
  journal_reflection: string;
  provenance: DataProvenance;
}

export interface KnowledgeDocItem {
  doc_id: string;
  title: string;
  agency: string;
  year: string;
  url: string;
  hazard_category: string;
  provenance: string;
  content: string;
}

export interface EmergencyProtocolResult {
  protocol_id: string;
  protocol_title: string;
  execution_mode: string;
  earth_comm_status: string;
  one_way_delay_minutes: number;
  round_trip_delay_minutes: number;
  severity: string;
  trigger_hazard: string;
  mission_phase: string;
  reported_symptoms: string[];
  vital_signs_summary: string;
  immediate_steps: string[];
  supporting_citation: string;
  protocol_gap_notice?: string;
  safety_disclaimer: string;
}

export interface SyncResponse {
  sync_result: {
    synchronized_count: number;
    remaining_queued: number;
    status: string;
    message?: string;
    synced_at?: string;
  };
  state: FullSystemState;
}

export interface FullSystemState {
  active_crew_id?: string;
  astronaut: AstronautProfile;
  baseline_history?: BaselineHistoryItem[];
  latest_telemetry: TelemetryRecord;
  telemetry_history: TelemetryRecord[];
  assessment: IntegratedAssessment;
  radiation_limits: {
    daily_equivalent_warn_msv: number;
    daily_equivalent_crit_msv: number;
    cumulative_mission_warn_msv: number;
    cumulative_mission_limit_msv: number;
    rule_classification: string;
  };
  environmental_limits: {
    cabin_temp_min_c: number;
    cabin_temp_max_c: number;
    cabin_pressure_min_kpa: number;
    cabin_pressure_max_kpa: number;
    o2_min_pct: number;
    o2_max_pct: number;
    co2_warn_mmhg: number;
    co2_crit_mmhg: number;
    humidity_min_pct: number;
    humidity_max_pct: number;
    aqi_warn: number;
    aqi_crit: number;
    rule_classification: string;
  };
  comm_state: {
    earth_comm_status: string;
    one_way_delay_minutes: number;
    round_trip_delay_minutes?: number;
    comm_condition?: string;
    mission_location?: string;
    mission_destination?: string;
    pending_messages_count?: number;
    distance_million_km: number;
    last_sync_timestamp: string;
    offline_mode_forced: boolean;
    pending_reports_count: number;
    dsn_note: string;
  };
  store_forward_reports: StoreForwardReport[];
  psych_questionnaires: PsychQuestionnaireRecord[];
  sans_assessments?: SansAssessmentRecord[];
  medical_kit?: MedicalKitItem[];
  crew_fleet_matrix?: CrewFleetMember[];
  privacy_pin_hint?: string;
  devices_catalog?: DeviceCatalogEntry[];
  device_states?: Record<string, DeviceConnectionState>;
  device_measurements?: DeviceMeasurementRecord[];
  hardware_examinations?: HardwareExamRecord[];
  biosample_records?: BiosampleRecord[];
  donki_state?: DonkiStateSummary;
  insight_state?: InsightStateSummary;
  food_state?: FoodAndSuppliesState;
  comm_centre_state?: CommCentreState;
  companion_state?: CompanionAndJournalState;
  knowledge_corpus: KnowledgeDocItem[];
  local_ai_status?: LocalAIStatus;
}

export interface DonkiServiceCatalogItem {
  id: string;
  name: string;
  endpoint: string;
  regime_scope: 'HELIOSPHERIC_DEEP_SPACE' | 'EARTH_MAGNETOSPHERE' | string;
  description: string;
}

export interface DonkiServiceStatusItem {
  status: 'OK' | 'RATE_LIMITED' | 'ERROR' | string;
  count: number;
  endpoint: string;
  synced_at: string;
  error: string;
}

export interface DonkiConfigSummary {
  key_status: string;
  key_source: string;
  using_custom_key: boolean;
  auto_advisory_in_eva: boolean;
  base_url: string;
  services_count: number;
}

export interface DonkiSyncMeta {
  last_sync_at: string;
  last_sync_status: 'NEVER_SYNCED' | 'SYNCED' | 'PARTIAL' | 'ERROR' | 'BLOCKED_OFFLINE' | string;
  last_sync_message: string;
  last_window: {
    start_date: string;
    end_date: string;
  };
  service_statuses: Record<string, DonkiServiceStatusItem>;
}

export interface DonkiAdvisorySummary {
  total_cached_events: number;
  sep_count: number;
  critical_flare_count: number;
  fast_cme_count: number;
  enlil_alert_count: number;
  earth_magnetosphere_count: number;
  advisories: string[];
  has_heliospheric_watch: boolean;
}

export interface DonkiEventItem {
  event_uid: string;
  service_type: string;
  activity_id: string;
  start_time: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO' | string;
  regime_scope: 'HELIOSPHERIC_DEEP_SPACE' | 'EARTH_MAGNETOSPHERE' | string;
  title: string;
  summary: string;
  linked_ids: string[];
  source_url: string;
  metrics: Record<string, unknown>;
  data_provenance: string;
  fetched_at: string;
}

export interface DonkiStateSummary {
  config: DonkiConfigSummary;
  services: DonkiServiceCatalogItem[];
  sync_meta: DonkiSyncMeta;
  service_counts: Record<string, number>;
  advisory_summary: DonkiAdvisorySummary;
  events: DonkiEventItem[];
}

export interface InsightStatSummary {
  av?: number;
  mn?: number;
  mx?: number;
  ct?: number;
}

export interface InsightWindBin {
  sector: number;
  compass_degrees: number;
  compass_point: string;
  compass_right: number;
  compass_up: number;
  ct: number;
}

export interface InsightWeatherSol {
  sol_id: string;
  first_utc: string;
  last_utc: string;
  season: string;
  northern_season: string;
  southern_season: string;
  month_ordinal?: number | null;
  at: InsightStatSummary;
  hws: InsightStatSummary;
  pre: InsightStatSummary;
  wd: {
    most_common?: {
      compass_degrees: number;
      compass_point: string;
      ct: number;
    } | null;
    bins?: InsightWindBin[];
  };
  validity: Record<string, { valid: boolean; hours_count: number }>;
  missing_sensors: string[];
  data_provenance: string;
  fetched_at: string;
}

export interface InsightStateSummary {
  config: {
    key_status: string;
    key_source: string;
    using_custom_key: boolean;
    endpoint?: string;
  };
  sync_meta: {
    last_sync_at: string;
    last_sync_status: 'NEVER_SYNCED' | 'SYNCED' | 'EMPTY_GAP' | 'RATE_LIMITED' | 'BLOCKED_OFFLINE' | 'ERROR' | string;
    last_sync_message: string;
    sol_keys: string[];
    endpoint: string;
  };
  summary: {
    sol_count: number;
    latest_sol_id?: string | null;
    landing_site: string;
    data_archive_notice: string;
    latest_pressure_pa?: number | null;
    latest_pressure_kpa?: number | null;
    latest_temp_av_c?: number | null;
    latest_temp_min_c?: number | null;
    latest_temp_max_c?: number | null;
    diurnal_temp_swing_c?: number | null;
    latest_wind_av_ms?: number | null;
    latest_wind_compass?: string | null;
    sols_with_missing_sensors: string[];
  };
  sols: InsightWeatherSol[];
}

export type IntegrationClassification =
  | 'SUPPORTED_CONNECTION'
  | 'IMPORT_SUPPORTED'
  | 'GUIDED_EXAMINATION'
  | 'SIMULATION_AVAILABLE'
  | 'NOT_INTEGRATED';

export type DeviceConnectionStatus =
  | 'not_connected'
  | 'connected'
  | 'simulation'
  | 'disconnected'
  | 'error'
  | 'unavailable';

export type DeviceDataQuality =
  | 'valid'
  | 'warning'
  | 'invalid_unit'
  | 'out_of_range'
  | 'incomplete';

export interface DeviceResearchRef {
  label: string;
  url: string;
  agency: string;
}

export interface DeviceCatalogEntry {
  device_id: string;
  code: string;
  name: string;
  category: 'wearables' | 'imaging' | 'dosimetry' | 'telemedicine' | 'biosamples' | 'behavioral_perf';
  category_label: string;
  illustration_type: string;
  measures: string[];
  how_it_works: string;
  body_systems: string[];
  research_references: DeviceResearchRef[];
  supported_outputs: string[];
  connection_methods: string[];
  integration_classification: IntegrationClassification;
  secondary_classifications?: IntegrationClassification[];
  capabilities: {
    supports_simulation: boolean;
    supports_import: boolean;
    supports_guided_exam: boolean;
    supports_biosample: boolean;
    is_countermeasure_only: boolean;
    is_wellbeing_activity: boolean;
  };
  limitations_notice: string;
}

export interface DeviceConnectionState {
  crew_id: string;
  device_id: string;
  connection_status: DeviceConnectionStatus;
  active_mode: string;
  last_error: string;
  last_measurement_at: string;
  updated_at: string;
}

export interface DeviceMeasurementRecord {
  id?: number;
  record_uid: string;
  crew_id?: string;
  astronaut_id: string;
  device_id: string;
  device_name: string;
  measurement_category: string;
  measurement_type: string;
  value: number | null;
  value_text?: string | null;
  unit: string;
  recorded_at: string;
  connection_method: string;
  data_source: string;
  connection_status: DeviceConnectionStatus;
  quality_status: DeviceDataQuality;
  quality_note: string;
  confirmed: boolean;
  telemetry_field?: string | null;
  metadata: Record<string, unknown>;
  created_at?: string;
}

export interface HardwareAttachmentItem {
  filename: string;
  mime_type: string;
  size_bytes: number;
  summary: string;
  content_preview: string;
}

export interface HardwareExamRecord {
  id?: number;
  exam_uid: string;
  crew_id?: string;
  device_id: string;
  device_name: string;
  exam_type: string;
  mission_day: number;
  recorded_at: string;
  data_source: string;
  findings: Record<string, unknown>;
  summary_note: string;
  abnormal_flag: boolean;
  abnormal_reason: string;
  attachments: HardwareAttachmentItem[];
  created_at?: string;
}

export interface BiosampleRecord {
  id?: number;
  sample_uid: string;
  crew_id?: string;
  device_id: string;
  device_name: string;
  specimen_type: string;
  collection_protocol: string;
  mission_day: number;
  collected_at: string;
  storage_location: string;
  status: string;
  notes: string;
  attachments: HardwareAttachmentItem[];
  assay_results: {
    filename?: string;
    format?: string;
    notes?: string;
    markers?: Record<string, unknown>[];
    provenance?: string;
  };
  assay_imported_at: string;
  created_at?: string;
}

// ============================================================================
// PART 1: FOOD & LIFE-SUPPORT SUPPLIES INTERFACES
// ============================================================================

export type FoodItemStatus = 'AVAILABLE' | 'RUNNING_LOW' | 'CRITICAL' | 'EXPIRING_SOON' | 'EXPIRED';

export interface FoodItemRecord {
  id?: number;
  item_uid: string;
  name: string;
  category: string;
  quantity: number;
  initial_quantity: number;
  serving_size: string;
  unit: string;
  calories_per_serving: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  water_ml_per_serving: number;
  micronutrients: Record<string, number>;
  nutrition_complete: boolean;
  storage_requirements: string;
  bay_location: string;
  expiry_sol: number;
  expiry_date: string;
  shelf_life_days: number;
  sols_until_expiry: number;
  added_sol: number;
  date_added: string;
  food_source: string;
  min_threshold: number;
  critical_threshold: number;
  daily_ration_per_astronaut: number;
  status: FoodItemStatus;
  provenance: string;
  notes: string;
  updated_at: string;
}

export interface FoodConsumptionRecord {
  id?: number;
  consumption_uid: string;
  crew_id: string;
  mission_day: number;
  meal_type: string;
  food_item_uid: string;
  food_name: string;
  category: string;
  quantity_consumed: number;
  unit: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  water_ml: number;
  micronutrients: Record<string, number>;
  is_estimated_nutrition: boolean;
  notes: string;
  provenance: string;
  recorded_at: string;
}

export interface ResupplyRecord {
  id?: number;
  resupply_uid: string;
  mission_day: number;
  event_type: string;
  food_item_uid: string;
  food_name: string;
  quantity_delta: number;
  quantity_after: number;
  unit: string;
  source: string;
  authorised_by: string;
  notes: string;
  provenance: string;
  recorded_at: string;
}

export interface SupplyProjectionResult {
  is_projection: boolean;
  projection_disclaimer: string;
  total_portions: number;
  astronaut_count: number;
  portions_per_astronaut_per_day: number;
  daily_crew_consumption_rate: number;
  estimated_remaining_days: number;
  projected_depletion_sol: number;
  projected_depletion_date: string;
  planned_mission_end_sol: number;
  mission_remaining_sols: number;
  next_resupply_sol: number | null;
  covers_until_resupply: boolean;
  covers_full_mission: boolean;
}

export interface CategorySupplyProjection {
  category: string;
  item_count: number;
  available_quantity: number;
  unit: string;
  configured_daily_crew_rate: number;
  effective_daily_crew_rate: number;
  estimated_remaining_days: number;
  projected_depletion_sol: number;
  projected_depletion_date: string;
  consumption_trend: 'ELEVATED_CONSUMPTION' | 'CONSERVING' | 'NOMINAL_STEADY' | string;
  status: RiskLevel;
  is_projection: boolean;
}

export interface NutritionTargets {
  crew_id: string;
  calories_target_kcal: number;
  protein_target_g: number;
  carbs_target_g: number;
  fat_target_g: number;
  water_target_ml: number;
  vitamin_d_target_iu: number;
  calcium_target_mg: number;
  notes: string;
  updated_at: string;
}

export interface NutritionOverview {
  crew_id: string;
  mission_day: number;
  targets: NutritionTargets;
  recorded: {
    calories_kcal: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
    water_ml: number;
    micronutrients: Record<string, number>;
    meals_logged_count: number;
    contains_estimated_values: boolean;
  };
  progress_pct: {
    calories: number;
    protein: number;
    carbs: number;
    fat: number;
    water: number;
  };
  explanations: string[];
  safety_disclaimer: string;
}

export interface FoodAlertItem {
  alert_uid: string;
  alert_type: string;
  severity: RiskLevel;
  affected_item_uid: string;
  affected_item_name: string;
  current_quantity: number;
  unit: string;
  recommended_action: string;
  timestamp: string;
}

export interface FoodAndSuppliesState {
  mission_config: {
    crew_count: number;
    current_mission_sol: number;
    planned_mission_end_sol: number;
    next_resupply_sol: number;
    next_resupply_label: string;
    portions_per_astronaut_per_day: number;
    water_liters_per_astronaut_per_day: number;
    water_warning_threshold_liters: number;
  };
  summary: {
    total_food_items: number;
    available_meal_portions: number;
    total_kcal_available: number;
    estimated_meal_supply_days: number;
    estimated_caloric_supply_days: number;
    potable_water_liters: number;
    estimated_water_supply_days: number;
    low_stock_count: number;
    expiring_soon_count: number;
    daily_food_consumption_kcal: number;
    daily_water_consumption_ml: number;
    provenance_note: string;
  };
  primary_meal_projection: SupplyProjectionResult;
  category_projections: CategorySupplyProjection[];
  nutrition_overview: NutritionOverview;
  items: FoodItemRecord[];
  low_stock_items: FoodItemRecord[];
  expiring_soon_items: FoodItemRecord[];
  food_alerts: FoodAlertItem[];
  consumption_history: FoodConsumptionRecord[];
  resupply_history: ResupplyRecord[];
}

// ============================================================================
// PART 2: DISTANCE FROM EARTH & MISSION COMMUNICATION INTERFACES
// ============================================================================

export interface CommScenarioPreset {
  scenario_id: string;
  label: string;
  mission_location: string;
  mission_destination: string;
  distance_million_km: number;
  one_way_delay_minutes: number;
  comm_condition: 'NORMAL' | 'DELAYED' | 'INTERMITTENT' | 'BLACKOUT' | string;
  earth_comm_status: string;
  offline_mode_forced: boolean;
  signal_quality_pct: number;
  bandwidth_kbps: number;
  relay_satellite: string;
  next_comm_window_utc: string;
  telemetry_source_type: string;
  explanation: string;
}

export type CommMessageStatus =
  | 'Draft'
  | 'Queued'
  | 'Waiting for Connection'
  | 'Sending'
  | 'Sent'
  | 'Failed';

export interface CommMessageRecord {
  id?: number;
  message_uid: string;
  crew_id: string;
  sender_name: string;
  recipient: string;
  message_type: string;
  priority: 'NORMAL' | 'IMPORTANT' | 'URGENT' | string;
  subject: string;
  body: string;
  status: CommMessageStatus;
  one_way_delay_minutes: number;
  round_trip_delay_minutes: number;
  distance_million_km: number;
  created_at: string;
  updated_at: string;
  sent_at?: string | null;
  acknowledged_at?: string | null;
  retry_count: number;
  failure_reason: string;
  linked_report_uid: string;
  provenance: string;
}

export interface SyncHistoryRecord {
  id?: number;
  sync_uid: string;
  timestamp: string;
  mission_day: number;
  comm_condition: string;
  one_way_delay_minutes: number;
  round_trip_delay_minutes: number;
  distance_million_km: number;
  messages_attempted: number;
  messages_sent: number;
  messages_failed: number;
  reports_synced: number;
  status: string;
  summary: string;
}

export interface CommCentreState {
  mission_location: string;
  mission_destination: string;
  scenario_id: string;
  comm_condition: 'NORMAL' | 'DELAYED' | 'INTERMITTENT' | 'BLACKOUT' | string;
  earth_comm_status: string;
  offline_mode_forced: boolean;
  distance_million_km: number;
  distance_au: number;
  one_way_delay_minutes: number;
  round_trip_delay_minutes: number;
  signal_quality_pct: number;
  bandwidth_kbps: number;
  relay_satellite: string;
  last_successful_comm: string;
  last_sync_timestamp: string;
  next_comm_window_utc: string;
  telemetry_source_type: string;
  pending_messages_count: number;
  draft_messages_count: number;
  unsent_health_reports_count: number;
  scenario_presets: CommScenarioPreset[];
  messages: CommMessageRecord[];
  sync_history: SyncHistoryRecord[];
  latency_explanation: string;
  local_vs_earth_capabilities: {
    available_locally_offline: string[];
    requires_earth_connectivity: string[];
  };
}

// ============================================================================
// PART 3: ISOLATION SUPPORT — PERSONAL JOURNAL & AI COMPANION INTERFACES
// ============================================================================

export interface JournalEntryRecord {
  id?: number;
  entry_uid: string;
  crew_id: string;
  mission_day: number;
  title: string;
  content: string;
  mood: string;
  feelings: string[];
  tags: string[];
  guided_prompt: string;
  is_private: boolean;
  allow_ai_access: boolean;
  provenance: string;
  created_at: string;
  updated_at: string;
}

export interface MoodCheckInRecord {
  id?: number;
  checkin_uid: string;
  crew_id: string;
  mission_day: number;
  mood: string;
  mood_numeric: number;
  feelings: string[];
  note: string;
  source: string;
  provenance: string;
  recorded_at: string;
}

export interface CompanionPrivacySettings {
  crew_id: string;
  allow_ai_journal_context: boolean;
  allow_ai_mood_context: boolean;
  allow_ai_mission_telemetry_context: boolean;
  store_companion_history: boolean;
  preferred_topics: string[];
  escalation_contact_role: string;
  escalation_procedure_note: string;
  updated_at: string;
}

export interface CompanionMessageRecord {
  id?: number;
  message_uid: string;
  conversation_uid?: string;
  crew_id?: string;
  role: 'user' | 'assistant';
  content: string;
  engine_used: string;
  safety_escalation_triggered: boolean;
  support_tier: string;
  suggested_coping: string[];
  created_at: string;
}

export interface CompanionConversationRecord {
  id?: number;
  conversation_uid: string;
  crew_id: string;
  title: string;
  conversation_mode: string;
  created_at: string;
  updated_at: string;
  messages: CompanionMessageRecord[];
}

export interface CompanionAndJournalState {
  crew_id: string;
  feature_title: string;
  privacy_settings: CompanionPrivacySettings;
  guided_reflection_prompts: string[];
  mood_levels: string[];
  feeling_tags: string[];
  journal_entries: JournalEntryRecord[];
  mood_checkins: MoodCheckInRecord[];
  mood_trend: {
    sol: number;
    mood: string;
    mood_numeric: number;
    feelings: string[];
    recorded_at: string;
  }[];
  conversations: CompanionConversationRecord[];
  local_ai_status: LocalAIStatus;
  non_diagnostic_disclaimer: string;
}


