import React, { useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from 'recharts';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clock,
  Eye,
  HeartPulse,
  HelpCircle,
  Moon,
  Radio,
  ShieldAlert,
  Thermometer,
  TrendingUp,
  Users,
  Wind,
} from 'lucide-react';
import { FullSystemState } from '../types';
import { InteractiveHumanBody } from './InteractiveHumanBody';
import { GuideSection } from './HealthGuideModal';
import { formatRecordedTime, gravityRegimeLabel, provenanceLabel, statusMeta } from './uiHelpers';

interface MissionOverviewViewProps {
  state: FullSystemState;
  selectedRegionId: string;
  onSelectRegion: (id: string) => void;
  onStartAssessment: (regionId?: string) => void;
  onOpenHazard: (hazardId: string) => void;
  onAskAssistant: (prompt: string) => void;
  onOpenEmergency: () => void;
  onOpenSansModal?: () => void;
  onOpenOps?: () => void;
  onOpenFoodSupplies?: () => void;
  onOpenCommCentre?: () => void;
  onOpenCompanion?: () => void;
  onOpenJournal?: () => void;
  onOpenGuide?: (section?: GuideSection, stepId?: string) => void;
}

type TrendTab = 'vitals' | 'sleep_mood' | 'radiation' | 'environment';

export const MissionOverviewView: React.FC<MissionOverviewViewProps> = ({
  state,
  selectedRegionId,
  onSelectRegion,
  onStartAssessment,
  onOpenHazard,
  onAskAssistant,
  onOpenEmergency,
  onOpenSansModal,
  onOpenOps,
  onOpenFoodSupplies,
  onOpenCommCentre,
  onOpenCompanion,
  onOpenJournal,
  onOpenGuide,
}) => {
  const [trendDays, setTrendDays] = useState<7 | 14 | 30>(14);
  const [trendTab, setTrendTab] = useState<TrendTab>('sleep_mood');

  const { latest_telemetry: latest, astronaut, assessment, telemetry_history } = state;
  const glance = assessment.glance_summary;
  const overallMeta = statusMeta(assessment.overall_status);
  const recordedTime = formatRecordedTime(latest.timestamp);

  const slicedHistory = useMemo(() => {
    const raw = telemetry_history.slice(-trendDays);
    const counts: Record<number, number> = {};
    return raw.map((row) => {
      counts[row.mission_day] = (counts[row.mission_day] || 0) + 1;
      return {
        ...row,
        solLabel: counts[row.mission_day] > 1 ? `Sol ${row.mission_day} (#${counts[row.mission_day]})` : `Sol ${row.mission_day}`,
      };
    });
  }, [telemetry_history, trendDays]);

  const bodyRegions = assessment.marscare_body_regions || [];

  const vitalCards = useMemo(() => {
    const hrDelta = Math.round(latest.heart_rate_bpm - astronaut.baseline_hr_bpm);
    const sbpDelta = Math.round(latest.systolic_bp_mmhg - astronaut.baseline_systolic_mmhg);
    const dbpDelta = Math.round(latest.diastolic_bp_mmhg - astronaut.baseline_diastolic_mmhg);
    const spo2Delta = latest.spo2_pct - astronaut.baseline_spo2_pct;
    const tempDelta = latest.body_temp_c - astronaut.baseline_temp_c;
    const sleepDelta = latest.sleep_duration_hrs - astronaut.baseline_sleep_hrs;
    const moodDelta = latest.mood_score - astronaut.baseline_mood_score;
    const stressDelta = latest.stress_level - astronaut.baseline_stress_score;
    return [
      {
        title: 'Heart Rate',
        value: `${Math.round(latest.heart_rate_bpm)}`,
        unit: 'BPM',
        baseline: `Baseline ${Math.round(astronaut.baseline_hr_bpm)} BPM (${hrDelta >= 0 ? '+' : ''}${hrDelta})`,
        time: recordedTime,
        regionId: 'heart',
        icon: HeartPulse,
        flag: Math.abs(hrDelta) >= 12 ? 'WARNING' : 'NORMAL',
      },
      {
        title: 'Blood Pressure',
        value: `${Math.round(latest.systolic_bp_mmhg)}/${Math.round(latest.diastolic_bp_mmhg)}`,
        unit: 'mmHg',
        baseline: `Baseline ${Math.round(astronaut.baseline_systolic_mmhg)}/${Math.round(astronaut.baseline_diastolic_mmhg)} (${sbpDelta >= 0 ? '+' : ''}${sbpDelta}/${dbpDelta >= 0 ? '+' : ''}${dbpDelta})`,
        time: recordedTime,
        regionId: 'heart',
        icon: Activity,
        flag: sbpDelta <= -10 || sbpDelta >= 20 ? 'WARNING' : 'NORMAL',
      },
      {
        title: 'Oxygen Saturation',
        value: `${latest.spo2_pct.toFixed(1)}`,
        unit: '%',
        baseline: `Baseline ${astronaut.baseline_spo2_pct.toFixed(1)}% (${spo2Delta >= 0 ? '+' : ''}${spo2Delta.toFixed(1)}%)`,
        time: recordedTime,
        regionId: 'lungs',
        icon: Wind,
        flag: spo2Delta <= -2.5 ? 'WARNING' : 'NORMAL',
      },
      {
        title: 'Body Temperature',
        value: `${latest.body_temp_c.toFixed(1)}`,
        unit: '°C',
        baseline: `Baseline ${astronaut.baseline_temp_c.toFixed(1)}°C (${tempDelta >= 0 ? '+' : ''}${tempDelta.toFixed(1)}°C)`,
        time: recordedTime,
        regionId: 'whole_body',
        icon: Thermometer,
        flag: Math.abs(tempDelta) >= 0.8 ? 'WARNING' : 'NORMAL',
      },
      {
        title: 'Sleep Duration',
        value: `${latest.sleep_duration_hrs.toFixed(1)}`,
        unit: 'hrs',
        baseline: `Baseline ${astronaut.baseline_sleep_hrs.toFixed(1)}h (${sleepDelta >= 0 ? '+' : ''}${sleepDelta.toFixed(1)}h)`,
        time: recordedTime,
        regionId: 'head_and_brain',
        icon: Moon,
        flag: sleepDelta <= -1.0 ? 'WARNING' : 'NORMAL',
      },
      {
        title: 'Mood & Stress',
        value: `M ${latest.mood_score.toFixed(1)} · S ${latest.stress_level.toFixed(1)}`,
        unit: '/10',
        baseline: `Mood ${latest.mood_score.toFixed(1)} (Base ${astronaut.baseline_mood_score.toFixed(1)}, ${moodDelta >= 0 ? '+' : ''}${moodDelta.toFixed(1)}) · Stress ${latest.stress_level.toFixed(1)} (Base ${astronaut.baseline_stress_score.toFixed(1)}, ${stressDelta >= 0 ? '+' : ''}${stressDelta.toFixed(1)})`,
        time: recordedTime,
        regionId: 'head_and_brain',
        icon: Activity,
        flag: stressDelta >= 2.2 || moodDelta <= -1.8 ? 'WARNING' : 'NORMAL',
      },
    ];
  }, [latest, astronaut, recordedTime]);

  const hazardSummaryCards = useMemo(() => {
    const hs = assessment.hazard_statuses || {};
    const mods = assessment.hazard_modules_4step || [];
    const statusFor = (id: string, fullKey: string) =>
      mods.find((m) => m.id === id)?.status || hs[fullKey] || 'NORMAL';
    return [
      {
        id: 'radiation',
        name: 'Space Radiation',
        status: statusFor('radiation', 'Space Radiation'),
        metric: `${latest.equivalent_dose_rate_msv_day.toFixed(2)} mSv/day`,
        sub: `${latest.absorbed_dose_mgy.toFixed(2)} mGy absorbed`,
      },
      {
        id: 'isolation',
        name: 'Isolation & Confinement',
        status: statusFor('isolation', 'Isolation and Confinement'),
        metric: `${latest.sleep_duration_hrs.toFixed(1)} hrs sleep`,
        sub: `Mood ${latest.mood_score.toFixed(1)} · Fatigue ${latest.fatigue_level.toFixed(1)}`,
      },
      {
        id: 'distance',
        name: 'Distance from Earth',
        status: statusFor('distance', 'Distance from Earth'),
        metric: assessment.comm_mode?.label || 'Delayed',
        sub: `${state.comm_state.one_way_delay_minutes} min one-way`,
      },
      {
        id: 'gravity',
        name: 'Gravity Fields',
        status: statusFor('gravity', 'Gravity Fields'),
        metric: gravityRegimeLabel(latest.gravity_g),
        sub: `Strength ${latest.muscle_strength_idx.toFixed(0)}% · Bal ${latest.balance_score.toFixed(0)}%`,
      },
      {
        id: 'environment',
        name: 'Hostile Environments',
        status: statusFor('environment', 'Hostile and Closed Environments'),
        metric: `${latest.co2_mmhg.toFixed(1)} mmHg CO₂`,
        sub: `O₂ ${latest.oxygen_pct.toFixed(1)}% · RH ${latest.humidity_pct.toFixed(0)}%`,
      },
    ];
  }, [assessment, latest, state.comm_state.one_way_delay_minutes]);

  return (
    <div className="space-y-6 lg:space-y-7">
      {/* 1. Crew Wayfinding Triage Band: Immediate 3-Question Health Glance */}
      <section
        aria-label="Crew Health Triage Overview"
        className="mc-card p-5 lg:p-6 border border-[#A5D8FF]/20"
      >
        <div className="grid grid-cols-1 md:grid-cols-3 min-[1520px]:grid-cols-[175px_1fr_1fr_1fr_205px] gap-4 lg:gap-5 items-stretch">
          {/* Sol & Context Anchor */}
          <div className="md:col-span-3 min-[1520px]:col-span-1 flex flex-wrap min-[1520px]:flex-col justify-between items-center min-[1520px]:items-start gap-3 pb-3 border-b border-white/[0.06] min-[1520px]:border-b-0 min-[1520px]:pb-0 min-[1520px]:pr-2">
            <div>
              <div className="text-sm text-[#E5E5E4]/80">Mission Sol</div>
              <div className="text-4xl lg:text-5xl font-bold text-[#FAF9FA] tabular-data tracking-tight">
                {latest.mission_day}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 mt-1">
              <span className="px-2.5 py-1 rounded-full text-xs bg-[#0B0D1A] text-[#A5D8FF] border border-[#A5D8FF]/30">
                {gravityRegimeLabel(latest.gravity_g)}
              </span>
              <span className="px-2.5 py-1 rounded-full text-xs bg-[#0B0D1A] text-[#E5E5E4] border border-white/10">
                {provenanceLabel(latest.provenance)}
              </span>
              {assessment.eva_readiness && (
                <span
                  className={`px-2.5 py-1 rounded-full text-xs font-bold border ${assessment.eva_readiness.status === 'HOLD'
                    ? 'bg-red-500/20 text-red-200 border-red-400/50'
                    : assessment.eva_readiness.status === 'CAUTION'
                      ? 'bg-amber-500/20 text-amber-200 border-amber-400/50'
                      : 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50'
                    }`}
                >
                  EVA: {assessment.eva_readiness.status} ({assessment.eva_readiness.score_pct}%)
                </span>
              )}
            </div>
          </div>

          {/* Question 1: How am I doing? */}
          <div className="rounded-xl bg-[#0B0D1A] p-4 h-full flex flex-col justify-between gap-2">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-[#A5D8FF]">How am I doing?</h2>
              <span className={`px-3 py-0.5 rounded-full text-xs font-semibold ${overallMeta.badgeClass}`}>
                {overallMeta.label}
              </span>
            </div>
            <p className="text-sm text-[#FAF9FA] leading-relaxed">
              {glance?.how_am_i_doing || 'Evaluation complete against your personal mission baseline.'}
            </p>
          </div>

          {/* Question 2: What has changed? */}
          <div className="rounded-xl bg-[#0B0D1A] p-4 h-full flex flex-col justify-between gap-2">
            <h2 className="text-sm font-semibold text-[#A5D8FF]">What has changed?</h2>
            <p className="text-sm text-[#E5E5E4] leading-relaxed">
              {glance?.what_has_changed || 'Monitoring 30-Sol physiological shifts.'}
            </p>
          </div>

          {/* Question 3: Should I take any action? */}
          <div className="rounded-xl bg-[#0B0D1A] p-4 h-full flex flex-col justify-between gap-2.5">
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-[#A5D8FF]">Should I take any action?</h2>
              <p className="text-sm text-[#E5E5E4] leading-relaxed">
                {glance?.should_i_take_action || 'Continue daily countermeasures and log check-ins.'}
              </p>
            </div>
            {assessment.exercise_contraindicated && (
              <div className="rounded-lg bg-red-500/15 border border-red-400/40 px-3 py-2 text-xs font-semibold text-red-200">
                Exercise Hold Active — Medical triage priority before physical countermeasures
              </div>
            )}
          </div>

          {/* Action CTA Column */}
          <div className="md:col-span-3 min-[1520px]:col-span-1 flex flex-wrap min-[1520px]:flex-col items-center min-[1520px]:items-stretch justify-end gap-3 pt-1 min-[1520px]:pt-0">
            {(assessment.overall_status === 'CRITICAL' || assessment.auto_emergency_recommended) && (
              <button
                type="button"
                onClick={onOpenEmergency}
                className="w-full sm:w-auto min-[1520px]:w-full px-4 py-3 rounded-xl text-sm font-bold bg-red-500/20 hover:bg-red-500/30 border border-red-400/60 text-red-100 inline-flex items-center justify-center gap-2"
              >
                <ShieldAlert className="w-4 h-4 text-red-300" />
                <span>Launch Emergency Checklist</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => onStartAssessment(selectedRegionId)}
              className="mc-btn-primary w-full sm:w-auto min-[1520px]:w-full px-6 py-3 text-sm inline-flex items-center justify-center gap-2"
            >
              <span>Start Assessment</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            {onOpenGuide && (
              <button
                type="button"
                onClick={() => onOpenGuide('walkthrough', 'overview')}
                className="mc-btn-secondary w-full sm:w-auto min-[1520px]:w-full px-4 py-2 text-xs inline-flex items-center justify-center gap-1.5"
              >
                <HelpCircle className="w-3.5 h-3.5 text-[#A5D8FF]" />
                <span>How to Assess</span>
              </button>
            )}
            {assessment.overall_status === 'WARNING' && !assessment.auto_emergency_recommended && (
              <button
                type="button"
                onClick={onOpenEmergency}
                className="mc-btn-secondary w-full sm:w-auto min-[1520px]:w-full px-4 py-2.5 text-xs inline-flex items-center justify-center gap-1.5"
              >
                <ShieldAlert className="w-3.5 h-3.5 text-amber-300" />
                <span>Onboard Protocol</span>
              </button>
            )}
          </div>
        </div>
      </section>

      {/* 2. Centerpiece Feature: Interactive Human Body */}
      <InteractiveHumanBody
        regions={bodyRegions}
        selectedRegionId={selectedRegionId}
        onSelectRegion={onSelectRegion}
        onStartAssessment={(id) => onStartAssessment(id)}
        onAskAssistant={onAskAssistant}
      />

      {/* 2b. EVA Suit Readiness & Deterministic Predictive Threshold Runways */}
      {(assessment.eva_readiness || assessment.predictive_runways) && (
        <section
          aria-label="EVA Readiness and Predictive Threshold Runways"
          className="grid grid-cols-1 xl:grid-cols-12 gap-5 lg:gap-6"
        >
          {assessment.eva_readiness && (
            <div className="xl:col-span-5 mc-card p-5 lg:p-6 space-y-4 flex flex-col justify-between">
              <div className="space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold text-[#FAF9FA]">
                    Autonomous EVA Readiness
                  </h2>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold border ${assessment.eva_readiness.status === 'HOLD'
                      ? 'bg-red-500/20 text-red-200 border-red-400/50'
                      : assessment.eva_readiness.status === 'CAUTION'
                        ? 'bg-amber-500/20 text-amber-200 border-amber-400/50'
                        : 'bg-emerald-500/20 text-emerald-200 border-emerald-400/50'
                      }`}
                  >
                    {assessment.eva_readiness.status} · {assessment.eva_readiness.score_pct}%
                  </span>
                </div>
                <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
                  {assessment.eva_readiness.summary}
                </p>

                {assessment.eva_readiness.blocking_factors.length > 0 && (
                  <div className="rounded-xl bg-red-500/10 border border-red-400/35 p-2.5 text-xs text-red-200 space-y-1">
                    <div className="font-semibold">Hold Factors:</div>
                    {assessment.eva_readiness.blocking_factors.map((bf) => (
                      <div key={bf}>• {bf}</div>
                    ))}
                  </div>
                )}

                {assessment.eva_readiness.advisory_factors.length > 0 && (
                  <div className="rounded-xl bg-amber-500/10 border border-amber-400/30 p-2.5 text-xs text-amber-200 space-y-1">
                    <div className="font-semibold">Advisory Considerations:</div>
                    {assessment.eva_readiness.advisory_factors.map((af) => (
                      <div key={af}>• {af}</div>
                    ))}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                  {assessment.eva_readiness.pre_eva_checklist.slice(0, 4).map((ck) => (
                    <div
                      key={ck.item}
                      className="rounded-lg bg-[#0B0D1A] px-3 py-2.5 border border-white/[0.06] flex items-start gap-2 text-xs"
                    >
                      <CheckCircle2
                        className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${ck.ok ? 'text-emerald-400' : 'text-amber-300'}`}
                      />
                      <span className="text-[#E5E5E4] leading-snug" title={ck.detail}>
                        {ck.item}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2 pt-2 border-t border-white/[0.07]">
                {onOpenSansModal && (
                  <button
                    type="button"
                    onClick={onOpenSansModal}
                    className="mc-btn-secondary px-3.5 py-2 text-xs inline-flex items-center gap-1.5"
                  >
                    <Eye className="w-3.5 h-3.5 text-[#A5D8FF]" />
                    <span>Run SANS Amsler Check</span>
                  </button>
                )}
                {onOpenOps && (
                  <button
                    type="button"
                    onClick={onOpenOps}
                    className="mc-btn-secondary px-3.5 py-2 text-xs inline-flex items-center gap-1.5"
                  >
                    <Users className="w-3.5 h-3.5 text-[#A5D8FF]" />
                    <span>Crew Matrix &amp; Med Kit</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {assessment.predictive_runways && (
            <div className="xl:col-span-7 mc-card p-5 lg:p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold text-[#FAF9FA] inline-flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#A5D8FF]" />
                  <span>Deterministic Predictive Threshold Runways</span>
                </h2>
                <span className="text-xs text-[#A5D8FF]">Local linear projection</span>
              </div>
              <p className="text-xs text-[#E5E5E4]/75 leading-relaxed">
                {assessment.predictive_runways.disclaimer}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                <div className="rounded-xl bg-[#0B0D1A] p-4 border border-white/[0.06] space-y-1.5">
                  <div className="text-xs font-semibold text-[#A5D8FF]">Cabin CO₂ Slope</div>
                  <div className="text-sm font-bold text-[#FAF9FA] tabular-data">
                    {assessment.predictive_runways.co2.current_mmhg} mmHg (
                    {assessment.predictive_runways.co2.slope_per_sol >= 0 ? '+' : ''}
                    {assessment.predictive_runways.co2.slope_per_sol}/sol)
                  </div>
                  <p className="text-xs text-[#E5E5E4]/80 leading-relaxed">
                    {assessment.predictive_runways.co2.summary}
                  </p>
                </div>

                <div className="rounded-xl bg-[#0B0D1A] p-4 border border-white/[0.06] space-y-1.5">
                  <div className="text-xs font-semibold text-[#A5D8FF]">Cumulative Radiation Runway</div>
                  <div className="text-sm font-bold text-[#FAF9FA] tabular-data">
                    {assessment.predictive_runways.radiation_budget.cumulative_msv} /{' '}
                    {assessment.predictive_runways.radiation_budget.reference_limit_msv} mSv
                  </div>
                  <p className="text-xs text-[#E5E5E4]/80 leading-relaxed">
                    {assessment.predictive_runways.radiation_budget.summary}
                  </p>
                </div>

                <div className="rounded-xl bg-[#0B0D1A] p-4 border border-white/[0.06] space-y-1.5">
                  <div className="text-xs font-semibold text-[#A5D8FF]">7-Sol Sleep Debt Recovery</div>
                  <div className="text-sm font-bold text-[#FAF9FA] tabular-data">
                    {assessment.predictive_runways.sleep_debt.debt_7sol_hrs} hrs deficit ·{' '}
                    {assessment.predictive_runways.sleep_debt.estimated_recovery_nights} recovery nights
                  </div>
                  <p className="text-xs text-[#E5E5E4]/80 leading-relaxed">
                    {assessment.predictive_runways.sleep_debt.summary}
                  </p>
                </div>

                <div className="rounded-xl bg-[#0B0D1A] p-4 border border-white/[0.06] space-y-1.5">
                  <div className="text-xs font-semibold text-[#A5D8FF]">Musculoskeletal Countermeasure</div>
                  <div className="text-sm font-bold text-[#FAF9FA] tabular-data">
                    Strength Index {assessment.predictive_runways.musculoskeletal.current_strength_idx}% (
                    {assessment.predictive_runways.musculoskeletal.slope_per_sol >= 0 ? '+' : ''}
                    {assessment.predictive_runways.musculoskeletal.slope_per_sol}/sol)
                  </div>
                  <p className="text-xs text-[#E5E5E4]/80 leading-relaxed">
                    {assessment.predictive_runways.musculoskeletal.summary}
                  </p>
                </div>
              </div>
            </div>
          )}
        </section>
      )}

      {/* 3. Latest Vital Signs vs Personal Baseline */}
      <section aria-label="Latest Vital Signs">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl font-semibold text-[#FAF9FA]">Vital Signs vs. Personal Baseline</h2>
            <p className="text-sm text-[#E5E5E4]/75 mt-1">
              Compares readings against {astronaut.name}&apos;s individual mission baseline rather than universal Earth reference ranges. Tap any card to focus its body system.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-[#E5E5E4]/75">
            <Clock className="w-3.5 h-3.5 text-[#A5D8FF]" />
            <span>Updated {recordedTime}</span>
          </span>
        </div>

        <div className="mb-4 rounded-2xl bg-[#121522] border border-[#A5D8FF]/20 px-4 py-3.5 text-xs text-[#E5E5E4]/85 leading-relaxed">
          <span className="font-semibold text-[#A5D8FF]">Baseline Recommendation: </span>
          Avoid arbitrary thresholds or assuming that ordinary Earth-based clinical reference ranges automatically represent safe operating limits under current {gravityRegimeLabel(latest.gravity_g)} conditions. Status flags measure relative drift from personal mission baselines alongside mission-configured prototype safety rules.
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-4">
          {vitalCards.map((vc) => {
            const Icon = vc.icon;
            const flagMeta = statusMeta(vc.flag);
            return (
              <button
                key={vc.title}
                type="button"
                onClick={() => onSelectRegion(vc.regionId)}
                className="mc-card p-5 text-left hover:border-[#A5D8FF]/45 transition-colors flex flex-col justify-between gap-3.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-[#E5E5E4] flex items-center gap-1.5">
                    <Icon className="w-4 h-4 text-[#A5D8FF]" />
                    <span>{vc.title}</span>
                  </span>
                  <span className={`w-2 h-2 rounded-full ${flagMeta.dotClass}`} title={flagMeta.label} />
                </div>
                <div className="tabular-data">
                  <span className="text-2xl font-bold text-[#FAF9FA]">{vc.value}</span>
                  <span className="text-xs text-[#E5E5E4]/75 ml-1">{vc.unit}</span>
                </div>
                <div className="text-xs text-[#A5D8FF]/90 leading-relaxed">{vc.baseline}</div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 4. Five Spaceflight Hazard Overview Cards */}
      <section aria-label="Five Spaceflight Hazards Overview">
        <div className="flex items-center justify-between gap-2 mb-4">
          <div>
            <h2 className="text-xl font-semibold text-[#FAF9FA]">Five Spaceflight Hazards</h2>
            <p className="text-sm text-[#E5E5E4]/75 mt-1">
              Open any hazard module to inspect monitoring data, spaceflight effects, and guided actions.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
          {hazardSummaryCards.map((hc) => {
            const meta = statusMeta(hc.status);
            return (
              <button
                key={hc.id}
                type="button"
                onClick={() => onOpenHazard(hc.id)}
                className="mc-card p-5 text-left hover:border-[#A5D8FF]/45 transition-colors flex flex-col justify-between gap-3.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-[#FAF9FA] leading-snug">{hc.name}</span>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold shrink-0 ${meta.badgeClass}`}>
                    {meta.label}
                  </span>
                </div>
                <div>
                  <div className="text-base font-bold text-[#FAF9FA] tabular-data">{hc.metric}</div>
                  <div className="text-xs text-[#E5E5E4]/75 mt-1">{hc.sub}</div>
                </div>
                <div className="flex items-center justify-between text-xs font-medium text-[#A5D8FF] pt-2 border-t border-white/[0.06]">
                  <span>Open module</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 5. Interactive Health Trends (7, 14, or 30 Mission Days) + Important Alerts */}
      <section className="grid grid-cols-1 xl:grid-cols-[1.45fr_1fr] gap-6">
        {/* Left: Interactive 7 / 14 / 30 Sol Trends Chart */}
        <div className="mc-card p-5 lg:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div>
              <h2 className="text-xl font-semibold text-[#FAF9FA]">Mission Health Trends</h2>
              <p className="text-sm text-[#E5E5E4]/75">
                Interactive timeline across the last {trendDays} mission days (Simulated + User Entries)
              </p>
            </div>
            <div className="flex items-center gap-1.5 bg-[#0B0D1A] p-1 rounded-full border border-white/[0.08]">
              {([7, 14, 30] as const).map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setTrendDays(days)}
                  className={`px-3.5 py-1 rounded-full text-xs font-semibold transition-colors ${trendDays === days
                    ? 'bg-[#EEF0F6] text-[#040404]'
                    : 'text-[#E5E5E4] hover:text-[#FAF9FA]'
                    }`}
                >
                  {days} Days
                </button>
              ))}
            </div>
          </div>

          {/* Metric Series Selector */}
          <div className="flex flex-wrap gap-2 mb-4">
            {[
              { id: 'sleep_mood', label: 'Sleep, Mood & Stress' },
              { id: 'vitals', label: 'Heart Rate & SpO₂' },
              { id: 'radiation', label: 'Radiation (mSv vs mGy)' },
              { id: 'environment', label: 'CO₂, Temp & Humidity' },
            ].map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTrendTab(t.id as TrendTab)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-colors ${trendTab === t.id
                  ? 'bg-[#A5D8FF]/20 text-[#FAF9FA] border border-[#A5D8FF]'
                  : 'bg-[#0B0D1A] text-[#E5E5E4]/80 border border-white/[0.07] hover:text-[#FAF9FA]'
                  }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="h-[275px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={slicedHistory} margin={{ top: 8, right: 12, left: -8, bottom: 4 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis
                  dataKey="solLabel"
                  stroke="#94a3b8"
                  fontSize={12}
                />
                <YAxis
                  yAxisId="left"
                  stroke="#A5D8FF"
                  fontSize={11}
                  width={44}
                  unit={trendTab === 'sleep_mood' ? 'h' : ''}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#E5E5E4"
                  fontSize={11}
                  width={44}
                  domain={trendTab === 'sleep_mood' ? [0, 10] : ['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#121522',
                    border: '1px solid rgba(165,216,255,0.35)',
                    borderRadius: '12px',
                    fontSize: '12px',
                    color: '#FAF9FA',
                  }}
                  labelFormatter={(label) => `Mission ${label}`}
                />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '6px', color: '#E5E5E4' }} />
                {trendTab === 'sleep_mood' && (
                  <>
                    <ReferenceLine
                      yAxisId="left"
                      y={astronaut.baseline_sleep_hrs}
                      stroke="rgba(165,216,255,0.45)"
                      strokeDasharray="4 4"
                    />
                    <Line yAxisId="left" type="monotone" dataKey="sleep_duration_hrs" name="Sleep (hrs)" stroke="#A5D8FF" strokeWidth={2.5} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="mood_score" name="Mood (/10)" stroke="#34D399" strokeWidth={2} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="stress_level" name="Stress (/10)" stroke="#FBBF24" strokeWidth={2} dot={false} />
                  </>
                )}
                {trendTab === 'vitals' && (
                  <>
                    <ReferenceLine
                      yAxisId="left"
                      y={astronaut.baseline_hr_bpm}
                      stroke="rgba(165,216,255,0.45)"
                      strokeDasharray="4 4"
                    />
                    <Line yAxisId="left" type="monotone" dataKey="heart_rate_bpm" name="Heart Rate (BPM)" stroke="#A5D8FF" strokeWidth={2.5} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="spo2_pct" name="SpO₂ (%)" stroke="#E5E5E4" strokeWidth={2} dot={false} />
                  </>
                )}
                {trendTab === 'radiation' && (
                  <>
                    <Line yAxisId="left" type="monotone" dataKey="equivalent_dose_rate_msv_day" name="Equivalent Rate (mSv/day)" stroke="#A5D8FF" strokeWidth={2.5} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="absorbed_dose_mgy" name="Absorbed Dose (mGy/day)" stroke="#E5E5E4" strokeWidth={2} dot={false} />
                  </>
                )}
                {trendTab === 'environment' && (
                  <>
                    <Line yAxisId="left" type="monotone" dataKey="co2_mmhg" name="Cabin CO₂ (mmHg)" stroke="#A5D8FF" strokeWidth={2.5} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="cabin_temp_c" name="Cabin Temp (°C)" stroke="#FBBF24" strokeWidth={2} dot={false} />
                    <Line yAxisId="right" type="monotone" dataKey="humidity_pct" name="Relative Humidity (%)" stroke="#E5E5E4" strokeWidth={2} dot={false} />
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right: Important Alerts & Prioritized Recommendations */}
        <div className="mc-card p-5 lg:p-6 flex flex-col justify-between gap-4">
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-xl font-semibold text-[#FAF9FA]">Important Alerts &amp; Actions</h2>
              <span className="text-xs text-[#E5E5E4]/75">
                {assessment.active_alerts.length} alerts · {assessment.recommendations?.length || 0} actions
              </span>
            </div>

            {assessment.exercise_contraindicated && (
              <div className="rounded-xl bg-red-500/15 border border-red-400/50 p-3 text-xs text-red-100 leading-relaxed">
                <span className="font-bold">EXERCISE CONTRAINDICATED: </span>
                Routine exercise countermeasures are automatically suspended while critical physiological flags or red-flag symptoms remain active.
              </div>
            )}

            {assessment.active_alerts.length === 0 ? (
              <div className="rounded-xl bg-[#0B0D1A] p-4 text-sm text-[#E5E5E4]">
                No threshold warnings active. All monitored systems are operating calmly within personal mission baselines.
              </div>
            ) : (
              <div className="space-y-3">
                {assessment.active_alerts.map((al) => {
                  const meta = statusMeta(al.severity);
                  return (
                    <div key={al.id} className="rounded-xl bg-[#0B0D1A] p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-[#FAF9FA] flex items-center gap-1.5">
                          <AlertTriangle className={`w-4 h-4 ${meta.textClass}`} />
                          <span>{al.hazard}</span>
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${meta.badgeClass}`}>
                          {meta.label}
                        </span>
                      </div>
                      <p className="text-xs text-[#E5E5E4] leading-relaxed">{al.message}</p>
                      <p className="text-xs text-[#A5D8FF] leading-relaxed">
                        Next step: {al.action_required}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}

            {assessment.recommendations && assessment.recommendations.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-white/[0.08]">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[#A5D8FF]">
                  Prioritized Action Stack
                </h3>
                <div className="space-y-2">
                  {assessment.recommendations.map((rec, idx) => (
                    <div
                      key={`${rec.hazard}-${idx}`}
                      className={`rounded-xl p-3 border text-xs leading-relaxed ${rec.priority === 'IMMEDIATE'
                        ? 'bg-red-500/10 border-red-400/40 text-red-100'
                        : rec.priority === 'HIGH'
                          ? 'bg-amber-500/10 border-amber-400/35 text-amber-100'
                          : 'bg-[#0B0D1A] border-white/[0.08] text-[#E5E5E4]'
                        }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="font-semibold">{rec.hazard}</span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${rec.priority === 'IMMEDIATE'
                            ? 'bg-red-500/25 text-red-200'
                            : rec.priority === 'HIGH'
                              ? 'bg-amber-500/25 text-amber-200'
                              : 'bg-white/10 text-[#E5E5E4]'
                            }`}
                        >
                          {rec.priority}
                        </span>
                      </div>
                      <p>{rec.action}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-white/[0.08] flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs text-[#E5E5E4]/75">
              <Radio className="w-3.5 h-3.5 text-[#A5D8FF]" />
              <span>Offline-ready autonomous logic</span>
            </span>
            <button
              type="button"
              onClick={onOpenEmergency}
              className="mc-btn-secondary px-4 py-2 text-xs"
            >
              Emergency Escalation Checklist
            </button>
          </div>
        </div>
      </section>

      {/* Quick-Access Support Modules: Food & Supplies, Distance from Earth, Personal Companion & Journal */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="mc-card p-5 lg:p-6 flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="text-base font-semibold text-[#FAF9FA]">
                Food &amp; Life-Support Supplies
              </h3>
              <span className="mc-pill shrink-0 bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                ~{state.food_state?.summary.estimated_meal_supply_days ?? 64.6} Sols Projected
              </span>
            </div>
            <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
              {state.food_state?.summary.available_meal_portions ?? 975} primary meal portions ·{' '}
              {state.food_state?.summary.potable_water_liters ?? 840} L water ·{' '}
              {state.food_state?.summary.low_stock_count ?? 1} low stock ·{' '}
              {state.food_state?.summary.expiring_soon_count ?? 2} expiring soon.
            </p>
          </div>
          <div className="flex items-center justify-between gap-3 pt-3 border-t border-white/[0.06] text-xs">
            <span className="text-[#8E95A8]">
              Sol {latest.mission_day}: {state.food_state?.summary.daily_food_consumption_kcal?.toFixed(0) ?? 1305} kcal logged
            </span>
            {onOpenFoodSupplies && (
              <button
                type="button"
                onClick={onOpenFoodSupplies}
                className="mc-btn-secondary px-3.5 py-2 text-xs inline-flex items-center gap-1 shrink-0"
              >
                <span>Open Food &amp; Supplies</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        <div className="mc-card p-5 lg:p-6 flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="text-base font-semibold text-[#FAF9FA]">
                Distance from Earth &amp; Message Centre
              </h3>
              <span className="mc-pill shrink-0 bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/30">
                {state.comm_centre_state?.one_way_delay_minutes ?? state.comm_state.one_way_delay_minutes}m OW /{' '}
                {state.comm_centre_state?.round_trip_delay_minutes ??
                  Number((state.comm_state.one_way_delay_minutes * 2).toFixed(1))}
                m RT
              </span>
            </div>
            <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
              {state.comm_centre_state?.distance_million_km ?? state.comm_state.distance_million_km}M km from Earth ·{' '}
              {state.comm_centre_state?.pending_messages_count ?? 1} pending message(s) ·{' '}
              {state.comm_centre_state?.unsent_health_reports_count ?? state.comm_state.pending_reports_count} unsent report(s).
            </p>
          </div>
          <div className="flex items-center justify-between gap-3 pt-3 border-t border-white/[0.06] text-xs">
            <span className="text-[#8E95A8]">
              Mode: {state.comm_centre_state?.comm_condition ?? 'DELAYED'}
            </span>
            {onOpenCommCentre && (
              <button
                type="button"
                onClick={onOpenCommCentre}
                className="mc-btn-secondary px-3.5 py-2 text-xs inline-flex items-center gap-1 shrink-0"
              >
                <span>Open Message Centre</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        <div className="mc-card p-5 lg:p-6 flex flex-col justify-between space-y-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="text-base font-semibold text-[#FAF9FA]">
                TARSCARE Personal Companion
              </h3>
              <span className="mc-pill shrink-0 bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                Always Here, Offline
              </span>
            </div>
            <p className="text-xs text-[#E5E5E4]/85 leading-relaxed">
              Private personal journal ({state.companion_state?.journal_entries.length ?? 3} entries), self-reported mood check-ins, and empathetic onboard AI companion.
            </p>
          </div>
          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-white/[0.06] text-xs">
            {onOpenJournal && (
              <button
                type="button"
                onClick={onOpenJournal}
                className="mc-btn-secondary px-3.5 py-2 text-xs"
              >
                My Journal
              </button>
            )}
            {onOpenCompanion && (
              <button
                type="button"
                onClick={onOpenCompanion}
                className="mc-btn-primary px-3.5 py-2 text-xs inline-flex items-center gap-1"
              >
                <span>Open Companion</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
};