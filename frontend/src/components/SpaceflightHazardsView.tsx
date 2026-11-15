import React, { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import {
  Activity,
  Eye,
  HelpCircle,
  MessageSquare,
  Radiation,
  Radio,
  Settings2,
  TrendingUp,
  Users,
  Wind,
} from 'lucide-react';
import { FullSystemState } from '../types';
import { apiRequest, gravityRegimeLabel, statusMeta } from './uiHelpers';
import { DonkiSpaceWeatherPanel } from './DonkiSpaceWeatherPanel';
import { GuideSection } from './HealthGuideModal';
import { InsightWeatherPanel } from './InsightWeatherPanel';

interface SpaceflightHazardsViewProps {
  state: FullSystemState;
  activeHazardId: string;
  onSelectHazard: (id: string) => void;
  onStateUpdated: (next: FullSystemState) => void;
  onAskAssistant: (prompt: string) => void;
  onOpenSansModal?: () => void;
  onNavigateModule?: (tab: string) => void;
  onOpenGuide?: (section?: GuideSection, stepId?: string) => void;
}

const HAZARD_META = [
  { id: 'radiation', label: 'Space Radiation', icon: Radiation },
  { id: 'isolation', label: 'Isolation & Confinement', icon: Users },
  { id: 'distance', label: 'Distance from Earth', icon: Radio },
  { id: 'gravity', label: 'Gravity Fields', icon: Activity },
  { id: 'environment', label: 'Hostile Environments', icon: Wind },
];

const GRAVITY_GUIDE: Record<string, { label: string; context: string; focus: string }> = {
  '1g': {
    label: '1g Earth Baseline',
    context: 'Full hydrostatic blood pressure gradient and skeletal weight-bearing load.',
    focus: 'Used as your personal reference for orthostatic heart rate, blood pressure, and posture.',
  },
  '0g': {
    label: '0g Microgravity Transit',
    context: 'Eliminates weight-bearing bone loading (CSA TBone) and shifts body fluid headward (CSA Vascular & SANS).',
    focus: 'Prioritize daily ARED resistive sets, aerobic cycle intervals, and vision/neuro-ocular screening.',
  },
  '0.38g': {
    label: '0.38g Mars Surface',
    context: 'Partial gravity reintroduces vertical loading on a cardiovascular system adapted to 0g.',
    focus: 'Monitor standing heart rate spikes, pre-hydrate with isotonic fluid, and maintain bone-loading cadence.',
  },
};

export const SpaceflightHazardsView: React.FC<SpaceflightHazardsViewProps> = ({
  state,
  activeHazardId,
  onSelectHazard,
  onStateUpdated,
  onAskAssistant,
  onOpenSansModal,
  onNavigateModule,
  onOpenGuide,
}) => {
  const modules = state.assessment.hazard_modules_4step || [];
  const activeMod = modules.find((m) => m.id === activeHazardId) || modules[0];

  const [gravityExplorer, setGravityExplorer] = useState<'1g' | '0g' | '0.38g'>(
    state.latest_telemetry.gravity_g === 0
      ? '0g'
      : state.latest_telemetry.gravity_g >= 0.9
        ? '1g'
        : '0.38g',
  );
  const [warnLimit, setWarnLimit] = useState(state.radiation_limits.daily_equivalent_warn_msv);
  const [co2Limit, setCo2Limit] = useState(state.environmental_limits.co2_warn_mmhg);
  const [savingLimits, setSavingLimits] = useState(false);
  const [limitNotice, setLimitNotice] = useState<string | null>(null);

  useEffect(() => {
    setWarnLimit(state.radiation_limits.daily_equivalent_warn_msv);
    setCo2Limit(state.environmental_limits.co2_warn_mmhg);
    setGravityExplorer(
      state.latest_telemetry.gravity_g === 0
        ? '0g'
        : state.latest_telemetry.gravity_g >= 0.9
          ? '1g'
          : '0.38g',
    );
  }, [
    state.radiation_limits.daily_equivalent_warn_msv,
    state.environmental_limits.co2_warn_mmhg,
    state.latest_telemetry.gravity_g,
  ]);

  const seriesMeta = useMemo(() => {
    if (activeHazardId === 'radiation') {
      return {
        title: '14-Sol Equivalent Rate (mSv/d) & Absorbed Dose (mGy/d)',
        primaryName: 'Equivalent (mSv/day)',
        secondaryName: 'Absorbed (mGy/day)',
      };
    }
    if (activeHazardId === 'isolation') {
      return {
        title: '14-Sol Sleep Duration (hrs) & Mood (/10)',
        primaryName: 'Sleep (hrs)',
        secondaryName: 'Mood (/10)',
      };
    }
    if (activeHazardId === 'gravity') {
      return {
        title: '14-Sol Resting HR (BPM) & Muscle Strength (%)',
        primaryName: 'Heart Rate (BPM)',
        secondaryName: 'Muscle Strength (%)',
      };
    }
    if (activeHazardId === 'environment') {
      return {
        title: '14-Sol Cabin CO₂ (mmHg) & Cabin Temp (°C)',
        primaryName: 'Cabin CO₂ (mmHg)',
        secondaryName: 'Cabin Temp (°C)',
      };
    }
    return {
      title: '14-Sol One-Way Signal Delay (min) & Sleep Quality (%)',
      primaryName: 'One-Way Delay (min)',
      secondaryName: 'Sleep Quality (%)',
    };
  }, [activeHazardId]);

  const chartData = useMemo(() => {
    const slice = state.telemetry_history.slice(-14);
    const counts: Record<number, number> = {};
    return slice.map((r) => {
      counts[r.mission_day] = (counts[r.mission_day] || 0) + 1;
      const solLabel =
        counts[r.mission_day] > 1 ? `S${r.mission_day}#${counts[r.mission_day]}` : `S${r.mission_day}`;
      if (activeHazardId === 'radiation') {
        return { solLabel, primary: r.equivalent_dose_rate_msv_day, secondary: r.absorbed_dose_mgy };
      }
      if (activeHazardId === 'isolation') {
        return { solLabel, primary: r.sleep_duration_hrs, secondary: r.mood_score };
      }
      if (activeHazardId === 'gravity') {
        return { solLabel, primary: r.heart_rate_bpm, secondary: r.muscle_strength_idx };
      }
      if (activeHazardId === 'environment') {
        return { solLabel, primary: r.co2_mmhg, secondary: r.cabin_temp_c };
      }
      return {
        solLabel,
        primary: state.comm_state.one_way_delay_minutes,
        secondary: r.sleep_quality_pct,
      };
    });
  }, [state.telemetry_history, activeHazardId, state.comm_state.one_way_delay_minutes]);

  const saveConfiguredLimits = async () => {
    setSavingLimits(true);
    setLimitNotice(null);
    try {
      await apiRequest('/api/config/limits', {
        method: 'POST',
        body: JSON.stringify({
          radiation_limits: {
            ...state.radiation_limits,
            daily_equivalent_warn_msv: warnLimit,
          },
          environmental_limits: {
            ...state.environmental_limits,
            co2_warn_mmhg: co2Limit,
          },
        }),
      });
      const fresh = await apiRequest<FullSystemState>('/api/state');
      onStateUpdated(fresh);
      setLimitNotice('Mission-configured alert thresholds updated (user-configured, not NASA-approved limits).');
    } catch (err) {
      setLimitNotice(err instanceof Error ? err.message : 'Unable to save configured limits.');
    } finally {
      setSavingLimits(false);
    }
  };

  if (!activeMod) return null;
  const meta = statusMeta(activeMod.status);
  const { latest_telemetry: latest } = state;

  return (
    <div className="space-y-6">
      {/* Hazard Selection Pills */}
      <section className="mc-card p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {HAZARD_META.map((hm) => {
            const Icon = hm.icon;
            const isSel = hm.id === activeMod.id;
            const modMatch = modules.find((m) => m.id === hm.id);
            const hStatus = statusMeta(modMatch?.status || 'NORMAL');
            return (
              <button
                key={hm.id}
                type="button"
                onClick={() => onSelectHazard(hm.id)}
                className={`px-4 py-2 rounded-full text-sm font-medium inline-flex items-center gap-2 transition-colors ${isSel
                  ? 'bg-[#EEF0F6] text-[#040404]'
                  : 'bg-[#0B0D1A] text-[#E5E5E4] border border-white/10 hover:text-[#FAF9FA]'
                  }`}
              >
                <Icon className="w-4 h-4" />
                <span>{hm.label}</span>
                <span className={`w-2 h-2 rounded-full ${hStatus.dotClass}`} />
              </button>
            );
          })}
        </div>
        <span className="text-xs text-[#E5E5E4]/75">{activeMod.provenance}</span>
      </section>

      {/* Main Hazard Header */}
      <section className="mc-card p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-[#FAF9FA]">{activeMod.title}</h1>
            <span className={`px-3 py-1 rounded-full text-xs font-semibold ${meta.badgeClass}`}>
              {meta.label}
            </span>
          </div>
          <p className="text-sm text-[#E5E5E4]/80 mt-1">
            Structured autonomous brief tailored for Mission Sol {latest.mission_day} · {gravityRegimeLabel(latest.gravity_g)}.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {onOpenGuide && (
            <button
              type="button"
              onClick={() => onOpenGuide('risks', 'hazards')}
              className="mc-btn-secondary px-4 py-2.5 text-sm inline-flex items-center gap-2"
            >
              <HelpCircle className="w-4 h-4 text-[#A5D8FF]" />
              <span>Explain Risks Simply</span>
            </button>
          )}
          <button
            type="button"
            onClick={() =>
              onAskAssistant(`Summarize current risks and guidance for ${activeMod.title} on Sol ${latest.mission_day}.`)
            }
            className="mc-btn-secondary px-4 py-2.5 text-sm inline-flex items-center gap-2"
          >
            <MessageSquare className="w-4 h-4 text-[#A5D8FF]" />
            <span>Ask AI Health Assistant</span>
          </button>
        </div>
      </section>

      {/* The 4 Consistent Sections Required by Design Brief */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Section 1: What are we monitoring? */}
        <div className="mc-card p-5 lg:p-6 space-y-4">
          <h2 className="text-lg font-semibold text-[#A5D8FF]">1. What are we monitoring?</h2>
          <p className="text-sm text-[#FAF9FA] leading-relaxed">{activeMod.what_are_we_monitoring}</p>

          {activeMod.id === 'radiation' && (
            <div className="grid grid-cols-3 gap-2.5 pt-1">
              <div className="rounded-xl bg-[#0B0D1A] p-3">
                <div className="text-xs text-[#E5E5E4]/75">Absorbed Dose</div>
                <div className="text-lg font-bold text-[#FAF9FA] tabular-data mt-0.5">
                  {latest.absorbed_dose_mgy.toFixed(2)} mGy
                </div>
                <div className="text-xs text-[#E5E5E4]/60">Physical energy</div>
              </div>
              <div className="rounded-xl bg-[#0B0D1A] p-3">
                <div className="text-xs text-[#E5E5E4]/75">Equivalent Rate</div>
                <div className="text-lg font-bold text-[#FAF9FA] tabular-data mt-0.5">
                  {latest.equivalent_dose_rate_msv_day.toFixed(2)} mSv/d
                </div>
                <div className="text-xs text-[#E5E5E4]/60">Bio-weighted</div>
              </div>
              <div className="rounded-xl bg-[#0B0D1A] p-3">
                <div className="text-xs text-[#E5E5E4]/75">Cumulative</div>
                <div className="text-lg font-bold text-[#FAF9FA] tabular-data mt-0.5">
                  {latest.cumulative_effective_dose_msv.toFixed(1)} mSv
                </div>
                <div className="text-xs text-[#E5E5E4]/60">Mission total</div>
              </div>
            </div>
          )}

          {activeMod.id === 'gravity' && (
            <div className="rounded-xl bg-[#0B0D1A] p-3.5 space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold text-[#A5D8FF]">Gravity Environment Explorer</span>
                <div className="flex gap-1">
                  {(['1g', '0g', '0.38g'] as const).map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGravityExplorer(g)}
                      className={`px-2.5 py-1 rounded-full text-xs font-semibold ${gravityExplorer === g
                        ? 'bg-[#EEF0F6] text-[#040404]'
                        : 'bg-[#121522] text-[#E5E5E4]/80'
                        }`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </div>
              <div className="text-sm font-medium text-[#FAF9FA]">{GRAVITY_GUIDE[gravityExplorer].label}</div>
              <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
                {GRAVITY_GUIDE[gravityExplorer].context}{' '}
                {state.assessment.exercise_contraindicated
                  ? 'EXERCISE HOLD ACTIVE: Suspend physical countermeasures until cardiopulmonary & critical triage flags resolve.'
                  : GRAVITY_GUIDE[gravityExplorer].focus}
              </p>
              {onOpenSansModal && (
                <div className="pt-2 border-t border-white/[0.07] flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-[#E5E5E4]/80">
                    SANS Vision:{' '}
                    {state.assessment.latest_sans
                      ? `Sol ${state.assessment.latest_sans.mission_day} (${state.assessment.latest_sans.wavy_lines_detected || state.assessment.latest_sans.scotoma_cells.length > 0 || state.assessment.latest_sans.near_acuity_shift ? 'Distortion / shift flagged' : 'Clear grid'})`
                      : 'No Amsler check recorded'}
                  </span>
                  <button
                    type="button"
                    onClick={onOpenSansModal}
                    className="mc-btn-secondary px-3 py-1.5 text-xs inline-flex items-center gap-1.5"
                  >
                    <Eye className="w-3.5 h-3.5 text-[#A5D8FF]" />
                    <span>Run SANS Amsler Check</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Section 2: What has changed? */}
        <div className="mc-card p-5 lg:p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-[#A5D8FF]">2. What has changed?</h2>
            <span className="text-xs text-[#E5E5E4]/75">{seriesMeta.title}</span>
          </div>
          <p className="text-sm text-[#FAF9FA] leading-relaxed">{activeMod.what_has_changed}</p>
          <div className="h-[195px] w-full rounded-xl bg-[#0B0D1A] p-3">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="hazArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#A5D8FF" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#A5D8FF" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="solLabel" stroke="#94a3b8" fontSize={11} />
                <YAxis yAxisId="left" stroke="#A5D8FF" fontSize={11} width={38} />
                <YAxis yAxisId="right" orientation="right" stroke="#FBBF24" fontSize={11} width={38} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#121522',
                    border: '1px solid rgba(165,216,255,0.35)',
                    borderRadius: '10px',
                    fontSize: '12px',
                    color: '#FAF9FA',
                  }}
                  labelFormatter={(s) => `Mission ${s}`}
                />
                <Legend wrapperStyle={{ fontSize: '11px', color: '#E5E5E4' }} />
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="primary"
                  name={seriesMeta.primaryName}
                  stroke="#A5D8FF"
                  strokeWidth={2}
                  fill="url(#hazArea)"
                />
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="secondary"
                  name={seriesMeta.secondaryName}
                  stroke="#FBBF24"
                  strokeWidth={1.8}
                  fillOpacity={0}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {state.assessment.predictive_runways && activeMod.id !== 'distance' && (
            <div className="rounded-xl bg-[#0B0D1A] border border-[#A5D8FF]/20 p-3 space-y-1">
              <div className="text-xs font-semibold text-[#A5D8FF] inline-flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5" />
                <span>Deterministic Predictive Runway</span>
              </div>
              <p className="text-xs text-[#E5E5E4]/90 leading-relaxed">
                {activeMod.id === 'radiation'
                  ? state.assessment.predictive_runways.radiation_budget.summary
                  : activeMod.id === 'isolation'
                    ? state.assessment.predictive_runways.sleep_debt.summary
                    : activeMod.id === 'gravity'
                      ? state.assessment.predictive_runways.musculoskeletal.summary
                      : state.assessment.predictive_runways.co2.summary}
              </p>
            </div>
          )}
        </div>

        {/* Section 3: Why does it matter in space? */}
        <div className="mc-card p-5 lg:p-6 space-y-3">
          <h2 className="text-lg font-semibold text-[#A5D8FF]">3. Why does it matter in space?</h2>
          <p className="text-sm text-[#FAF9FA] leading-relaxed">{activeMod.why_it_matters_in_space}</p>
          <div className="rounded-xl bg-[#0B0D1A] p-3.5 text-xs text-[#E5E5E4]/80 leading-relaxed">
            {activeMod.id === 'radiation'
              ? 'Distinction notice: Absorbed dose (Gy) is distinct from equivalent/effective dose (Sv). The NASA Radiation Data Portal (ARMAS) represents Earth atmosphere flights, not Mars surface exposure.'
              : activeMod.id === 'isolation'
                  ? 'Clinical safeguard: TARS Care tracks mood, stress, and sleep recovery trends without diagnosing depression, anxiety, or psychiatric conditions.'
                  : activeMod.id === 'environment'
                    ? 'Clinical safeguard: Correlates respiratory dryness or headaches with cabin CO₂/humidity and NASA OSDR/EDA guidance without auto-diagnosing infection.'
                    : 'Scientific alignment: Grounded in NASA Human Research Program (HRP) and Canadian Space Agency (CSA) studies (CCISS, CARDIOBREATH, C-STARS, TBone, Vascular).'}
          </div>
        </div>

        {/* Section 4: What should I do next? */}
        <div className="mc-card p-5 lg:p-6 space-y-4">
          <h2 className="text-lg font-semibold text-[#A5D8FF]">4. What should I do next?</h2>
          {state.assessment.exercise_contraindicated && (
            <div className="rounded-xl bg-red-500/15 border border-red-400/50 p-3 text-xs text-red-100 leading-relaxed">
              <span className="font-bold">EXERCISE HOLD ACTIVE: </span>
              Routine exercise protocols are suspended until active CRITICAL or cardiopulmonary flags resolve.
            </div>
          )}
          <p className="text-sm text-[#FAF9FA] leading-relaxed">{activeMod.what_should_i_do_next}</p>

          {(activeMod.id === 'radiation' || activeMod.id === 'environment') && (
            <div className="rounded-xl bg-[#0B0D1A] p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#E5E5E4]">
                <Settings2 className="w-4 h-4 text-[#A5D8FF]" />
                <span>Mission-Configured Demo Alert Threshold (Non-NASA Reference)</span>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {activeMod.id === 'radiation' ? (
                  <label htmlFor="hazard-warn-msv-input" className="flex items-center gap-2 text-xs text-[#E5E5E4]">
                    <span>Daily Equiv. Warn (mSv/day):</span>
                    <input
                      id="hazard-warn-msv-input"
                      name="hazard_warn_msv"
                      type="number"
                      step="0.1"
                      value={warnLimit}
                      onChange={(e) => setWarnLimit(parseFloat(e.target.value) || 1.2)}
                      className="w-24 rounded-lg bg-[#121522] border border-white/15 px-2.5 py-1.5 text-sm text-[#FAF9FA] tabular-data"
                    />
                  </label>
                ) : (
                  <label htmlFor="hazard-warn-co2-input" className="flex items-center gap-2 text-xs text-[#E5E5E4]">
                    <span>Cabin CO₂ Warn (mmHg):</span>
                    <input
                      id="hazard-warn-co2-input"
                      name="hazard_warn_co2"
                      type="number"
                      step="0.1"
                      value={co2Limit}
                      onChange={(e) => setCo2Limit(parseFloat(e.target.value) || 3.0)}
                      className="w-24 rounded-lg bg-[#121522] border border-white/15 px-2.5 py-1.5 text-sm text-[#FAF9FA] tabular-data"
                    />
                  </label>
                )}
                <button
                  type="button"
                  disabled={savingLimits}
                  onClick={saveConfiguredLimits}
                  className="mc-btn-secondary px-3.5 py-1.5 text-xs"
                >
                  {savingLimits ? 'Updating...' : 'Apply Config Limit'}
                </button>
              </div>
              {limitNotice && <p className="text-xs text-[#A5D8FF]">{limitNotice}</p>}
            </div>
          )}
        </div>
      </section>

      {activeMod.id === 'radiation' && (
        <DonkiSpaceWeatherPanel state={state} onStateUpdated={onStateUpdated} />
      )}
      {activeMod.id === 'environment' && (
        <InsightWeatherPanel state={state} onStateUpdated={onStateUpdated} />
      )}

      {/* Five-Hazard Integrated Support Modules Panel */}
      <section className="mc-card p-5 lg:p-6 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-[#FAF9FA]">
              Connected Astronaut Support Systems ({activeMod.title})
            </h2>
            <p className="text-xs text-[#8E95A8]">
              Integrates Food &amp; Life-Support Supplies, Distance from Earth Communication, and Personal Journal &amp; AI Companion into the Five-Hazard model.
            </p>
          </div>
          {onNavigateModule && (
            <div className="flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                onClick={() => onNavigateModule('food')}
                className="mc-btn-secondary px-3 py-1.5"
              >
                Open Food &amp; Supplies
              </button>
              <button
                type="button"
                onClick={() => onNavigateModule('comm')}
                className="mc-btn-secondary px-3 py-1.5"
              >
                Open Distance from Earth
              </button>
              <button
                type="button"
                onClick={() => onNavigateModule('companion')}
                className="mc-btn-primary px-3 py-1.5"
              >
                Open Personal Companion &amp; Journal
              </button>
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 text-xs">
          {Object.entries(state.assessment.five_hazard_support_integration || {}).map(
            ([hzName, info]) => (
              <div key={hzName} className="p-3 rounded-xl bg-[#0B0D1A] space-y-1">
                <div className="font-semibold text-[#FAF9FA]">{hzName}</div>
                <div className="text-[11px] text-[#A5D8FF]">
                  {info.connected_modules.join(' · ')}
                </div>
                <p className="text-[11px] text-[#E5E5E4]/80">{info.summary}</p>
              </div>
            )
          )}
        </div>
      </section>
    </div>
  );
};