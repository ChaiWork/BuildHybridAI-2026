import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Download,
  Eye,
  EyeOff,
  FileText,
  Globe,
  Lock,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  Trash2,
  Unlock,
  Wifi,
  WifiOff,
  Clock,
} from 'lucide-react';
import { FullSystemState, SyncResponse } from '../types';
import {
  apiRequest,
  deviceStatusMeta,
  formatRecordedTime,
  gravityRegimeLabel,
  provenanceLabel,
  statusMeta,
} from './uiHelpers';
import { AIProviderSwitcher } from './AIProviderSwitcher';
import { DonkiSpaceWeatherPanel } from './DonkiSpaceWeatherPanel';
import { InsightWeatherPanel } from './InsightWeatherPanel';
import {
  HybridSuiteSnapshot,
  subscribeHybridSuite,
  syncFirebaseWithCommMode,
} from '../lib/firebaseHybridAI';

interface HistoryProps {
  state: FullSystemState;
  onStateUpdated: (next: FullSystemState) => void;
  unlockedCrewIds?: Record<string, boolean>;
  onUnlockCrew?: (crewId: string) => void;
  onLockCrew?: (crewId: string) => void;
}

export const HealthHistoryView: React.FC<HistoryProps> = ({
  state,
  onStateUpdated,
  unlockedCrewIds,
  onUnlockCrew,
  onLockCrew,
}) => {
  const [daysWindow, setDaysWindow] = useState<7 | 14 | 30>(30);
  const [provFilter, setProvFilter] = useState<'ALL' | 'SIMULATED' | 'USER'>('ALL');
  const [creatingReport, setCreatingReport] = useState(false);
  const [historyNotice, setHistoryNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [showJournals, setShowJournals] = useState(false);
  const [pinPromptOpen, setPinPromptOpen] = useState(false);
  const [pinInput, setPinInput] = useState('');
  const [pinBusy, setPinBusy] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);

  const activeCrewId = state.active_crew_id || state.astronaut.astronaut_id;
  const crewUnlocked = Boolean(unlockedCrewIds?.[activeCrewId]);
  const journalsVisible = crewUnlocked && showJournals;

  const handleTogglePrivateReflections = () => {
    if (journalsVisible) {
      setShowJournals(false);
      setPinPromptOpen(false);
      onLockCrew?.(activeCrewId);
      return;
    }
    if (crewUnlocked) {
      setShowJournals(true);
      setPinPromptOpen(false);
      return;
    }
    setPinError(null);
    setPinPromptOpen((prev) => !prev);
  };

  const handleVerifyPrivacyPin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPinBusy(true);
    setPinError(null);
    try {
      await apiRequest<{ unlocked: boolean }>('/api/crew/unlock-reflections', {
        method: 'POST',
        body: JSON.stringify({ crew_id: activeCrewId, pin: pinInput.trim() }),
      });
      onUnlockCrew?.(activeCrewId);
      setShowJournals(true);
      setPinPromptOpen(false);
      setPinInput('');
    } catch (err) {
      setPinError(err instanceof Error ? err.message : 'Invalid Privacy PIN.');
    } finally {
      setPinBusy(false);
    }
  };

  const filteredRecords = useMemo(() => {
    const sliced = state.telemetry_history.slice(-daysWindow).reverse();
    if (provFilter === 'USER') {
      return sliced.filter((r) => r.provenance === 'USER_ENTERED');
    }
    if (provFilter === 'SIMULATED') {
      return sliced.filter((r) => r.provenance !== 'USER_ENTERED');
    }
    return sliced;
  }, [state.telemetry_history, daysWindow, provFilter]);

  const historicalAlerts = useMemo(() => {
    return filteredRecords
      .filter(
        (r) =>
          r.equivalent_dose_rate_msv_day >= 1.5 ||
          r.sleep_duration_hrs <= 6.2 ||
          r.co2_mmhg >= 3.0 ||
          r.dizziness_severity >= 1 ||
          r.heart_rate_bpm >= 110 ||
          r.spo2_pct <= 93 ||
          r.chest_discomfort ||
          r.palpitations ||
          r.shortness_of_breath ||
          (r.reported_symptoms && r.reported_symptoms.length > 0) ||
          r.respiratory_symptoms.length > 0,
      )
      .map((r) => ({
        sol: r.mission_day,
        timestamp: r.timestamp,
        provenance: provenanceLabel(r.provenance),
        notes: r.notes,
        badges: [
          r.chest_discomfort ? 'Chest Discomfort' : null,
          r.palpitations ? 'Palpitations' : null,
          r.shortness_of_breath ? 'Shortness of Breath' : null,
          r.heart_rate_bpm >= 110 ? `HR ${Math.round(r.heart_rate_bpm)} BPM` : null,
          r.spo2_pct <= 93 ? `SpO₂ ${r.spo2_pct.toFixed(1)}%` : null,
          r.equivalent_dose_rate_msv_day >= 1.5 ? `Radiation ${r.equivalent_dose_rate_msv_day} mSv/d` : null,
          r.sleep_duration_hrs <= 6.2 ? `Low Sleep ${r.sleep_duration_hrs}h` : null,
          r.co2_mmhg >= 3.0 ? `CO₂ ${r.co2_mmhg} mmHg` : null,
          r.dizziness_severity >= 1 ? `Dizziness Gr.${r.dizziness_severity}` : null,
        ].filter(Boolean) as string[],
      }));
  }, [filteredRecords]);

  const generateReport = async () => {
    setCreatingReport(true);
    setHistoryNotice(null);
    try {
      await apiRequest('/api/reports/generate', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const fresh = await apiRequest<FullSystemState>('/api/state');
      onStateUpdated(fresh);
      setHistoryNotice({
        kind: 'ok',
        text: `Generated local store-and-forward report for Sol ${fresh.latest_telemetry.mission_day}.`,
      });
    } catch (err) {
      setHistoryNotice({
        kind: 'err',
        text: err instanceof Error ? err.message : 'Unable to generate store-and-forward report.',
      });
    } finally {
      setCreatingReport(false);
    }
  };

  const downloadSummaryMarkdown = () => {
    const latest = state.latest_telemetry;
    const symptomList = [
      ...(latest.reported_symptoms || []),
      ...(latest.chest_discomfort ? ['Chest discomfort'] : []),
      ...(latest.palpitations ? ['Palpitations'] : []),
      ...(latest.shortness_of_breath ? ['Shortness of breath'] : []),
    ];
    const alertsText = state.assessment.active_alerts.length
      ? state.assessment.active_alerts
        .map((a) => `- **[${a.severity}] ${a.hazard}**: ${a.message} (Next: ${a.action_required})`)
        .join('\n')
      : '- None active.';
    const recsText = state.assessment.recommendations.length
      ? state.assessment.recommendations
        .map((r) => `- **[${r.priority}] ${r.hazard}**: ${r.action}`)
        .join('\n')
      : '- Continue baseline monitoring.';
    const psychText = (state.psych_questionnaires || []).slice(0, 5).length
      ? (state.psych_questionnaires || [])
        .slice(0, 5)
        .map(
          (pq) =>
            `- Sol ${pq.mission_day} (${provenanceLabel(pq.provenance)}): Mood/Emot ${pq.emotional_condition_rating}/10 · Stress ${pq.psychological_stress_rating}/10 · Fatigue ${pq.fatigue_rating}/10 · Sleep Diff ${pq.sleep_difficulty_rating}/10 · Isolation ${pq.isolation_feeling_rating}/10`,
        )
        .join('\n')
      : '- No standalone psychological check-ins recorded.';

    const lines = [
      `# TARS Care Local Health Summary — Sol ${latest.mission_day}`,
      `Astronaut: ${state.astronaut.name} (${state.astronaut.role})`,
      `Gravity Environment: ${gravityRegimeLabel(latest.gravity_g)}`,
      `Overall Status: ${state.assessment.overall_status}${state.assessment.exercise_contraindicated ? ' (EXERCISE HOLD ACTIVE)' : ''}`,
      `Communication Mode: ${state.assessment.comm_mode?.label || 'Delayed'} (${state.comm_state.one_way_delay_minutes} min one-way)`,
      ``,
      `## Latest Measurements (${provenanceLabel(latest.provenance)})`,
      `- Heart Rate: ${latest.heart_rate_bpm} BPM (Baseline ${state.astronaut.baseline_hr_bpm} BPM)`,
      `- Blood Pressure: ${latest.systolic_bp_mmhg}/${latest.diastolic_bp_mmhg} mmHg (Baseline ${state.astronaut.baseline_systolic_mmhg}/${state.astronaut.baseline_diastolic_mmhg} mmHg)`,
      `- Oxygen Saturation: ${latest.spo2_pct}% | Respiratory Rate: ${latest.respiratory_rate_bpm ?? 16}/min`,
      `- Body Temperature: ${latest.body_temp_c} °C`,
      `- Sleep Duration: ${latest.sleep_duration_hrs} hrs (Quality ${latest.sleep_quality_pct}%) | Mood: ${latest.mood_score}/10 | Stress: ${latest.stress_level}/10`,
      `- Muscle Strength: ${latest.muscle_strength_idx}% | Balance: ${latest.balance_score}% | Dizziness Grade: ${latest.dizziness_severity}/3`,
      `- Absorbed Dose: ${latest.absorbed_dose_mgy} mGy | Equivalent Rate: ${latest.equivalent_dose_rate_msv_day} mSv/day | Cumulative: ${latest.cumulative_effective_dose_msv} mSv`,
      `- Cabin Environment: CO2 ${latest.co2_mmhg} mmHg | O2 ${latest.oxygen_pct}% | Temp ${latest.cabin_temp_c} °C | RH ${latest.humidity_pct}%`,
      `- Active Symptoms: ${symptomList.length ? Array.from(new Set(symptomList)).join(', ') : 'None reported'}`,
      ``,
      `## How Am I Doing?`,
      `${state.assessment.glance_summary?.how_am_i_doing || ''}`,
      `${state.assessment.glance_summary?.what_has_changed || ''}`,
      ``,
      `## Active Alerts`,
      alertsText,
      ``,
      `## Prioritized Recommendations`,
      recsText,
      ``,
      `## Recent Behavioral & Sleep Check-Ins`,
      psychText,
      ``,
      `Generated autonomously offline by TARS Care. Mission decision-support summary only; not a clinical diagnosis.`,
    ].join('\n');

    const blob = new Blob([lines], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const filename = `tarscare-sol-${latest.mission_day}-summary.md`;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    setHistoryNotice({
      kind: 'ok',
      text: `Exported local Markdown report: ${filename}`,
    });
  };

  return (
    <div className="space-y-6">
      {/* Controls & Local Report Export Header */}
      <section className="mc-card p-5 lg:p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#FAF9FA]">Health History &amp; Mission Logs</h1>
          <p className="text-sm text-[#E5E5E4]/80 mt-1">
            Review longitudinal radiation, sleep, exercise, vital measurements, and generate offline reports.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex bg-[#0B0D1A] p-1 rounded-full border border-white/10">
            {([7, 14, 30] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDaysWindow(d)}
                className={`px-3 py-1 rounded-full text-xs font-semibold ${daysWindow === d ? 'bg-[#EEF0F6] text-[#040404]' : 'text-[#E5E5E4]'
                  }`}
              >
                {d}d
              </button>
            ))}
          </div>

          <div className="flex bg-[#0B0D1A] p-1 rounded-full border border-white/10">
            {([
              { id: 'ALL', label: 'All Data' },
              { id: 'SIMULATED', label: 'Simulated' },
              { id: 'USER', label: 'User-Entered' },
            ] as const).map((pf) => (
              <button
                key={pf.id}
                type="button"
                onClick={() => setProvFilter(pf.id)}
                className={`px-3 py-1 rounded-full text-xs font-medium ${provFilter === pf.id ? 'bg-[#A5D8FF]/20 text-[#FAF9FA]' : 'text-[#E5E5E4]/80'
                  }`}
              >
                {pf.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            disabled={creatingReport}
            onClick={generateReport}
            className="mc-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>{creatingReport ? 'Generating...' : 'Generate Sync Report'}</span>
          </button>

          <button
            type="button"
            onClick={downloadSummaryMarkdown}
            className="mc-btn-secondary px-4 py-2 text-xs inline-flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5 text-[#A5D8FF]" />
            <span>Export Markdown</span>
          </button>
        </div>
      </section>

      {/* Store-and-Forward Reports & Historical Alerts */}
      {historyNotice && (
        <div
          className={`rounded-xl px-4 py-3 text-xs border ${historyNotice.kind === 'err'
            ? 'bg-red-500/15 border-red-400/40 text-red-100'
            : 'bg-[#0B0D1A] border-[#A5D8FF]/35 text-[#A5D8FF]'
            }`}
        >
          {historyNotice.text}
        </div>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="mc-card p-5 space-y-3.5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-[#FAF9FA]">Earth Sync &amp; Generated Reports</h2>
            <span className="text-xs text-[#E5E5E4]/75">
              {state.store_forward_reports.length} records stored locally
            </span>
          </div>
          <div className="space-y-2.5 max-h-[280px] overflow-y-auto pr-1">
            {state.store_forward_reports.map((rpt) => {
              const rMeta = statusMeta(rpt.risk_level);
              const isSynced = rpt.transmission_status === 'SYNCHRONIZED_ACK';
              return (
                <div key={rpt.report_uid} className="rounded-xl bg-[#0B0D1A] p-3.5 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-[#FAF9FA]">{rpt.title}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${rMeta.badgeClass}`}>
                      {rMeta.label}
                    </span>
                  </div>
                  <p className="text-xs text-[#E5E5E4]/85">{rpt.summary}</p>
                  <div className="flex items-center justify-between text-xs pt-1 text-[#A5D8FF]/90">
                    <span>{isSynced ? 'Synced with Earth' : 'Queued locally (Store-and-Forward)'}</span>
                    <span className="text-[#E5E5E4]/60">{provenanceLabel(rpt.provenance)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mc-card p-5 space-y-3.5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-[#FAF9FA]">Historical Alerts ({daysWindow}d Window)</h2>
            <span className="text-xs text-[#E5E5E4]/75">{historicalAlerts.length} flagged Sols</span>
          </div>
          <div className="space-y-2.5 max-h-[280px] overflow-y-auto pr-1">
            {historicalAlerts.map((al, i) => (
              <div key={`${al.sol}-${i}`} className="rounded-xl bg-[#0B0D1A] p-3.5 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <strong className="text-[#FAF9FA]">Sol {al.sol}</strong>
                  <span className="text-[#E5E5E4]/65">{al.provenance}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {al.badges.map((b) => (
                    <span key={b} className="px-2 py-0.5 rounded-full text-xs bg-amber-500/15 text-amber-300">
                      {b}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-[#E5E5E4]/80">{al.notes}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Behavioral & Sleep Check-In History */}
      <section className="mc-card p-5 lg:p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA] flex items-center gap-2">
              <span>Behavioral &amp; Sleep Check-In History ({state.psych_questionnaires?.length || 0})</span>
              {journalsVisible ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  <Unlock className="w-3 h-3" />
                  <span>PIN Unlocked</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-[#0B0D1A] text-[#A5D8FF] border border-[#A5D8FF]/25">
                  <Lock className="w-3 h-3" />
                  <span>PIN Protected</span>
                </span>
              )}
            </h2>
            <p className="text-xs text-[#E5E5E4]/75 mt-0.5">
              Self-reported isolation, fatigue, mood, concentration, and PIN-gated private reflections stored separately from sensor telemetry.
            </p>
          </div>
          <button
            type="button"
            onClick={handleTogglePrivateReflections}
            className="mc-btn-secondary px-3.5 py-1.5 text-xs inline-flex items-center gap-1.5"
          >
            {journalsVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            <span>{journalsVisible ? 'Lock & Hide Reflections' : 'Unlock Private Reflections'}</span>
          </button>
        </div>

        {pinPromptOpen && !journalsVisible && (
          <form
            onSubmit={handleVerifyPrivacyPin}
            className="rounded-xl bg-[#0B0D1A] border border-[#A5D8FF]/30 p-3.5 flex flex-wrap items-end gap-3"
          >
            <label htmlFor="history-privacy-pin-input" className="block space-y-1">
              <span className="text-xs font-medium text-[#E5E5E4]">
                Enter Crew Privacy PIN for {state.astronaut.name} ({state.privacy_pin_hint || 'Default demo PIN: 2026'})
              </span>
              <input
                id="history-privacy-pin-input"
                name="history_privacy_pin"
                type="password"
                autoComplete="off"
                value={pinInput}
                onChange={(e) => setPinInput(e.target.value)}
                placeholder="Enter PIN (2026)"
                className="block w-48 rounded-lg bg-[#121522] border border-white/15 px-3 py-1.5 text-xs text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={pinBusy}
              className="mc-btn-primary px-4 py-1.5 text-xs"
            >
              {pinBusy ? 'Verifying...' : 'Verify & Unlock'}
            </button>
            <button
              type="button"
              onClick={() => {
                setPinPromptOpen(false);
                setPinError(null);
              }}
              className="mc-btn-secondary px-3 py-1.5 text-xs"
            >
              Cancel
            </button>
            {pinError && <div className="w-full text-xs text-red-300">{pinError}</div>}
          </form>
        )}

        {(state.psych_questionnaires?.length || 0) === 0 ? (
          <div className="rounded-xl bg-[#0B0D1A] p-4 text-xs text-[#E5E5E4]/75">
            No standalone psychological check-ins recorded yet.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pr-1">
            {state.psych_questionnaires.map((pq, idx) => (
              <div key={`${pq.mission_day}-${pq.timestamp}-${idx}`} className="rounded-xl bg-[#0B0D1A] p-3.5 border border-white/[0.06] space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <strong className="text-sm text-[#FAF9FA]">Sol {pq.mission_day}</strong>
                  <span className="text-[#A5D8FF]">{provenanceLabel(pq.provenance)}</span>
                </div>
                <div className="flex flex-wrap gap-2 text-[#E5E5E4]/85 tabular-data">
                  <span>Mood {pq.emotional_condition_rating}/10</span>
                  <span>· Stress {pq.psychological_stress_rating}/10</span>
                  <span>· Fatigue {pq.fatigue_rating}/10</span>
                  <span>· Sleep Diff {pq.sleep_difficulty_rating}/10</span>
                  <span>· Isolation {pq.isolation_feeling_rating}/10</span>
                </div>
                {pq.journal_reflection && (
                  <p className="text-[#E5E5E4]/75 italic pt-1 border-t border-white/[0.06]">
                    {journalsVisible
                      ? pq.journal_reflection
                      : '[Private reflection PIN-locked — click "Unlock Private Reflections" with local PIN to inspect]'}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Longitudinal Radiation, Sleep, Exercise & Vitals Log Table */}
      <section className="mc-card p-5 lg:p-6 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-[#FAF9FA]">
            Physiological &amp; Hazard Log ({filteredRecords.length} entries)
          </h2>
          <span className="text-xs text-[#E5E5E4]/70">Sorted newest first</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs sm:text-sm min-w-[820px]">
            <thead>
              <tr className="border-b border-white/10 text-[#E5E5E4]/75">
                <th className="py-2.5 pr-3">Sol</th>
                <th className="py-2.5 pr-3">Source</th>
                <th className="py-2.5 pr-3">HR / BP</th>
                <th className="py-2.5 pr-3">SpO₂</th>
                <th className="py-2.5 pr-3">Sleep</th>
                <th className="py-2.5 pr-3">Exercise</th>
                <th className="py-2.5 pr-3">Absorbed / Equiv Rad.</th>
                <th className="py-2.5 pr-3">Cabin CO₂</th>
                <th className="py-2.5">Flags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06] tabular-data">
              {filteredRecords.map((r, idx) => (
                <tr key={`${r.mission_day}-${r.timestamp}-${idx}`} className="hover:bg-white/[0.02]">
                  <td className="py-2.5 pr-3 font-semibold text-[#FAF9FA]">Sol {r.mission_day}</td>
                  <td className="py-2.5 pr-3 text-[#A5D8FF] text-xs">{provenanceLabel(r.provenance)}</td>
                  <td className="py-2.5 pr-3 text-[#FAF9FA]">
                    {Math.round(r.heart_rate_bpm)} BPM · {Math.round(r.systolic_bp_mmhg)}/{Math.round(r.diastolic_bp_mmhg)}
                  </td>
                  <td className="py-2.5 pr-3 text-[#FAF9FA]">{r.spo2_pct.toFixed(1)}%</td>
                  <td className="py-2.5 pr-3 text-[#E5E5E4]">{r.sleep_duration_hrs.toFixed(1)} hrs</td>
                  <td className="py-2.5 pr-3 text-[#E5E5E4]">{Math.round(r.exercise_adherence_pct)}% ARED</td>
                  <td className="py-2.5 pr-3 text-[#E5E5E4]">
                    {r.absorbed_dose_mgy.toFixed(2)} mGy / {r.equivalent_dose_rate_msv_day.toFixed(2)} mSv/d
                  </td>
                  <td className="py-2.5 pr-3 text-[#E5E5E4]">{r.co2_mmhg.toFixed(1)} mmHg</td>
                  <td className="py-2.5 text-xs text-amber-300">
                    {[
                      r.chest_discomfort ? 'Chest' : null,
                      r.palpitations ? 'Palp' : null,
                      r.shortness_of_breath ? 'SOB' : null,
                      r.dizziness_severity >= 1 ? `Diz${r.dizziness_severity}` : null,
                    ].filter(Boolean).join(', ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Connected Hardware Measurements, Guided Exams & Biological Specimens History */}
      <section className="mc-card p-5 lg:p-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA]">
              Connected Devices, Guided Examinations &amp; Biosamples History
            </h2>
            <p className="text-xs text-[#E5E5E4]/75 mt-0.5">
              Preserves source instruments, physical units, and strict distinction between Simulated Mode and Imported/Examination records.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="px-2.5 py-1 rounded bg-[#0B0D1A] border border-white/10 text-[#A5D8FF]">
              {(state.device_measurements || []).length} Confirmed Readings
            </span>
            <span className="px-2.5 py-1 rounded bg-[#0B0D1A] border border-white/10 text-[#FAF9FA]">
              {(state.hardware_examinations || []).length} Guided Exams
            </span>
            <span className="px-2.5 py-1 rounded bg-[#0B0D1A] border border-white/10 text-[#FAF9FA]">
              {(state.biosample_records || []).length} Specimens
            </span>
          </div>
        </div>

        {(state.device_measurements || []).length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs min-w-[740px]">
              <thead>
                <tr className="border-b border-white/10 text-[#E5E5E4]/75">
                  <th className="py-2 pr-3">Recorded</th>
                  <th className="py-2 pr-3">Instrument</th>
                  <th className="py-2 pr-3">Measurement</th>
                  <th className="py-2 pr-3">Value &amp; Unit</th>
                  <th className="py-2 pr-3">Data Source</th>
                  <th className="py-2">Device Status / Validation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06] tabular-data">
                {(state.device_measurements || []).slice(0, 20).map((m) => (
                  <tr key={m.record_uid}>
                    <td className="py-2 pr-3 text-[#E5E5E4]/80">{formatRecordedTime(m.recorded_at)}</td>
                    <td className="py-2 pr-3 font-medium text-[#FAF9FA]">{m.device_name}</td>
                    <td className="py-2 pr-3 text-[#E5E5E4]">{m.measurement_type.replace(/_/g, ' ')}</td>
                    <td className="py-2 pr-3 font-mono text-[#A5D8FF]">
                      {m.value ?? m.value_text} {m.unit}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] ${
                          m.data_source === 'simulated'
                            ? 'bg-amber-500/15 text-amber-300'
                            : 'bg-[#0B0D1A] text-[#FAF9FA] border border-white/15'
                        }`}
                      >
                        {m.data_source === 'simulated' ? 'SIMULATED DEMO' : m.data_source}
                      </span>
                    </td>
                    <td className="py-2 text-[#E5E5E4]/85">
                      {deviceStatusMeta(m.connection_status).label} · {m.quality_status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-[#FAF9FA]">Guided Examinations &amp; Countermeasures</h3>
            {(state.hardware_examinations || []).length === 0 ? (
              <div className="rounded-xl bg-[#0B0D1A] p-3 text-xs text-[#E5E5E4]/70">
                No guided examinations recorded yet.
              </div>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {(state.hardware_examinations || []).map((ex) => (
                  <div
                    key={ex.exam_uid}
                    className={`rounded-xl bg-[#0B0D1A] p-3 border text-xs space-y-1 ${
                      ex.abnormal_flag ? 'border-amber-500/40' : 'border-white/10'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <strong className="text-[#FAF9FA]">{ex.device_name}</strong>
                      <span className="text-[#A5D8FF]">Sol {ex.mission_day}</span>
                    </div>
                    <div className="text-[#E5E5E4]/85">{ex.summary_note}</div>
                    {ex.abnormal_flag && (
                      <div className="text-amber-300 font-medium">Flag: {ex.abnormal_reason}</div>
                    )}
                    {ex.attachments?.length > 0 && (
                      <div className="text-[#E5E5E4]/70">
                        Attachments: {ex.attachments.map((a) => a.filename).join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-[#FAF9FA]">Biological Specimens &amp; Lab Assays</h3>
            {(state.biosample_records || []).length === 0 ? (
              <div className="rounded-xl bg-[#0B0D1A] p-3 text-xs text-[#E5E5E4]/70">
                No biological specimens registered yet.
              </div>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {(state.biosample_records || []).map((b) => (
                  <div key={b.sample_uid} className="rounded-xl bg-[#0B0D1A] p-3 border border-white/10 text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <strong className="text-[#FAF9FA]">
                        {b.sample_uid} · {b.specimen_type}
                      </strong>
                      <span className="px-2 py-0.5 rounded bg-[#181C2E] text-[#A5D8FF]">{b.status}</span>
                    </div>
                    <div className="text-[#E5E5E4]/80">
                      Sol {b.mission_day} · Storage: {b.storage_location}
                    </div>
                    {b.assay_results?.markers && b.assay_results.markers.length > 0 && (
                      <div className="text-emerald-300 pt-1 border-t border-white/10">
                        Imported Assays:{' '}
                        {b.assay_results.markers
                          .map((mk) => `${mk.biomarker ?? 'Marker'}: ${mk.value ?? ''} ${mk.unit ?? ''}`)
                          .join(' | ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
};

interface CommProps {
  state: FullSystemState;
  onStateUpdated: (next: FullSystemState) => void;
  onOpenEmergency: () => void;
  onOpenSpaceRadiation?: () => void;
  onOpenEnvironment?: () => void;
}

export const CommunicationStatusView: React.FC<CommProps> = ({
  state,
  onStateUpdated,
  onOpenEmergency,
  onOpenSpaceRadiation,
  onOpenEnvironment,
}) => {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);

  const commCentre = state.comm_centre_state;
  const currentMode = state.assessment.comm_mode?.mode || 'DELAYED';
  const pendingCount =
    state.comm_state.pending_reports_count ??
    state.store_forward_reports.filter((r) => r.transmission_status !== 'SYNCHRONIZED_ACK').length;

  // Delay simulator form state
  const [customDelayMin, setCustomDelayMin] = useState<number>(
    commCentre?.one_way_delay_minutes ?? state.comm_state.one_way_delay_minutes ?? 14.2
  );
  const [customDistanceMkm, setCustomDistanceMkm] = useState<number>(
    commCentre?.distance_million_km ?? state.comm_state.distance_million_km ?? 255.4
  );
  const [fbSnap, setFbSnap] = useState<HybridSuiteSnapshot | null>(null);

  useEffect(() => {
    return subscribeHybridSuite(setFbSnap);
  }, []);

  // Message Centre compose state
  const [msgForm, setMsgForm] = useState({
    subject: '',
    body: '',
    recipient: 'Earth Mission Control & Flight Surgeons (MCC-Houston)',
    message_type: 'MISSION_CONTROL_MESSAGE',
    priority: 'NORMAL',
    save_as_draft: false,
    simulate_failure: false,
  });

  const setCommMode = async (mode: 'CONNECTED' | 'DELAYED' | 'OFFLINE') => {
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      await apiRequest('/api/comm/mode', {
        method: 'POST',
        body: JSON.stringify({ mode }),
      });
      await syncFirebaseWithCommMode(mode);
      const fresh = await apiRequest<FullSystemState>('/api/state');
      onStateUpdated(fresh);
      setNotice(
        mode === 'OFFLINE'
          ? 'Switched to OFFLINE Blackout: Cloud Firestore network paused (IndexedDB Store-and-Forward active) & Firebase AI Logic locked to ONLY_ON_DEVICE.'
          : `Communication simulation switched to ${mode}: Cloud Firestore Store-and-Forward sync active & Remote Config refreshed.`,
      );
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Unable to switch communication mode.');
    } finally {
      setBusy(false);
    }
  };

  const applyScenarioPreset = async (scenarioId: string) => {
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      const res = await apiRequest<{ state?: FullSystemState; comm_centre_state?: any }>(
        '/api/comm/simulator',
        {
          method: 'POST',
          body: JSON.stringify({ scenario_id: scenarioId }),
        }
      );
      if (res.state) {
        onStateUpdated(res.state);
        if (res.state.comm_centre_state) {
          setCustomDelayMin(res.state.comm_centre_state.one_way_delay_minutes);
          setCustomDistanceMkm(res.state.comm_centre_state.distance_million_km);
        }
      }
      setNotice(`Loaded mission communication preset: ${scenarioId}.`);
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Unable to load scenario preset.');
    } finally {
      setBusy(false);
    }
  };

  const applyCustomSimulator = async (conditionOverride?: string) => {
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      const res = await apiRequest<{ state?: FullSystemState }>('/api/comm/simulator', {
        method: 'POST',
        body: JSON.stringify({
          comm_condition: conditionOverride || commCentre?.comm_condition || 'DELAYED',
          one_way_delay_minutes: Number(customDelayMin),
          distance_million_km: Number(customDistanceMkm),
        }),
      });
      if (res.state) onStateUpdated(res.state);
      setNotice(
        `Configured communication delay simulator: ${customDelayMin} min one-way (${(
          Number(customDelayMin) * 2
        ).toFixed(1)} min round-trip) at ${customDistanceMkm}M km.`
      );
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Unable to update simulator.');
    } finally {
      setBusy(false);
    }
  };

  const handleComposeMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!msgForm.subject.trim() || !msgForm.body.trim()) return;
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      const res = await apiRequest<{ message: any; state?: FullSystemState }>(
        '/api/comm/messages',
        {
          method: 'POST',
          body: JSON.stringify(msgForm),
        }
      );
      if (res.state) onStateUpdated(res.state);
      setMsgForm({
        ...msgForm,
        subject: '',
        body: '',
        save_as_draft: false,
        simulate_failure: false,
      });
      setNotice(`Message "${res.message.subject}" recorded with status: ${res.message.status}.`);
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Failed to create message.');
    } finally {
      setBusy(false);
    }
  };

  const handleRetryOrSendMessage = async (messageUid: string, simulateFail = false) => {
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      const res = await apiRequest<{ message: any; state?: FullSystemState }>(
        `/api/comm/messages/${messageUid}/retry`,
        {
          method: 'POST',
          body: JSON.stringify({ simulate_failure: simulateFail }),
        }
      );
      if (res.state) onStateUpdated(res.state);
      setNotice(
        `Transmission status for "${res.message.subject}": ${res.message.status}${
          res.message.failure_reason ? ` (${res.message.failure_reason})` : ''
        }`
      );
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Failed to retry message.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteMessage = async (messageUid: string) => {
    setBusy(true);
    try {
      const res = await apiRequest<{ state?: FullSystemState }>(
        `/api/comm/messages/${messageUid}`,
        { method: 'DELETE' }
      );
      if (res.state) onStateUpdated(res.state);
    } finally {
      setBusy(false);
    }
  };

  const syncQueue = async () => {
    setBusy(true);
    setNotice(null);
    setSyncError(null);
    try {
      const res = await apiRequest<SyncResponse>('/api/comm/sync', {
        method: 'POST',
      });
      if (res.state) {
        onStateUpdated(res.state);
      } else {
        const fresh = await apiRequest<FullSystemState>('/api/state');
        onStateUpdated(fresh);
      }
      const sr = res.sync_result;
      if (!sr || sr.status === 'BLOCKED_OFFLINE') {
        setSyncError(
          sr?.message ||
            'Synchronization blocked while Offline (Blackout). Switch to Delayed or Connected to transmit queued packets.'
        );
      } else {
        setNotice(
          sr.message ||
            `Synchronized ${sr.synchronized_count} queued store-and-forward report(s); ${sr.remaining_queued} remaining.`
        );
      }
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Failed to synchronize queued telemetry.');
    } finally {
      setBusy(false);
    }
  };

  const aiStatus = state.local_ai_status;
  const oneWayDelay = commCentre?.one_way_delay_minutes ?? state.comm_state.one_way_delay_minutes ?? 14.2;
  const roundTripDelay = commCentre?.round_trip_delay_minutes ?? Number((oneWayDelay * 2).toFixed(2));
  const commCondition = commCentre?.comm_condition ?? (currentMode === 'OFFLINE' ? 'BLACKOUT' : currentMode === 'CONNECTED' ? 'NORMAL' : 'DELAYED');

  const msgStatusBadge = (st: string) => {
    switch (st) {
      case 'Sent':
        return (
          <span className="mc-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            Sent (Confirmed)
          </span>
        );
      case 'Queued':
      case 'Sending':
        return (
          <span className="mc-pill bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/30">
            {st}
          </span>
        );
      case 'Waiting for Connection':
        return (
          <span className="mc-pill bg-amber-500/15 text-amber-300 border border-amber-500/30">
            Waiting for Connection
          </span>
        );
      case 'Failed':
        return (
          <span className="mc-pill bg-rose-500/20 text-rose-300 border border-rose-500/40">
            Failed (Retry Available)
          </span>
        );
      default:
        return (
          <span className="mc-pill bg-white/10 text-[#E5E5E4]">
            {st}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* PART 2.8: MISSION COMMUNICATION DASHBOARD */}
      <section className="mc-card p-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5 mb-1">
              <h1 className="text-2xl font-bold text-[#FAF9FA]">
                Distance from Earth &amp; Mission Communication
              </h1>
              <span className="mc-pill bg-white/5 text-[#8E95A8] border border-white/10">
                Source: {commCentre?.telemetry_source_type || 'CONFIGURED_SIMULATION'}
              </span>
            </div>
            <p className="text-sm text-[#E5E5E4]/80">
              {commCentre?.mission_location || 'Jezero-Elysium Frontier Habitat · Mars Surface (0.38g)'} &rarr;{' '}
              {commCentre?.mission_destination || 'Mars Surface Operations'}
            </p>
          </div>
          <span
            className={`px-4 py-1.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 ${
              currentMode === 'CONNECTED'
                ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                : currentMode === 'OFFLINE'
                ? 'bg-red-500/15 text-red-300 border border-red-500/30'
                : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
            }`}
          >
            {currentMode === 'OFFLINE' ? <WifiOff className="w-4 h-4" /> : <Wifi className="w-4 h-4" />}
            <span>
              {commCondition} · {state.assessment.comm_mode?.label || currentMode}
            </span>
          </span>
        </div>

        {/* Key Telemetry Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3.5 text-xs">
          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">Distance from Earth</span>
            <span className="text-lg font-bold text-[#FAF9FA] tabular-nums mt-1 block">
              {commCentre?.distance_million_km ?? state.comm_state.distance_million_km} M km
            </span>
            <span className="text-[11px] text-[#A5D8FF]">{commCentre?.distance_au ?? 1.707} AU</span>
          </div>

          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">One-Way Signal Delay</span>
            <span className="text-lg font-bold text-[#FAF9FA] tabular-nums mt-1 block">
              {oneWayDelay} min
            </span>
            <span className="text-[11px] text-[#8E95A8]">Mars range: ~4–24 min</span>
          </div>

          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">Round-Trip Delay</span>
            <span className="text-lg font-bold text-[#FAF9FA] tabular-nums mt-1 block">
              {roundTripDelay} min
            </span>
            <span className="text-[11px] text-[#8E95A8]">2 &times; one-way light time</span>
          </div>

          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">Pending Messages</span>
            <span className="text-lg font-bold text-[#FAF9FA] tabular-nums mt-1 block">
              {commCentre?.pending_messages_count ?? 0} queued
            </span>
            <span className="text-[11px] text-[#8E95A8]">
              {commCentre?.draft_messages_count ?? 0} draft(s)
            </span>
          </div>

          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">Unsent Health Reports</span>
            <span className="text-lg font-bold text-[#FAF9FA] tabular-nums mt-1 block">
              {pendingCount} packet(s)
            </span>
            <span className="text-[11px] text-[#8E95A8]">Store-and-forward queue</span>
          </div>

          <div className="rounded-xl bg-[#0B0D1A] p-3.5">
            <span className="text-[#8E95A8] block">Next Comm Window</span>
            <span className="text-xs font-semibold text-[#FAF9FA] mt-1 block">
              {commCentre?.next_comm_window_utc || 'Scheduled DSN Orbiter Pass'}
            </span>
            <span className="text-[11px] text-[#8E95A8]">
              Last sync: {formatRecordedTime(state.comm_state.last_sync_timestamp)}
            </span>
          </div>
        </div>

        {/* 3-State Mode Simulation Buttons */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {([
            {
              id: 'CONNECTED',
              title: 'Connected (Normal Near-Earth)',
              desc: 'Simulated low-latency direct link (0 min delay). Reports acknowledge upon submission.',
            },
            {
              id: 'DELAYED',
              title: 'Delayed (Mars Nominal)',
              desc: `Simulated deep-space delay (${oneWayDelay} min one-way / ${roundTripDelay} min round-trip). Assessments execute autonomously onboard.`,
            },
            {
              id: 'OFFLINE',
              title: 'Offline (Communication Blackout)',
              desc: 'Zero Earth link (solar conjunction). All health assessments, food logs, journals, and AI companion operate 100% locally.',
            },
          ] as const).map((opt) => {
            const active = currentMode === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                disabled={busy}
                onClick={() => setCommMode(opt.id)}
                className={`rounded-2xl p-4 text-left transition-colors border ${
                  active
                    ? 'bg-[#A5D8FF]/15 border-[#A5D8FF]'
                    : 'bg-[#0B0D1A] border-white/[0.08] hover:border-[#A5D8FF]/45'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <strong className="text-base text-[#FAF9FA]">{opt.title}</strong>
                  {active && <CheckCircle2 className="w-4 h-4 text-[#A5D8FF]" />}
                </div>
                <p className="text-xs text-[#E5E5E4]/80 leading-relaxed">{opt.desc}</p>
              </button>
            );
          })}
        </div>

        {syncError && (
          <div className="rounded-xl bg-amber-500/15 px-4 py-3 text-sm text-amber-100 border border-amber-400/40 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0" />
            <span>{syncError}</span>
          </div>
        )}

        {notice && (
          <div className="rounded-xl bg-[#0B0D1A] px-4 py-3 text-sm text-[#A5D8FF] border border-[#A5D8FF]/30">
            {notice}
          </div>
        )}
      </section>

      {/* FIREBASE CLOUD FIRESTORE STORE-AND-FORWARD & ANDROID EVA CROSS-PLATFORM SYNC */}
      <section className="mc-card p-6 space-y-4 border border-[#A5D8FF]/25">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA] flex items-center gap-2">
              <Globe className="w-4 h-4 text-[#A5D8FF]" />
              <span>Firebase Offline Store-and-Forward &amp; Cross-Platform Android EVA Sync</span>
            </h2>
            <p className="text-xs text-[#E5E5E4]/75 mt-0.5">
              Powered by Cloud Firestore IndexedDB <code className="text-[#A5D8FF]">persistentLocalCache</code>, Firebase App Check, Crew Auth &amp; Remote Config — syncing field telemetry between the Native Android EVA Companion and Web Habitat Workstation.
            </p>
          </div>
          <span
            className={`mc-pill border ${
              fbSnap?.firestoreNetworkEnabled
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/35'
                : 'bg-amber-500/15 text-amber-200 border-amber-500/35'
            }`}
          >
            {fbSnap?.firestoreNetworkEnabled
              ? `Firestore Link Active (${fbSnap.pendingSyncWrites} pending)`
              : `Firestore Offline Queue (${fbSnap?.pendingSyncWrites ?? 0} queued locally)`}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="rounded-xl bg-[#0B0D1A] p-3.5 border border-white/[0.06]">
            <span className="text-[#8E95A8] block">Firebase AI Logic Policy</span>
            <strong className="text-[#FAF9FA] block mt-1">
              {currentMode === 'OFFLINE'
                ? 'ONLY_ON_DEVICE (Blackout Locked)'
                : (fbSnap?.selectedMode || 'prefer_on_device').toUpperCase()}
            </strong>
            <span className="text-[11px] text-[#A5D8FF]">
              Cloud fallback: {fbSnap?.cloudModel || 'gemini-3.5-flash-lite'}
            </span>
          </div>
          <div className="rounded-xl bg-[#0B0D1A] p-3.5 border border-white/[0.06]">
            <span className="text-[#8E95A8] block">Remote Config Mission Thresholds</span>
            <strong className="text-[#FAF9FA] block mt-1">
              CO₂ Warn: {fbSnap?.remoteConfig.co2WarnMmhg ?? 3.0} mmHg · Rad Warn:{' '}
              {fbSnap?.remoteConfig.radWarnMsv ?? 50} mSv
            </strong>
            <span className="text-[11px] text-[#8E95A8]">
              Source: {fbSnap?.remoteConfig.source || 'default'}
            </span>
          </div>
          <div className="rounded-xl bg-[#0B0D1A] p-3.5 border border-white/[0.06]">
            <span className="text-[#8E95A8] block">App Check &amp; Multi-Platform Status</span>
            <strong className="text-[#FAF9FA] block mt-1">
              {fbSnap?.firebaseConfigured
                ? `Project: ${fbSnap.projectId}`
                : 'Local Sandbox (Configure Project to Sync Android ↔ Web)'}
            </strong>
            <span className="text-[11px] text-[#A5D8FF]">
              App Check: {fbSnap?.appCheckMode || 'local_sandbox'}
            </span>
          </div>
        </div>

        {fbSnap && fbSnap.recentSyncItems.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-[#A5D8FF]">
              Live Cross-Platform Firestore Sync Stream (Web Chrome ↔ Android EVA Companion)
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
              {fbSnap.recentSyncItems.slice(0, 6).map((item) => (
                <div
                  key={item.id}
                  className="rounded-xl bg-[#0B0D1A] p-3 border border-white/[0.07] flex flex-col justify-between gap-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-[#FAF9FA]">
                      {item.sourcePlatform === 'ANDROID_COMPANION'
                        ? 'Android EVA Companion'
                        : 'Web Habitat Console'}{' '}
                      · Sol {item.sol}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        item.pendingCloudSync
                          ? 'bg-amber-500/20 text-amber-200 border border-amber-400/35'
                          : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                      }`}
                    >
                      {item.pendingCloudSync ? 'Queued Locally (IndexedDB)' : 'Synced to Firestore'}
                    </span>
                  </div>
                  <p className="text-[#E5E5E4]/85 line-clamp-2">{item.summary}</p>
                  <div className="text-[11px] text-[#8E95A8]">
                    {item.crewName} · AI Source: {item.inferenceSource}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* PART 2.9: CONFIGURABLE COMMUNICATION DELAY SIMULATOR */}
      <section className="mc-card p-6 space-y-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA] flex items-center gap-2">
              <Radio className="w-4 h-4 text-[#A5D8FF]" />
              Mission Trajectory &amp; Communication Delay Simulator
            </h2>
            <p className="text-xs text-[#8E95A8] mt-0.5">
              {commCentre?.latency_explanation ||
                'Distance governs one-way light time (~4–24 min for Mars), while actual communication availability also depends on spacecraft antennas, relay orbiters, and solar conjunction.'}
            </p>
          </div>
        </div>

        {/* Demonstration Scenario Presets */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          {(commCentre?.scenario_presets || []).map((preset) => {
            const isSelected = commCentre?.scenario_id === preset.scenario_id;
            return (
              <button
                key={preset.scenario_id}
                type="button"
                disabled={busy}
                onClick={() => applyScenarioPreset(preset.scenario_id)}
                className={`p-3.5 rounded-xl text-left transition-all ${
                  isSelected
                    ? 'bg-[#A5D8FF]/15 border border-[#A5D8FF]'
                    : 'bg-[#0B0D1A] hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-semibold text-[#FAF9FA]">{preset.label}</span>
                  <span className="mc-pill bg-white/10 text-[#A5D8FF]">
                    {preset.comm_condition}
                  </span>
                </div>
                <div className="text-[#E5E5E4] tabular-nums">
                  {preset.distance_million_km}M km · {preset.one_way_delay_minutes} min one-way ({(
                    preset.one_way_delay_minutes * 2
                  ).toFixed(1)}{' '}
                  min RT)
                </div>
                <p className="text-[11px] text-[#8E95A8] mt-1 line-clamp-2">{preset.explanation}</p>
              </button>
            );
          })}
        </div>

        {/* Custom Delay & Condition Controls */}
        <div className="pt-4 border-t border-[#222638] grid grid-cols-1 md:grid-cols-4 gap-4 items-end text-xs">
          <div>
            <label className="block text-[#E5E5E4] mb-1">
              One-Way Signal Delay: <strong>{customDelayMin} min</strong> (Round-Trip:{' '}
              <strong>{(Number(customDelayMin) * 2).toFixed(1)} min</strong>)
            </label>
            <input
              type="range"
              min="0"
              max="24"
              step="0.2"
              value={customDelayMin}
              onChange={(e) => setCustomDelayMin(Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-[#E5E5E4] mb-1">Distance from Earth (Million km)</label>
            <input
              type="number"
              step="0.5"
              min="0"
              value={customDistanceMkm}
              onChange={(e) => setCustomDistanceMkm(Number(e.target.value))}
              className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
            />
          </div>
          <div className="md:col-span-2 flex flex-wrap items-center gap-2">
            {(['NORMAL', 'DELAYED', 'INTERMITTENT', 'BLACKOUT'] as const).map((cond) => (
              <button
                key={cond}
                type="button"
                disabled={busy}
                onClick={() => applyCustomSimulator(cond)}
                className={`px-3 py-2 rounded-lg font-medium ${
                  commCondition === cond
                    ? 'bg-[#EEF0F6] text-[#040404]'
                    : 'bg-[#0B0D1A] text-[#E5E5E4] hover:bg-white/[0.08]'
                }`}
              >
                Apply {cond}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* PART 2.11: COMMUNICATION MESSAGE CENTRE */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Compose Message / Health Report to Mission Control */}
        <div className="mc-card p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA]">
              Compose Message to Mission Control
            </h2>
            <p className="text-xs text-[#8E95A8] mt-0.5">
              Prepare health reports, supply updates, or crew communications. Never marked as Sent until transmission is confirmed.
            </p>
          </div>
          <form onSubmit={handleComposeMessage} className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Message Type</label>
                <select
                  value={msgForm.message_type}
                  onChange={(e) => setMsgForm({ ...msgForm, message_type: e.target.value })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                >
                  <option value="MISSION_CONTROL_MESSAGE">Mission Control Message</option>
                  <option value="HEALTH_REPORT">Crew Health Report</option>
                  <option value="SUPPLY_REPORT">Food &amp; Supply Report</option>
                  <option value="URGENT_MEDICAL_CONSULT">Urgent Flight Surgeon Consult</option>
                </select>
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Priority</label>
                <select
                  value={msgForm.priority}
                  onChange={(e) => setMsgForm({ ...msgForm, priority: e.target.value })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                >
                  <option value="NORMAL">Normal</option>
                  <option value="IMPORTANT">Important</option>
                  <option value="URGENT">Urgent</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-[#E5E5E4] mb-1">Recipient Desk</label>
              <input
                type="text"
                value={msgForm.recipient}
                onChange={(e) => setMsgForm({ ...msgForm, recipient: e.target.value })}
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
              />
            </div>

            <div>
              <label className="block text-[#E5E5E4] mb-1">Subject *</label>
              <input
                type="text"
                required
                value={msgForm.subject}
                onChange={(e) => setMsgForm({ ...msgForm, subject: e.target.value })}
                placeholder={`Sol ${state.latest_telemetry.mission_day} Status & Telemetry Summary`}
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
              />
            </div>

            <div>
              <label className="block text-[#E5E5E4] mb-1">Message / Report Content *</label>
              <textarea
                rows={4}
                required
                value={msgForm.body}
                onChange={(e) => setMsgForm({ ...msgForm, body: e.target.value })}
                placeholder="Enter telemetry summary, medical questions, or supply status for Earth..."
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
              />
            </div>

            <div className="space-y-1.5 pt-1">
              <label className="flex items-center gap-2 text-[#E5E5E4]">
                <input
                  type="checkbox"
                  checked={msgForm.save_as_draft}
                  onChange={(e) => setMsgForm({ ...msgForm, save_as_draft: e.target.checked })}
                />
                Save as Draft (do not queue yet)
              </label>
              <label className="flex items-center gap-2 text-[#8E95A8]">
                <input
                  type="checkbox"
                  checked={msgForm.simulate_failure}
                  onChange={(e) =>
                    setMsgForm({ ...msgForm, simulate_failure: e.target.checked })
                  }
                />
                Simulate intermittent carrier drop (test Failed &rarr; Retry workflow)
              </label>
            </div>

            <button type="submit" disabled={busy} className="mc-btn-primary w-full py-2.5 flex items-center justify-center gap-1.5">
              <Send className="w-3.5 h-3.5" />
              {msgForm.save_as_draft ? 'Save Message Draft' : 'Queue / Transmit Message'}
            </button>
          </form>
        </div>

        {/* Message Queue & Transmission Log */}
        <div className="lg:col-span-2 mc-card p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-[#FAF9FA]">
                Communication Message Centre ({commCentre?.messages?.length || 0})
              </h2>
              <p className="text-xs text-[#8E95A8]">
                Statuses: Draft · Queued · Waiting for Connection · Sending · Sent · Failed
              </p>
            </div>
            <button
              type="button"
              disabled={busy || currentMode === 'OFFLINE'}
              onClick={syncQueue}
              className="mc-btn-primary px-4 py-2 text-xs inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {currentMode === 'OFFLINE'
                ? 'Sync Paused Offline'
                : 'Synchronize All Queued Messages & Reports'}
            </button>
          </div>

          <div className="divide-y divide-[#222638] max-h-[420px] overflow-y-auto pr-1 text-xs">
            {(commCentre?.messages || []).map((msg) => (
              <div key={msg.message_uid} className="py-3.5 first:pt-0 last:pb-0 space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-[#FAF9FA] text-sm">{msg.subject}</span>
                    <span
                      className={`mc-pill ${
                        msg.priority === 'URGENT'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : msg.priority === 'IMPORTANT'
                          ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                          : 'bg-white/5 text-[#8E95A8]'
                      }`}
                    >
                      {msg.priority}
                    </span>
                    <span className="mc-pill bg-white/5 text-[#E5E5E4]">{msg.message_type}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {msgStatusBadge(msg.status)}
                    {msg.status !== 'Sent' && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleRetryOrSendMessage(msg.message_uid, false)}
                        className="px-2.5 py-1 rounded bg-[#A5D8FF]/20 hover:bg-[#A5D8FF]/30 text-[#A5D8FF] font-medium flex items-center gap-1"
                      >
                        <RotateCcw className="w-3 h-3" />
                        {msg.status === 'Failed' ? 'Retry' : 'Send Now'}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleDeleteMessage(msg.message_uid)}
                      className="p-1 rounded bg-white/5 hover:bg-rose-500/20 text-[#8E95A8] hover:text-rose-300"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <p className="text-[#E5E5E4] leading-relaxed">{msg.body}</p>

                {msg.failure_reason && (
                  <p className="text-rose-300 text-[11px]">
                    Transmission note: {msg.failure_reason} (Retries: {msg.retry_count})
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-between text-[11px] text-[#8E95A8]">
                  <span>
                    To: {msg.recipient} · Latency: {msg.one_way_delay_minutes}m OW /{' '}
                    {msg.round_trip_delay_minutes}m RT ({msg.distance_million_km}M km)
                  </span>
                  <span>
                    Created: {formatRecordedTime(msg.created_at)}
                    {msg.sent_at ? ` · Sent: ${formatRecordedTime(msg.sent_at)}` : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Synchronisation History Log */}
          {(commCentre?.sync_history?.length || 0) > 0 && (
            <div className="pt-4 border-t border-[#222638]">
              <h3 className="text-xs font-semibold text-[#FAF9FA] mb-2">
                Recent Synchronisation &amp; DSN Pass Log
              </h3>
              <div className="space-y-1.5 text-[11px]">
                {(commCentre?.sync_history || []).slice(0, 4).map((sh) => (
                  <div
                    key={sh.sync_uid}
                    className="flex flex-wrap items-center justify-between gap-2 p-2 rounded-lg bg-[#0B0D1A]"
                  >
                    <span className="text-[#E5E5E4]">
                      <strong>Sol {sh.mission_day}</strong> ({sh.status}): {sh.summary}
                    </span>
                    <span className="text-[#8E95A8]">{formatRecordedTime(sh.timestamp)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* PART 2.10: LOCAL OFFLINE VS EARTH-DEPENDENT CAPABILITIES */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="mc-card p-5 lg:p-6 space-y-3">
          <h2 className="text-base font-semibold text-[#FAF9FA] flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            Available 100% Locally Offline (Zero Earth Dependency)
          </h2>
          <ul className="space-y-1.5 text-xs text-[#E5E5E4]">
            {(
              commCentre?.local_vs_earth_capabilities?.available_locally_offline || [
                '5-Hazard Integrated Health Assessment & EVA Readiness',
                'Food & Life-Support Supplies Inventory & Nutrition Tracking',
                'Private Personal Journal & TARSCARE AI Companion',
              ]
            ).map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="pt-2">
            <button
              type="button"
              onClick={onOpenEmergency}
              className="mc-btn-secondary px-4 py-2 text-xs inline-flex items-center gap-2"
            >
              <ShieldAlert className="w-4 h-4 text-amber-300" />
              <span>Run Offline Emergency Protocol</span>
            </button>
          </div>
        </div>

        <div className="mc-card p-5 lg:p-6 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-[#A5D8FF]" />
              <h2 className="text-lg font-semibold text-[#FAF9FA]">Autonomous &amp; API Intelligence Stack</h2>
            </div>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-[#0B0D1A] text-[#A5D8FF] border border-[#A5D8FF]/25">
              {aiStatus?.active_engine_mode || 'DETERMINISTIC_OFFLINE_RAG'}
            </span>
          </div>
          <div className="space-y-2.5 text-sm">
            <div className="flex items-center justify-between rounded-xl bg-[#0B0D1A] px-4 py-3">
              <span className="text-[#E5E5E4]">Local SQLite Telemetry Storage</span>
              <span className="text-xs font-semibold text-emerald-300">Ready Offline</span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-[#0B0D1A] px-4 py-3">
              <span className="text-[#E5E5E4]">Deterministic + Semantic Offline RAG</span>
              <span className="text-xs font-semibold text-[#A5D8FF]">
                {aiStatus?.sentence_transformers_cached
                  ? aiStatus?.embeddings_loaded
                    ? 'Cached Embeddings Loaded + TF-IDF'
                    : 'Cached Embeddings + TF-IDF'
                  : 'TF-IDF Active'}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-[#0B0D1A] px-4 py-3">
              <span className="text-[#E5E5E4]">Local Ollama Detection (127.0.0.1:11434)</span>
              <span className="text-xs font-semibold text-[#E5E5E4]">
                {aiStatus?.ollama_available
                  ? aiStatus?.llm_provider === 'local' && aiStatus?.llm_active
                    ? `Active (${aiStatus.ollama_model})`
                    : `Installed (${aiStatus.ollama_model}, Standby)`
                  : 'Not Running (Fallback Active)'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-xl bg-[#0B0D1A] px-4 py-3">
              <span className="text-[#E5E5E4]">External API LLM (Groq Cloud)</span>
              <span className="text-xs font-semibold text-[#A5D8FF] text-right">
                {aiStatus?.api_blocked_blackout
                  ? `Paused (OFFLINE Blackout · ${aiStatus.api_model || 'qwen/qwen3.8-27b'})`
                  : aiStatus?.api_key_configured
                    ? aiStatus?.llm_provider === 'api' && aiStatus?.llm_active
                      ? `Active (${aiStatus.api_model || 'qwen/qwen3.8-27b'}) · ${aiStatus.api_key_status}`
                      : `Ready (${aiStatus.api_model || 'qwen/qwen3.8-27b'}, Standby) · ${aiStatus.api_key_status}`
                    : 'Not Configured (Use Groq Key below)'}
              </span>
            </div>
          </div>

          <div className="pt-2 border-t border-white/[0.08]">
            <AIProviderSwitcher
              aiStatus={aiStatus}
              variant="panel"
              onStateUpdated={onStateUpdated}
              onNotice={setAiNotice}
            />
          </div>

          {aiNotice && (
            <div className="rounded-xl bg-[#0B0D1A] px-3.5 py-2.5 text-xs text-[#A5D8FF] border border-[#A5D8FF]/30">
              {aiNotice}
            </div>
          )}
        </div>
      </section>

      <DonkiSpaceWeatherPanel
        state={state}
        onStateUpdated={onStateUpdated}
        compact
        onOpenSpaceRadiation={onOpenSpaceRadiation}
      />

      <InsightWeatherPanel
        state={state}
        onStateUpdated={onStateUpdated}
        compact
        onOpenEnvironment={onOpenEnvironment}
      />
    </div>
  );
};

