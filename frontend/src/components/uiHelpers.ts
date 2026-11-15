import { DataProvenance, FullSystemState, LocalAIStatus, RiskLevel } from '../types';

export function statusMeta(status: RiskLevel | string | undefined): {
  label: string;
  badgeClass: string;
  dotClass: string;
  textClass: string;
} {
  const s = (status || 'NORMAL').toUpperCase();
  if (s === 'CRITICAL') {
    return {
      label: 'Critical',
      badgeClass: 'bg-red-500/15 text-red-400 border border-red-500/30',
      dotClass: 'bg-red-400',
      textClass: 'text-red-400',
    };
  }
  if (s === 'WARNING') {
    return {
      label: 'Warning',
      badgeClass: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
      dotClass: 'bg-amber-400',
      textClass: 'text-amber-300',
    };
  }
  return {
    label: 'Normal',
    badgeClass: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
    dotClass: 'bg-emerald-400',
    textClass: 'text-emerald-300',
  };
}

export function provenanceLabel(raw: DataProvenance | string | undefined): string {
  const r = String(raw || '').toUpperCase();
  if (r.includes('USER')) return 'User-Entered Data';
  if (r.includes('REAL')) return 'Real Research Data';
  if (r.includes('SIMULATED_ENV')) return 'Simulated Data (Environment)';
  return 'Simulated Data';
}

export function formatRecordedTime(iso: string | undefined): string {
  if (!iso) return 'Just now';
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }) + ' UTC';
  } catch {
    return iso;
  }
}

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface AIWarmupResponse {
  ok: boolean;
  model: string | null;
  latency_ms: number;
  message: string;
  status: LocalAIStatus;
}

export async function updateLocalAIConfig(
  payload: { llm_enabled?: boolean; selected_model?: string | null },
  onStateUpdated?: (state: FullSystemState) => void,
): Promise<LocalAIStatus> {
  const status = await apiRequest<LocalAIStatus>('/api/ai/config', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (onStateUpdated) {
    const fresh = await apiRequest<FullSystemState>('/api/state');
    onStateUpdated(fresh);
  }
  return status;
}

export async function warmupLocalAI(
  model?: string | null,
  onStateUpdated?: (state: FullSystemState) => void,
): Promise<AIWarmupResponse> {
  const res = await apiRequest<AIWarmupResponse>('/api/ai/warmup', {
    method: 'POST',
    body: JSON.stringify({ model: model || null }),
  });
  if (onStateUpdated) {
    const fresh = await apiRequest<FullSystemState>('/api/state');
    onStateUpdated(fresh);
  }
  return res;
}

export function gravityRegimeLabel(gravG: number | undefined): string {
  const g = typeof gravG === 'number' ? gravG : 0.38;
  if (g <= 0.05) return `Microgravity (${g.toFixed(2)}g)`;
  if (g < 0.8) return `Mars Partial Gravity (${g.toFixed(2)}g)`;
  return `Earth Gravity (${g.toFixed(2)}g)`;
}

export function buildEmergencyPayload(
  state: FullSystemState,
  triggerHazard = 'Primary Medical Triage',
  extraSymptoms: string[] = [],
) {
  const t = state.latest_telemetry;
  const symptoms = new Set<string>(extraSymptoms);
  if (t.chest_discomfort) symptoms.add('Chest pain / discomfort');
  if (t.palpitations) symptoms.add('Palpitations');
  if (t.shortness_of_breath) symptoms.add('Shortness of breath');
  if (t.faintness_presyncope) symptoms.add('Faintness / presyncope');
  if (t.dizziness_severity >= 1) symptoms.add(`Orthostatic dizziness (${t.dizziness_severity}/3)`);
  (t.reported_symptoms || []).forEach((s) => {
    if (s) symptoms.add(s);
  });
  (t.respiratory_symptoms || []).forEach((s) => {
    if (s) symptoms.add(s);
  });
  (t.infection_symptoms || []).forEach((s) => {
    if (s) symptoms.add(s);
  });

  const vitalSignsSummary = [
    `Sol ${t.mission_day}`,
    `HR ${Math.round(t.heart_rate_bpm)} bpm`,
    `BP ${Math.round(t.systolic_bp_mmhg)}/${Math.round(t.diastolic_bp_mmhg)} mmHg`,
    `SpO2 ${t.spo2_pct.toFixed(1)}%`,
    `RR ${Math.round(t.respiratory_rate_bpm ?? 16)}/min`,
    `Temp ${t.body_temp_c.toFixed(1)}°C`,
    `CO2 ${t.co2_mmhg.toFixed(2)} mmHg`,
    `Rad ${t.equivalent_dose_rate_msv_day.toFixed(2)} mSv/day (${t.absorbed_dose_mgy.toFixed(2)} mGy)`,
  ].join(' | ');

  return {
    trigger_hazard: triggerHazard,
    severity: state.assessment.overall_status === 'CRITICAL' ? 'CRITICAL' : 'WARNING',
    reported_symptoms: Array.from(symptoms),
    vital_signs_summary: vitalSignsSummary,
    mission_phase: state.latest_telemetry.mission_phase,
  };
}

export function buildClientFallbackEmergencyProtocol(
  state: FullSystemState | null,
  triggerHazard: string,
  extraSymptoms: string[] = [],
  backendError?: string,
) {
  const key = triggerHazard.toLowerCase();
  const payload = state
    ? buildEmergencyPayload(state, triggerHazard, extraSymptoms)
    : {
        trigger_hazard: triggerHazard,
        severity: 'CRITICAL',
        reported_symptoms: extraSymptoms,
        vital_signs_summary: 'Backend unavailable — verify live cuff BP, HR, SpO2, RR, and temperature on onboard CMO display.',
        mission_phase: 'MARS_SURFACE',
      };

  const isCardio = key.includes('cardiopulm') || key.includes('chest') || key.includes('palpitation');
  const isRad = key.includes('rad');
  const isEnv = key.includes('env') || key.includes('co2') || key.includes('resp');
  const isIso = key.includes('iso') || key.includes('sleep') || key.includes('psych');
  const isGrav = key.includes('grav') || key.includes('ortho') || key.includes('cardio');

  let protocolId = 'EMG-LOCAL-FALLBACK-00';
  let protocolTitle = 'Offline Autonomous CMO Primary Triage Protocol (Local Client Cache)';
  let steps = [
    '1. PRIMARY SURVEY (MARCH/ABCDE): Cease exertion; check airway, breathing (SpO2 & RR), circulation (HR/BP vs. personal baseline), and alertness.',
    '2. ONBOARD CMO & MEDICAL KIT CONTACT: Notify Crew Medical Officer and Mission Commander immediately; open physical Medical Operations Kit checklist.',
    '3. ENVIRONMENTAL CHECK: Confirm cabin O2, CO2, pressure, and radiation dosimeter readings directly on spacecraft displays.',
    '4. MANUAL RECORDING: Log time-stamped vitals and ECG strips locally; queue report once onboard API reconnects.',
  ];
  let citation = 'NASA-CSTARS-MED-01 / NASA-HRP-DIST-01';

  if (isCardio) {
    protocolId = 'EMG-CMO-CARDIOPULM-LOCAL';
    protocolTitle = 'Offline Cardiopulmonary Red-Flag & Chest Discomfort Checklist';
    steps = [
      '1. STOP EXERTION & REST: Immediately halt physical work or exercise; sit/recline in semi-Fowler supported posture.',
      '2. ACQUIRE ECG & REPEAT VITALS: Capture onboard 3-lead/12-lead ECG, bilateral BP, SpO2, and RR every 2–5 minutes.',
      '3. SUMMON CMO & MED KIT: Alert Crew Medical Officer and Mission Commander; open onboard emergency cardiac checklist.',
      '4. RULE OUT HYPOXIA / ECLSS FAILURE: Check O2/CO2; administer supplemental O2 per CMO kit ONLY if SpO2 < 94%. Do not auto-dose cardiac medications.',
    ];
    citation = 'CSA-CARDIO-CCISS-01 / NASA-CSTARS-MED-01';
  } else if (isRad) {
    protocolId = 'EMG-RAD-SPE-LOCAL';
    protocolTitle = 'Offline Solar Particle Event (SPE) Sheltering Checklist';
    steps = [
      '1. SHELTER IMMEDIATELY: Move all crew inside water-wall / high-hydrogen storm shelter within 5 minutes; cancel all EVAs.',
      '2. VERIFY DOSIMETRY: Cross-check personal dosimeters (mGy absorbed vs. mSv equivalent) against area TEPC hardware.',
      '3. NOTIFY CMO: Log acute nausea/fatigue/headache symptoms and prepare onboard 6-hr blood count per CMO procedure.',
    ];
    citation = 'NASA-HRP-RAD-01 / CSA-RAD-2026-01';
  } else if (isEnv) {
    protocolId = 'EMG-ENV-ECLSS-LOCAL';
    protocolTitle = 'Offline Habitat Atmospheric & Respiratory Emergency Checklist';
    steps = [
      '1. DON BREATHING PROTECTION: Use portable O2 mask if SpO2 < 94%, O2 < 19.5%, or CO2 > 4.5 mmHg.',
      '2. ECLSS SWITCHOVER: Switch CO2 scrubber (CDRA) to backup channel and inspect HEPA particulate filters.',
      '3. SUMMON CMO & LOG VITALS: Measure SpO2, respiratory rate, BP, and temperature; correlate across modules.',
    ];
    citation = 'NASA-HRP-ENV-01 / NASA-CSTARS-MED-01';
  } else if (isGrav) {
    protocolId = 'EMG-GRAV-ORTHO-LOCAL';
    protocolTitle = 'Offline Orthostatic Presyncope & Gravity Instability Checklist';
    steps = [
      '1. POSTURAL RESCUE: Place crewmember supine with legs elevated 30 degrees; abort all exertion/EVA.',
      '2. SUMMON CMO & MONITOR: Attach 3-lead ECG, SpO2, and BP cuff every 2 mins.',
      '3. ORAL ELECTROLYTES & COMPRESSION: Give 500 mL isotonic fluid only if fully alert and swallowing safely; apply compression garment.',
    ];
    citation = 'CSA-CARDIO-CCISS-01 / NASA-HRP-GRAV-01';
  } else if (isIso) {
    protocolId = 'EMG-ISO-CREW-LOCAL';
    protocolTitle = 'Offline Fatigue & Behavioral Safety Stand-Down Checklist';
    steps = [
      '1. OPERATIONAL STAND-DOWN: Pause high-criticality tasks (EVA, robotics, docking) immediately.',
      '2. CMO SUPPORTIVE CHECK-IN: Conduct private non-judgmental Crew Medical Officer / Commander check-in.',
      '3. PROTECTED SLEEP BLOCK: Establish dark, quiet, well-ventilated 9-hour rest block and redistribute workload.',
    ];
    citation = 'NASA-HRP-ISO-01 / NASA-CSTARS-MED-01';
  }

  return {
    protocol_id: protocolId,
    protocol_title: protocolTitle,
    execution_mode: 'CLIENT_LOCAL_DETERMINISTIC_FALLBACK',
    earth_comm_status: state?.comm_state?.earth_comm_status || 'OFFLINE_LOCAL_CACHE',
    one_way_delay_minutes: state?.comm_state?.one_way_delay_minutes ?? 14.2,
    round_trip_delay_minutes: Number(((state?.comm_state?.one_way_delay_minutes ?? 14.2) * 2).toFixed(1)),
    severity: payload.severity,
    trigger_hazard: payload.trigger_hazard,
    mission_phase: payload.mission_phase,
    reported_symptoms: payload.reported_symptoms,
    vital_signs_summary: payload.vital_signs_summary,
    immediate_steps: steps,
    supporting_citation: citation,
    protocol_gap_notice:
      (backendError ? `API error handled locally (${backendError}). ` : '') +
      'Executed from deterministic browser fallback checklist without Ollama or backend dependency. Physical CMO assessment and onboard kit verification remain mandatory.',
    safety_disclaimer:
      'Deterministic local client fallback active. Queue this incident packet manually once local backend sync restores.',
  };
}


