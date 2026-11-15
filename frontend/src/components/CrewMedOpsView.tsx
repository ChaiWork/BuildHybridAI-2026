import React, { useState } from 'react';
import {
  CheckCircle2,
  ClipboardCheck,
  Download,
  Lock,
  PackageCheck,
  Send,
  ShieldAlert,
  Unlock,
  Users,
} from 'lucide-react';
import { FullSystemState, RiskLevel } from '../types';
import { apiRequest, statusMeta } from './uiHelpers';

interface CrewMedOpsViewProps {
  state: FullSystemState;
  unlockedCrewIds: Record<string, boolean>;
  onUnlockCrew: (crewId: string) => void;
  onLockCrew: (crewId: string) => void;
  onStateUpdated: (next: FullSystemState) => void;
  onOpenSansModal: () => void;
}

function evaBadgeClass(status: string): string {
  if (status === 'HOLD') return 'bg-red-500/15 text-red-300 border border-red-500/35';
  if (status === 'CAUTION') return 'bg-amber-500/15 text-amber-300 border border-amber-500/35';
  return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/35';
}

export const CrewMedOpsView: React.FC<CrewMedOpsViewProps> = ({
  state,
  unlockedCrewIds,
  onUnlockCrew,
  onLockCrew,
  onStateUpdated,
  onOpenSansModal,
}) => {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // PIN verification & update controls
  const [pinCrewId, setPinCrewId] = useState<string>(state.active_crew_id || state.astronaut.astronaut_id);
  const [pinInput, setPinInput] = useState('');
  const [pinMsg, setPinMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // Consult draft builder state
  const [cmoNotes, setCmoNotes] = useState('');
  const [consultUrgency, setConsultUrgency] = useState<RiskLevel>(
    state.assessment.overall_status === 'CRITICAL' ? 'CRITICAL' : 'WARNING',
  );
  const [includeSans, setIncludeSans] = useState(true);
  const [consultMarkdown, setConsultMarkdown] = useState<string | null>(null);

  const fleet = state.crew_fleet_matrix || [];
  const medKit = state.medical_kit || [];
  const activeCrewId = state.active_crew_id || state.astronaut.astronaut_id;

  const selectCrewMember = async (crewId: string) => {
    setBusyKey(`select-${crewId}`);
    setNotice(null);
    try {
      const next = await apiRequest<FullSystemState>('/api/crew/select', {
        method: 'POST',
        body: JSON.stringify({ crew_id: crewId }),
      });
      onStateUpdated(next);
      setPinCrewId(crewId);
      setNotice({
        kind: 'ok',
        text: `Switched active monitoring focus to ${next.astronaut.name} (${next.astronaut.role}).`,
      });
    } catch (err) {
      setNotice({ kind: 'err', text: err instanceof Error ? err.message : 'Unable to switch crew profile.' });
    } finally {
      setBusyKey(null);
    }
  };

  const handleUnlockPin = async (e: React.FormEvent) => {
    e.preventDefault();
    setPinMsg(null);
    setBusyKey('unlock-pin');
    try {
      await apiRequest('/api/crew/unlock-reflections', {
        method: 'POST',
        body: JSON.stringify({ crew_id: pinCrewId, pin: pinInput }),
      });
      onUnlockCrew(pinCrewId);
      setPinInput('');
      setPinMsg({
        kind: 'ok',
        text: `Behavioral journal reflections unlocked locally for ${pinCrewId} (visible inside Health History).`,
      });
    } catch (err) {
      setPinMsg({
        kind: 'err',
        text: err instanceof Error ? err.message : 'Invalid Privacy PIN. Reflections remain locked.',
      });
    } finally {
      setBusyKey(null);
    }
  };

  const adjustKitItem = async (
    itemCode: string,
    opts: { quantity_delta?: number; mark_inspected?: boolean },
  ) => {
    setBusyKey(`kit-${itemCode}`);
    setNotice(null);
    try {
      const res = await apiRequest<{ state: FullSystemState }>('/api/medkit/adjust', {
        method: 'POST',
        body: JSON.stringify({
          item_code: itemCode,
          quantity_delta: opts.quantity_delta,
          mark_inspected: Boolean(opts.mark_inspected),
        }),
      });
      onStateUpdated(res.state);
      setNotice({
        kind: 'ok',
        text: `Updated local onboard Medical Kit item ${itemCode}.`,
      });
    } catch (err) {
      setNotice({
        kind: 'err',
        text: err instanceof Error ? err.message : 'Unable to update Medical Kit record.',
      });
    } finally {
      setBusyKey(null);
    }
  };

  const generateConsultDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusyKey('consult');
    setNotice(null);
    try {
      const res = await apiRequest<{
        report: { report_uid: string; transmission_status: string };
        markdown_preview: string;
        state: FullSystemState;
      }>('/api/consult/flight-surgeon-draft', {
        method: 'POST',
        body: JSON.stringify({
          cmo_notes: cmoNotes,
          urgency: consultUrgency,
          include_sans: includeSans,
        }),
      });
      onStateUpdated(res.state);
      setConsultMarkdown(res.markdown_preview);
      setNotice({
        kind: 'ok',
        text: `Consult packet ${res.report.report_uid} prepared (${res.report.transmission_status}) with zero automated prescriptions and private journals redacted.`,
      });
    } catch (err) {
      setNotice({
        kind: 'err',
        text: err instanceof Error ? err.message : 'Unable to draft Earth Flight Surgeon consultation.',
      });
    } finally {
      setBusyKey(null);
    }
  };

  const downloadConsultMarkdown = () => {
    if (!consultMarkdown) return;
    const blob = new Blob([consultMarkdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tarscare-consult-${state.astronaut.astronaut_id.toLowerCase()}-sol-${state.latest_telemetry.mission_day}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <section className="mc-card p-5 lg:p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#A5D8FF]">
            <Users className="w-4 h-4" />
            <span>CREW MEDICAL OFFICER (CMO) &amp; MISSION OPS</span>
          </div>
          <h1 className="text-2xl font-bold text-[#FAF9FA] mt-1">
            Multi-Crew Triage Matrix, Onboard Medical Kit &amp; Consult Builder
          </h1>
          <p className="text-sm text-[#E5E5E4]/80 mt-1">
            Monitor all four Ares-Horizon IV crewmates side-by-side while isolating private behavioral journals behind per-crewmember PINs.
          </p>
        </div>

        <button
          type="button"
          onClick={onOpenSansModal}
          className="mc-btn-secondary px-4 py-2 text-xs inline-flex items-center gap-1.5"
        >
          <ClipboardCheck className="w-4 h-4 text-[#A5D8FF]" />
          <span>Run SANS Amsler Vision Check</span>
        </button>
      </section>

      {notice && (
        <div
          className={`rounded-xl px-4 py-3 text-xs border ${
            notice.kind === 'err'
              ? 'border-red-500/40 bg-red-500/12 text-red-100'
              : 'border-[#A5D8FF]/35 bg-[#0B0D1A] text-[#A5D8FF]'
          }`}
        >
          {notice.text}
        </div>
      )}

      {/* Multi-Crew CMO Triage Matrix */}
      <section className="mc-card p-5 lg:p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA]">Crew Triage &amp; EVA Readiness Matrix</h2>
            <p className="text-xs text-[#E5E5E4]/75">
              Sorted automatically by highest medical acuity. Private journal reflections are never exposed in crew fleet summaries.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#0B0D1A] border border-white/10 text-xs text-[#94A3B8]">
            <Lock className="w-3.5 h-3.5 text-[#A5D8FF]" />
            <span>Journals Redacted in Fleet Matrix</span>
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse min-w-[820px]">
            <thead>
              <tr className="border-b border-white/10 text-[#94A3B8]">
                <th className="py-2.5 px-2.5">Crew Member</th>
                <th className="py-2.5 px-2.5">Triage Status</th>
                <th className="py-2.5 px-2.5">EVA Readiness</th>
                <th className="py-2.5 px-2.5">HR (Δ Base)</th>
                <th className="py-2.5 px-2.5">BP / SpO₂</th>
                <th className="py-2.5 px-2.5">Sleep / Rad</th>
                <th className="py-2.5 px-2.5">Priority Directive</th>
                <th className="py-2.5 px-2.5 text-right">Focus</th>
              </tr>
            </thead>
            <tbody>
              {fleet.map((member) => {
                const st = statusMeta(member.overall_status);
                const isSelected = member.crew_id === activeCrewId;
                return (
                  <tr
                    key={member.crew_id}
                    className={`border-b border-white/[0.06] ${
                      isSelected ? 'bg-[#A5D8FF]/[0.08]' : 'hover:bg-white/[0.02]'
                    }`}
                  >
                    <td className="py-3 px-2.5">
                      <div className="font-semibold text-[#FAF9FA] flex items-center gap-1.5">
                        <span>{member.name}</span>
                        {isSelected && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#A5D8FF]/20 text-[#A5D8FF]">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-[#94A3B8]">{member.role} · Sol {member.mission_day}</div>
                    </td>
                    <td className="py-3 px-2.5">
                      <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${st.badgeClass}`}>
                        {st.label}
                      </span>
                      {member.sans_flagged && (
                        <div className="text-[10px] text-amber-300 mt-1">SANS Eye Flag</div>
                      )}
                    </td>
                    <td className="py-3 px-2.5">
                      <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${evaBadgeClass(member.eva_status)}`}>
                        {member.eva_status} ({member.eva_score_pct}%)
                      </span>
                    </td>
                    <td className="py-3 px-2.5 tabular-data text-[#FAF9FA]">
                      {member.heart_rate_bpm} BPM{' '}
                      <span className="text-[#94A3B8]">
                        ({member.hr_delta >= 0 ? `+${member.hr_delta}` : member.hr_delta})
                      </span>
                    </td>
                    <td className="py-3 px-2.5 tabular-data text-[#FAF9FA]">
                      {member.bp_summary} · {member.spo2_pct}%
                    </td>
                    <td className="py-3 px-2.5 tabular-data text-[#E5E5E4]">
                      {member.sleep_duration_hrs}h · {member.cumulative_dose_msv} mSv
                    </td>
                    <td className="py-3 px-2.5 max-w-xs text-[#E5E5E4]/85">
                      <span className="line-clamp-2">{member.priority_headline}</span>
                    </td>
                    <td className="py-3 px-2.5 text-right">
                      <button
                        type="button"
                        disabled={isSelected || busyKey === `select-${member.crew_id}`}
                        onClick={() => selectCrewMember(member.crew_id)}
                        className={`px-3 py-1.5 rounded-full text-[11px] font-semibold ${
                          isSelected
                            ? 'bg-white/10 text-[#94A3B8] cursor-default'
                            : 'mc-btn-secondary'
                        }`}
                      >
                        {isSelected ? 'Selected' : 'Monitor Crewmate'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Behavioral Privacy PIN Unlock Bar */}
        <form
          onSubmit={handleUnlockPin}
          className="rounded-xl bg-[#0B0D1A] border border-white/[0.08] p-4 flex flex-wrap items-end gap-3"
        >
          <div>
            <label htmlFor="pin-crew-select" className="block text-[11px] text-[#94A3B8] mb-1">
              Behavioral Journal Access Target
            </label>
            <select
              id="pin-crew-select"
              name="pin_crew_id"
              value={pinCrewId}
              onChange={(e) => setPinCrewId(e.target.value)}
              className="rounded-lg bg-[#121522] border border-white/15 px-3 py-1.5 text-xs text-[#FAF9FA]"
            >
              {fleet.map((m) => (
                <option key={m.crew_id} value={m.crew_id}>
                  {m.name} {unlockedCrewIds[m.crew_id] ? '(Unlocked)' : '(Locked)'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="crew-privacy-pin-input" className="block text-[11px] text-[#94A3B8] mb-1">
              Privacy PIN ({state.privacy_pin_hint || 'Default demo PIN: 2026'})
            </label>
            <input
              id="crew-privacy-pin-input"
              name="privacy_pin"
              type="password"
              autoComplete="current-password"
              value={pinInput}
              onChange={(e) => setPinInput(e.target.value)}
              placeholder="Enter 4+ digit PIN"
              className="rounded-lg bg-[#121522] border border-white/15 px-3 py-1.5 text-xs text-[#FAF9FA] w-44"
            />
          </div>
          <button
            type="submit"
            disabled={!pinInput.trim() || busyKey === 'unlock-pin'}
            className="mc-btn-primary px-4 py-1.5 text-xs inline-flex items-center gap-1.5"
          >
            <Unlock className="w-3.5 h-3.5" />
            <span>Unlock Private Reflections</span>
          </button>
          {unlockedCrewIds[pinCrewId] && (
            <button
              type="button"
              onClick={() => {
                onLockCrew(pinCrewId);
                setPinMsg({ kind: 'ok', text: `Locked behavioral reflections for ${pinCrewId}.` });
              }}
              className="mc-btn-secondary px-3.5 py-1.5 text-xs inline-flex items-center gap-1.5"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Re-Lock</span>
            </button>
          )}
          {pinMsg && (
            <div className={`w-full text-xs ${pinMsg.kind === 'err' ? 'text-red-300' : 'text-emerald-300'}`}>
              {pinMsg.text}
            </div>
          )}
        </form>
      </section>

      {/* Bottom 2 Columns: Onboard Medical Kit Inventory + Flight Surgeon Consult Draft Builder */}
      <section className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Onboard Medical Kit Inventory */}
        <div className="mc-card p-5 lg:p-6 space-y-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-[#FAF9FA] flex items-center gap-2">
                <PackageCheck className="w-5 h-5 text-[#A5D8FF]" />
                <span>Onboard Medical Operations Kit</span>
              </h2>
              <p className="text-xs text-[#E5E5E4]/75 mt-0.5">
                Offline supply bay locations, reserves, and hardware boundaries. Medications remain sealed for CMO/Earth authorization only.
              </p>
            </div>
          </div>

          <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
            {medKit.map((item) => {
              const isLow = item.quantity <= item.min_threshold;
              return (
                <div key={item.item_code} className="rounded-xl bg-[#0B0D1A] p-3.5 border border-white/[0.07] space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-[#FAF9FA]">
                        {item.name}
                      </div>
                      <div className="text-[11px] text-[#A5D8FF]">
                        {item.item_code} · {item.bay_location} · {item.category}
                      </div>
                    </div>
                    <div className="text-right">
                      <span
                        className={`inline-flex px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                          item.cmo_auth_required
                            ? 'bg-red-500/15 text-red-200 border border-red-500/35'
                            : isLow
                              ? 'bg-amber-500/15 text-amber-300 border border-amber-500/35'
                              : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/35'
                        }`}
                      >
                        {item.quantity} {item.unit}
                      </span>
                      <div className="text-[10px] text-[#94A3B8] mt-0.5">Exp {item.expiry_date}</div>
                    </div>
                  </div>
                  <p className="text-xs text-[#E5E5E4]/80">{item.notes}</p>
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <span className="text-[11px] text-[#94A3B8]">
                      Last check: {item.last_inspected.slice(0, 10)} · Min reserve: {item.min_threshold}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {!item.cmo_auth_required && (
                        <>
                          <button
                            type="button"
                            disabled={busyKey === `kit-${item.item_code}` || item.quantity <= 0}
                            onClick={() => adjustKitItem(item.item_code, { quantity_delta: -1 })}
                            className="px-2.5 py-1 rounded-full bg-[#121522] border border-white/15 text-[11px] text-[#FAF9FA] hover:border-[#A5D8FF]/45 disabled:opacity-40"
                          >
                            Log -1 Used
                          </button>
                          <button
                            type="button"
                            disabled={busyKey === `kit-${item.item_code}`}
                            onClick={() => adjustKitItem(item.item_code, { quantity_delta: 1 })}
                            className="px-2.5 py-1 rounded-full bg-[#121522] border border-white/15 text-[11px] text-[#FAF9FA] hover:border-[#A5D8FF]/45"
                          >
                            +1 Restock
                          </button>
                        </>
                      )}
                      <button
                        type="button"
                        disabled={busyKey === `kit-${item.item_code}`}
                        onClick={() => adjustKitItem(item.item_code, { mark_inspected: true })}
                        className="px-2.5 py-1 rounded-full bg-[#121522] border border-white/15 text-[11px] text-[#A5D8FF] hover:border-[#A5D8FF]/45"
                      >
                        Verify Seal
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Delayed Earth Flight-Surgeon Consult Draft Builder */}
        <div className="mc-card p-5 lg:p-6 space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA] flex items-center gap-2">
              <Send className="w-5 h-5 text-[#A5D8FF]" />
              <span>Delayed Earth Flight-Surgeon Consult Draft</span>
            </h2>
            <p className="text-xs text-[#E5E5E4]/75 mt-0.5">
              Packages {state.astronaut.name}'s calibrated baseline audit, latest vitals, active symptoms, SANS check, and Medical Kit reserve status into a Store-and-Forward Earth consultation report.
            </p>
          </div>

          <form onSubmit={generateConsultDraft} className="space-y-3.5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor="consult-urgency" className="block text-xs text-[#94A3B8] mb-1">
                  Consult Priority Tier
                </label>
                <select
                  id="consult-urgency"
                  name="consult_urgency"
                  value={consultUrgency}
                  onChange={(e) => setConsultUrgency(e.target.value as RiskLevel)}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-white/15 px-3 py-2 text-xs text-[#FAF9FA]"
                >
                  <option value="NORMAL">Routine Async Check-In</option>
                  <option value="WARNING">Priority Review (Warning)</option>
                  <option value="CRITICAL">Priority-1 Medical Consult (Critical)</option>
                </select>
              </div>
              <label
                htmlFor="consult-include-sans"
                className="flex items-center gap-2 rounded-lg bg-[#0B0D1A] border border-white/10 px-3 py-2 text-xs text-[#FAF9FA] mt-5 cursor-pointer"
              >
                <input
                  id="consult-include-sans"
                  name="include_sans"
                  type="checkbox"
                  checked={includeSans}
                  onChange={(e) => setIncludeSans(e.target.checked)}
                />
                <span>Attach latest SANS Amsler result</span>
              </label>
            </div>

            <div>
              <label htmlFor="consult-cmo-notes" className="block text-xs text-[#94A3B8] mb-1">
                CMO Physical Exam &amp; Clinical Observations
              </label>
              <textarea
                id="consult-cmo-notes"
                name="cmo_notes"
                rows={4}
                value={cmoNotes}
                onChange={(e) => setCmoNotes(e.target.value)}
                placeholder="Enter physical exam findings, manual auscultation/ECG observation, oral fluid response, or specific question for Earth Flight Surgeons..."
                className="w-full rounded-xl bg-[#0B0D1A] border border-white/15 p-3 text-xs text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none"
              />
            </div>

            <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 p-3 text-[11px] text-amber-200 flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Non-prescribing guarantee: Consult packets include hardware status and physiological trends only, leaving any prescription authorization strictly to the CMO and Earth Flight Surgeons.
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="submit"
                disabled={busyKey === 'consult'}
                className="mc-btn-primary px-5 py-2.5 text-xs inline-flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{busyKey === 'consult' ? 'Packaging Consult...' : 'Draft & Queue Flight Surgeon Consult'}</span>
              </button>
              {consultMarkdown && (
                <button
                  type="button"
                  onClick={downloadConsultMarkdown}
                  className="mc-btn-secondary px-4 py-2.5 text-xs inline-flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5 text-[#A5D8FF]" />
                  <span>Download Consult (.md)</span>
                </button>
              )}
            </div>
          </form>

          {consultMarkdown && (
            <div className="rounded-xl bg-[#0B0D1A] border border-[#A5D8FF]/25 p-3.5 space-y-1.5">
              <div className="text-[11px] uppercase tracking-wider text-[#A5D8FF] font-semibold">
                Queued Store-and-Forward Consult Preview
              </div>
              <pre className="text-[11px] text-[#E5E5E4]/90 whitespace-pre-wrap max-h-56 overflow-y-auto font-mono leading-relaxed">
                {consultMarkdown}
              </pre>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
