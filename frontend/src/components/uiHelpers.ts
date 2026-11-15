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
    const raw = await res.text();
    let msg = raw;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.detail === 'string') {
        msg = parsed.detail;
      }
    } catch {
      // Keep plain text error body when not JSON
    }
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

export function deviceStatusMeta(status?: string): {
  label: string;
  badgeClass: string;
  dotClass: string;
} {
  const s = (status || 'not_connected').toLowerCase();
  if (s === 'connected') {
    return {
      label: 'Connected',
      badgeClass: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
      dotClass: 'bg-emerald-400',
    };
  }
  if (s === 'simulation') {
    return {
      label: 'Simulation Mode',
      badgeClass: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
      dotClass: 'bg-amber-400',
    };
  }
  if (s === 'error' || s === 'unavailable') {
    return {
      label: s === 'error' ? 'Connection Error' : 'Hardware Unavailable',
      badgeClass: 'bg-red-500/15 text-red-300 border border-red-500/30',
      dotClass: 'bg-red-400',
    };
  }
  if (s === 'disconnected') {
    return {
      label: 'Disconnected',
      badgeClass: 'bg-[#181C2E] text-[#E5E5E4]/85 border border-white/15',
      dotClass: 'bg-[#E5E5E4]/50',
    };
  }
  return {
    label: 'Not Connected',
    badgeClass: 'bg-[#181C2E] text-[#E5E5E4]/80 border border-white/15',
    dotClass: 'bg-[#E5E5E4]/40',
  };
}

export function classificationMeta(cls: string): {
  label: string;
  badgeClass: string;
} {
  switch (cls) {
    case 'SUPPORTED_CONNECTION':
      return {
        label: 'Supported Connection',
        badgeClass: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
      };
    case 'SIMULATION_AVAILABLE':
      return {
        label: 'Simulation Available',
        badgeClass: 'bg-[#181C2E] text-[#A5D8FF] border border-[#A5D8FF]/30',
      };
    case 'IMPORT_SUPPORTED':
      return {
        label: 'Import Supported',
        badgeClass: 'bg-[#181C2E] text-[#FAF9FA] border border-white/20',
      };
    case 'GUIDED_EXAMINATION':
      return {
        label: 'Guided Examination',
        badgeClass: 'bg-[#181C2E] text-[#E5E5E4] border border-white/15',
      };
    default:
      return {
        label: 'Not Integrated',
        badgeClass: 'bg-[#181C2E] text-[#E5E5E4]/65 border border-white/10',
      };
  }
}

export function deviceImportTemplate(deviceId: string): string {
  switch (deviceId) {
    case 'CSA_BIO_MONITOR':
      return 'measurement_type,value,unit,recorded_at\nheart_rate,74,BPM,2026-11-15T08:00:00Z\nrespiratory_rate,16,/min,2026-11-15T08:00:00Z\nspo2,98.2,%,2026-11-15T08:00:00Z\nphysical_activity,85,mins,2026-11-15T08:00:00Z';
    case 'BP_CUFF_CARDIOBREATH':
      return 'measurement_type,value,unit,recorded_at\nsystolic_bp,116,mmHg,2026-11-15T08:05:00Z\ndiastolic_bp,74,mmHg,2026-11-15T08:05:00Z';
    case 'ARCHER_ACTIGRAPHY':
      return 'measurement_type,value,unit,recorded_at\nsleep_duration,6.9,hrs,2026-11-15T07:30:00Z\nsleep_quality,82,%,2026-11-15T07:30:00Z\nphysical_activity,92,mins,2026-11-15T07:30:00Z';
    case 'EVARM_MOSFET':
      return 'measurement_type,value,unit,location,recorded_at\nabsorbed_dose,0.52,mGy,Left Torso EVA Badge,2026-11-15T09:15:00Z';
    case 'AUTO_BUBBLE_READER':
    case 'RADI_N2_BUBBLE':
      return 'measurement_type,value,unit,location,recorded_at\nneutron_bubble_count,18,bubbles,Columbus Rack 3,2026-11-15T09:30:00Z';
    case 'CANS_SPECTROMETER':
      return 'measurement_type,value,unit,recorded_at\nabsorbed_dose,0.49,mGy,2026-11-15T09:45:00Z\nequivalent_dose_rate,1.24,mSv/day,2026-11-15T09:45:00Z\ncumulative_effective_dose,169.6,mSv,2026-11-15T09:45:00Z';
    case 'TEMPUS_PRO':
      return 'measurement_type,value,unit,recorded_at\nheart_rate,72,BPM,2026-11-15T10:00:00Z\nsystolic_bp,114,mmHg,2026-11-15T10:00:00Z\ndiastolic_bp,73,mmHg,2026-11-15T10:00:00Z\nspo2,98.4,%,2026-11-15T10:00:00Z\nrespiratory_rate,15,/min,2026-11-15T10:00:00Z\nskin_or_body_temp,36.7,°C,2026-11-15T10:00:00Z';
    case 'POSTUROGRAPHY_BALANCE':
      return 'measurement_type,value,unit,recorded_at\nbalance_score,86,/100,2026-11-15T10:15:00Z';
    case 'CYCLE_ERGOMETER_ASTROFIT':
      return 'measurement_type,value,unit,recorded_at\nexercise_performance,91,%,2026-11-15T10:30:00Z\nergometer_power,175,W,2026-11-15T10:30:00Z\nphysical_activity,38,mins,2026-11-15T10:30:00Z';
    case 'TBONE_3D_SCANNER':
      return 'measurement_type,value,unit,recorded_at\ntbone_vbmd,312.4,mg HA/cm³,2026-11-15T11:00:00Z';
    default:
      return 'measurement_type,value,unit,recorded_at\nheart_rate,68,BPM,2026-11-15T08:00:00Z';
  }
}


