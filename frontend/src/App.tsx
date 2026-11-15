import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Contrast,
  HeartPulse,
  Mic,
  MicOff,
  Radio,
  RotateCcw,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Square,
  Users,
  Volume2,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import { EmergencyProtocolResult, FullSystemState } from './types';
import {
  apiRequest,
  buildClientFallbackEmergencyProtocol,
  buildEmergencyPayload,
  provenanceLabel,
  statusMeta,
} from './components/uiHelpers';
import { BaselineModal } from './components/BaselineModal';
import { MissionOverviewView } from './components/MissionOverviewView';
import { HealthAssessmentView } from './components/HealthAssessmentView';
import { SpaceflightHazardsView } from './components/SpaceflightHazardsView';
import { AIHealthAssistantView } from './components/AIHealthAssistantView';
import { CrewMedOpsView } from './components/CrewMedOpsView';
import { MedicalDevicesView } from './components/MedicalDevicesView';
import { SansAmslerModal } from './components/SansAmslerModal';
import {
  isSpeechRecognitionSupported,
  isSpeechSynthesisSupported,
  parseVoiceTriageCommand,
  speakText,
  startVoiceCommandListener,
  stopSpeaking,
} from './components/voiceHelpers';
import {
  CommunicationStatusView,
  HealthHistoryView,
} from './components/HealthHistoryAndCommViews';

type NavTab =
  | 'overview'
  | 'assessment'
  | 'devices'
  | 'hazards'
  | 'ops'
  | 'assistant'
  | 'history'
  | 'comm';

const NAV_ITEMS: { id: NavTab; label: string }[] = [
  { id: 'overview', label: 'Mission Overview' },
  { id: 'assessment', label: 'Health Assessment' },
  { id: 'devices', label: 'Medical Devices' },
  { id: 'hazards', label: 'Spaceflight Hazards' },
  { id: 'ops', label: 'Crew & Med Ops' },
  { id: 'assistant', label: 'AI Health Assistant' },
  { id: 'history', label: 'Health History' },
  { id: 'comm', label: 'Communication Status' },
];

export default function App() {
  const [state, setState] = useState<FullSystemState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<NavTab>('overview');
  const [selectedRegionId, setSelectedRegionId] = useState<string>('heart');
  const [activeHazardId, setActiveHazardId] = useState<string>('radiation');
  const [assistantSeedPrompt, setAssistantSeedPrompt] = useState<string | undefined>(undefined);
  const [deviceFocusCategory, setDeviceFocusCategory] = useState<string>('all');
  const [deviceFocusId, setDeviceFocusId] = useState<string | undefined>(undefined);

  // Multi-crew privacy unlock & SANS Amsler modal state
  const [unlockedCrewIds, setUnlockedCrewIds] = useState<Record<string, boolean>>({});
  const [sansModalOpen, setSansModalOpen] = useState(false);
  const [crewSwitching, setCrewSwitching] = useState(false);

  // Emergency Modal State + High-Contrast EVA Mode + Offline Voice Assist
  const [emergencyOpen, setEmergencyOpen] = useState(false);
  const [emergencyProtocol, setEmergencyProtocol] = useState<EmergencyProtocolResult | null>(null);
  const [emergencyHazard, setEmergencyHazard] = useState<string>('Cardiopulmonary & Chest Triage');
  const [emergencyLoading, setEmergencyLoading] = useState(false);
  const [emergencyError, setEmergencyError] = useState<string | null>(null);
  const [highContrastEva, setHighContrastEva] = useState(false);
  const [activeStepIdx, setActiveStepIdx] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Record<number, boolean>>({});
  const [elapsedSec, setElapsedSec] = useState(0);
  const [voiceSpeaking, setVoiceSpeaking] = useState(false);
  const [voiceListening, setVoiceListening] = useState(false);
  const [voiceStatusMsg, setVoiceStatusMsg] = useState<string | null>(null);
  const voiceStopRef = useRef<(() => void) | null>(null);

  // Baseline Calibration & Reset Confirmation Modals
  const [baselineOpen, setBaselineOpen] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const donkiAutoSyncRef = useRef(false);
  const insightAutoSyncRef = useRef(false);

  const loadState = useCallback(async () => {
    try {
      setError(null);
      const data = await apiRequest<FullSystemState>('/api/state');
      setState(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to reach onboard TARS Care telemetry backend.',
      );
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  useEffect(() => {
    if (!state) return;
    const mode = state.assessment?.comm_mode?.mode;
    if (mode === 'OFFLINE') return;

    const needDonki = !donkiAutoSyncRef.current && state.donki_state?.sync_meta?.last_sync_status === 'NEVER_SYNCED';
    const needInsight = !insightAutoSyncRef.current && state.insight_state?.sync_meta?.last_sync_status === 'NEVER_SYNCED';
    if (!needDonki && !needInsight) return;

    if (needDonki) donkiAutoSyncRef.current = true;
    if (needInsight) insightAutoSyncRef.current = true;

    const timer = window.setTimeout(async () => {
      try {
        const refreshed = await apiRequest<FullSystemState>('/api/state');
        let latestState = refreshed;
        if (needDonki && refreshed.donki_state?.sync_meta?.last_sync_status === 'NEVER_SYNCED') {
          const r1 = await apiRequest<{ state: FullSystemState }>('/api/donki/sync', {
            method: 'POST',
            body: JSON.stringify({}),
          });
          if (r1.state) latestState = r1.state;
        }
        if (needInsight && latestState.insight_state?.sync_meta?.last_sync_status === 'NEVER_SYNCED') {
          const r2 = await apiRequest<{ state: FullSystemState }>('/api/insight/sync', {
            method: 'POST',
            body: JSON.stringify({ feedtype: 'json', version: '1.0' }),
          });
          if (r2.state) latestState = r2.state;
        }
        setState(latestState);
      } catch {
        // Offline / rate-limited failure never blocks core telemetry operation
      }
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [state]);

  const handleConfirmResetDemo = async () => {
    setResetLoading(true);
    try {
      donkiAutoSyncRef.current = false;
      insightAutoSyncRef.current = false;
      const resetState = await apiRequest<FullSystemState>('/api/reset', { method: 'POST' });
      setState(resetState);
      setUnlockedCrewIds({});
      setResetConfirmOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset database.');
    } finally {
      setResetLoading(false);
    }
  };

  const handleSwitchCrew = async (nextCrewId: string) => {
    setCrewSwitching(true);
    try {
      const nextState = await apiRequest<FullSystemState>('/api/crew/select', {
        method: 'POST',
        body: JSON.stringify({ crew_id: nextCrewId }),
      });
      setState(nextState);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to switch crew profile.');
    } finally {
      setCrewSwitching(false);
    }
  };

  const triggerEmergencyProtocol = async (hazardName?: string) => {
    const recommendedHazard =
      hazardName ||
      state?.assessment.recommended_emergency_hazard ||
      emergencyHazard;
    setEmergencyHazard(recommendedHazard);
    setEmergencyOpen(true);
    setEmergencyLoading(true);
    setEmergencyError(null);
    setActiveStepIdx(0);
    setCompletedSteps({});
    setElapsedSec(0);
    setVoiceStatusMsg(null);
    stopSpeaking();
    setVoiceSpeaking(false);
    if (state?.assessment.overall_status === 'CRITICAL') {
      setHighContrastEva(true);
    }

    try {
      if (!state) {
        throw new Error('Telemetry state not loaded yet.');
      }
      const payload = buildEmergencyPayload(state, recommendedHazard);
      const res = await apiRequest<{ protocol: EmergencyProtocolResult; state?: FullSystemState }>(
        '/api/emergency/escalate',
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      );
      if (res && res.protocol && Array.isArray(res.protocol.immediate_steps)) {
        setEmergencyProtocol(res.protocol);
        if (res.protocol.severity === 'CRITICAL') {
          setHighContrastEva(true);
        }
        if (res.state) setState(res.state);
      } else {
        throw new Error('Malformed protocol response from local backend.');
      }
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Local backend API unreachable — switched to built-in deterministic fallback checklist.';
      setEmergencyError(msg);
      setEmergencyProtocol(
        buildClientFallbackEmergencyProtocol(state, recommendedHazard, [], msg),
      );
    } finally {
      setEmergencyLoading(false);
    }
  };

  useEffect(() => {
    if (!emergencyOpen) {
      stopSpeaking();
      voiceStopRef.current?.();
      voiceStopRef.current = null;
      setVoiceSpeaking(false);
      setVoiceListening(false);
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSec((prev) => prev + 1);
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [emergencyOpen]);

  useEffect(() => {
    return () => {
      stopSpeaking();
      voiceStopRef.current?.();
    };
  }, []);

  const speakProtocolSteps = (mode: 'all' | 'current', overrideIdx?: number) => {
    if (!emergencyProtocol || emergencyProtocol.immediate_steps.length === 0) return;
    if (!isSpeechSynthesisSupported()) {
      setVoiceStatusMsg('Speech synthesis unavailable in this browser environment; follow visual checklist.');
      return;
    }
    const steps = emergencyProtocol.immediate_steps;
    const idx = Math.min(overrideIdx ?? activeStepIdx, steps.length - 1);
    const text =
      mode === 'all'
        ? `${emergencyProtocol.protocol_title}. ${steps.map((s, i) => `Step ${i + 1}: ${s}`).join('. ')}`
        : `Step ${idx + 1} of ${steps.length}: ${steps[idx]}`;
    setVoiceSpeaking(true);
    setVoiceStatusMsg(
      mode === 'all'
        ? `Reading all ${steps.length} deterministic emergency steps aloud.`
        : `Reading step ${idx + 1} of ${steps.length}.`,
    );
    speakText(text, {
      onEnd: () => setVoiceSpeaking(false),
      onError: () => {
        setVoiceSpeaking(false);
        setVoiceStatusMsg('Voice readout stopped or unsupported.');
      },
    });
  };

  const applyVoiceCommandText = (rawCommand: string) => {
    const parsed = parseVoiceTriageCommand(rawCommand);
    if (!parsed) {
      setVoiceStatusMsg(`Heard "${rawCommand}" — try "next step", "confirm step", "read step", or "high contrast".`);
      return;
    }
    const totalSteps = emergencyProtocol?.immediate_steps.length ?? 0;
    setVoiceStatusMsg(`Voice command: ${parsed.label}`);
    if (parsed.action === 'STOP_VOICE') {
      stopSpeaking();
      setVoiceSpeaking(false);
    } else if (parsed.action === 'READ_STEPS') {
      speakProtocolSteps('current');
    } else if (parsed.action === 'NEXT_STEP' && totalSteps > 0) {
      const nextIdx = Math.min(activeStepIdx + 1, totalSteps - 1);
      setActiveStepIdx(nextIdx);
      if (isSpeechSynthesisSupported()) speakProtocolSteps('current', nextIdx);
    } else if (parsed.action === 'PREV_STEP' && totalSteps > 0) {
      const prevIdx = Math.max(activeStepIdx - 1, 0);
      setActiveStepIdx(prevIdx);
      if (isSpeechSynthesisSupported()) speakProtocolSteps('current', prevIdx);
    } else if (parsed.action === 'CONFIRM_STEP' && totalSteps > 0) {
      setCompletedSteps((prev) => ({ ...prev, [activeStepIdx]: true }));
      const nextIdx = Math.min(activeStepIdx + 1, totalSteps - 1);
      setActiveStepIdx(nextIdx);
    } else if (parsed.action === 'TOGGLE_HIGH_CONTRAST') {
      setHighContrastEva((prev) => !prev);
    } else if (parsed.action === 'SWITCH_HAZARD' && parsed.hazard) {
      void triggerEmergencyProtocol(parsed.hazard);
    } else if (parsed.action === 'ADD_SYMPTOM' && parsed.symptom) {
      const sym = parsed.symptom;
      setEmergencyProtocol((prev) => {
        if (!prev) return prev;
        const existing = prev.reported_symptoms || [];
        if (existing.includes(sym)) return prev;
        return { ...prev, reported_symptoms: [...existing, sym] };
      });
    }
  };

  const handleToggleVoiceCommand = () => {
    if (voiceListening) {
      voiceStopRef.current?.();
      voiceStopRef.current = null;
      setVoiceListening(false);
      return;
    }
    if (!isSpeechRecognitionSupported()) {
      setVoiceStatusMsg('Microphone SpeechRecognition unavailable here; use tactile voice-action chips below.');
      return;
    }
    setVoiceListening(true);
    setVoiceStatusMsg('Listening for hands-free command ("next step", "confirm step", "read step", "chest pain")...');
    voiceStopRef.current = startVoiceCommandListener({
      onResult: (transcript) => applyVoiceCommandText(transcript),
      onError: (message) => {
        setVoiceStatusMsg(message);
        setVoiceListening(false);
      },
      onEnd: () => {
        setVoiceListening(false);
        voiceStopRef.current = null;
      },
    });
  };

  useEffect(() => {
    if (!emergencyOpen && !resetConfirmOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setEmergencyOpen(false);
        setResetConfirmOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [emergencyOpen, resetConfirmOpen]);

  if (!state) {
    return (
      <div className="min-h-screen bg-[#0B0D1A] text-[#FAF9FA] flex items-center justify-center p-6">
        <div className="mc-card p-8 max-w-md w-full text-center space-y-4">
          <div className="w-10 h-10 rounded-full bg-[#A5D8FF]/20 border border-[#A5D8FF]/40 flex items-center justify-center mx-auto">
            <HeartPulse className="w-5 h-5 text-[#A5D8FF]" />
          </div>
          <h1 className="text-xl font-bold">TARS Care</h1>
          <p className="text-sm text-[#E5E5E4]/80">
            {error
              ? `Connection notice: ${error}`
              : 'Connecting to autonomous onboard health storage...'}
          </p>
          {error && (
            <button type="button" onClick={loadState} className="mc-btn-primary px-6 py-2.5 text-sm">
              Retry Connection
            </button>
          )}
        </div>
      </div>
    );
  }

  const commMode = state.assessment.comm_mode?.mode || 'DELAYED';
  const commLabel = state.assessment.comm_mode?.label || 'Delayed';
  const overallMeta = statusMeta(state.assessment.overall_status);

  return (
    <div className="min-h-screen bg-[#0B0D1A] text-[#FAF9FA] flex flex-col">
      {/* Main Application Header: Navigation + Astronaut Profile + Mission Day + Comm Status */}
      <header className="bg-[#0B0D1A] border-b border-white/[0.08]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-2.5 space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Brand */}
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-full bg-[#121522] border border-[#A5D8FF]/45 flex items-center justify-center"
                style={{ boxShadow: '0 0 18px rgba(165,216,255,0.22)' }}
              >
                <Sparkles className="w-4 h-4 text-[#A5D8FF]" />
              </div>
              <div>
                <div className="text-base font-bold tracking-tight text-[#FAF9FA]">TARS Care</div>
                <div className="text-xs text-[#E5E5E4]/75">
                  Personal Health Companion in Deep Space
                </div>
              </div>
            </div>

            {/* Astronaut Profile, Crew Switcher, Mission Day & Communication Status */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-2.5">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#121522] border border-white/[0.08]">
                <Users className="w-3.5 h-3.5 text-[#A5D8FF] shrink-0" />
                <label htmlFor="header-crew-select" className="sr-only">
                  Active Crew Member
                </label>
                <select
                  id="header-crew-select"
                  name="active_crew_id"
                  aria-label="Active Crew Member"
                  disabled={crewSwitching}
                  value={state.active_crew_id || state.astronaut.astronaut_id}
                  onChange={(e) => handleSwitchCrew(e.target.value)}
                  className="bg-transparent text-xs font-medium text-[#FAF9FA] focus:outline-none cursor-pointer pr-1"
                >
                  {(state.crew_fleet_matrix && state.crew_fleet_matrix.length > 0
                    ? state.crew_fleet_matrix
                    : [
                        {
                          crew_id: state.astronaut.astronaut_id,
                          name: state.astronaut.name,
                          role: state.astronaut.role,
                        },
                      ]
                  ).map((cm) => (
                    <option key={cm.crew_id} value={cm.crew_id} className="bg-[#121522] text-[#FAF9FA]">
                      {cm.name} ({cm.role})
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                onClick={() => setBaselineOpen(true)}
                className="px-3.5 py-1.5 rounded-full bg-[#121522] border border-white/[0.08] hover:border-[#A5D8FF]/45 text-xs sm:text-sm text-[#FAF9FA] inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF]"
                title="Calibrate Astronaut Personal Baseline & Profile"
              >
                <Activity className="w-3.5 h-3.5 text-[#A5D8FF]" />
                <span className="font-medium">{state.astronaut.name}</span>
                <span className="text-[#E5E5E4]/65">·</span>
                <span className="tabular-data text-[#A5D8FF] font-semibold">
                  Sol {state.latest_telemetry.mission_day}
                </span>
                <SlidersHorizontal className="w-3.5 h-3.5 text-[#94A3B8]" />
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('comm')}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF] ${commMode === 'CONNECTED'
                  ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                  : commMode === 'OFFLINE'
                    ? 'bg-red-500/15 text-red-300 border border-red-500/30'
                    : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                  }`}
              >
                {commMode === 'OFFLINE' ? (
                  <WifiOff className="w-3.5 h-3.5" />
                ) : (
                  <Wifi className="w-3.5 h-3.5" />
                )}
                <span>{commLabel}</span>
              </button>

              <button
                type="button"
                onClick={() => triggerEmergencyProtocol()}
                className={`px-3.5 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF] ${overallMeta.badgeClass}`}
                title="Open Autonomous Emergency Escalation Checklist"
              >
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>Status: {overallMeta.label}</span>
              </button>

              <button
                type="button"
                onClick={() => setResetConfirmOpen(true)}
                className="p-2 rounded-full bg-[#121522] border border-white/[0.08] text-[#E5E5E4]/80 hover:text-[#FAF9FA] hover:border-[#A5D8FF]/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF]"
                title="Reset Demo Dataset to Sol 155–184 Baseline"
                aria-label="Reset Demo Dataset"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

        {/* 7 Main Navigation Items */}
        <nav aria-label="Main navigation" className="flex items-center gap-2 overflow-x-auto pb-1">
          {NAV_ITEMS.map((item) => {
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveTab(item.id)}
                className={`px-4 py-2 rounded-full text-xs sm:text-sm font-medium whitespace-nowrap transition-all duration-150 ${active
                  ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                  : 'bg-[#121522] text-[#E5E5E4] border border-white/[0.06] hover:border-[#A5D8FF]/40 hover:text-[#FAF9FA]'
                  }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>

    {/* Main Content Workspace */}
    <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-3.5">
      {activeTab === 'overview' && (
        <MissionOverviewView
          state={state}
          selectedRegionId={selectedRegionId}
          onSelectRegion={setSelectedRegionId}
          onStartAssessment={(regionId) => {
            if (regionId) setSelectedRegionId(regionId);
            setActiveTab('assessment');
          }}
          onOpenHazard={(hazardId) => {
            setActiveHazardId(hazardId);
            setActiveTab('hazards');
          }}
          onAskAssistant={(prompt) => {
            setAssistantSeedPrompt(`${prompt} [Sol ${state.latest_telemetry.mission_day}]`);
            setActiveTab('assistant');
          }}
          onOpenEmergency={() => triggerEmergencyProtocol()}
          onOpenSansModal={() => setSansModalOpen(true)}
          onOpenOps={() => setActiveTab('ops')}
        />
      )}

      {activeTab === 'assessment' && (
        <HealthAssessmentView
          state={state}
          focusedRegionId={selectedRegionId}
          onStateUpdated={setState}
          onOpenEmergency={(hz?: string) => triggerEmergencyProtocol(hz)}
          onOpenSansModal={() => setSansModalOpen(true)}
          onOpenDevices={(opts) => {
            setDeviceFocusCategory(opts?.category || 'all');
            setDeviceFocusId(opts?.deviceId);
            setActiveTab('devices');
          }}
        />
      )}

      {activeTab === 'devices' && (
        <MedicalDevicesView
          state={state}
          onStateUpdated={setState}
          initialCategory={deviceFocusCategory}
          initialDeviceId={deviceFocusId}
          onNavigateTab={(tab) => setActiveTab(tab)}
          onOpenSansModal={() => setSansModalOpen(true)}
        />
      )}

      {activeTab === 'hazards' && (
        <SpaceflightHazardsView
          state={state}
          activeHazardId={activeHazardId}
          onSelectHazard={setActiveHazardId}
          onStateUpdated={setState}
          onAskAssistant={(prompt) => {
            setAssistantSeedPrompt(prompt);
            setActiveTab('assistant');
          }}
          onOpenSansModal={() => setSansModalOpen(true)}
        />
      )}

      {activeTab === 'ops' && (
        <CrewMedOpsView
          state={state}
          unlockedCrewIds={unlockedCrewIds}
          onUnlockCrew={(cid) => setUnlockedCrewIds((prev) => ({ ...prev, [cid]: true }))}
          onLockCrew={(cid) => setUnlockedCrewIds((prev) => ({ ...prev, [cid]: false }))}
          onStateUpdated={setState}
          onOpenSansModal={() => setSansModalOpen(true)}
        />
      )}

      {activeTab === 'assistant' && (
        <AIHealthAssistantView
          state={state}
          initialPrompt={assistantSeedPrompt}
          onStateUpdated={setState}
        />
      )}

      {activeTab === 'history' && (
        <HealthHistoryView
          state={state}
          onStateUpdated={setState}
          unlockedCrewIds={unlockedCrewIds}
          onUnlockCrew={(cid) => setUnlockedCrewIds((prev) => ({ ...prev, [cid]: true }))}
          onLockCrew={(cid) => setUnlockedCrewIds((prev) => ({ ...prev, [cid]: false }))}
        />
      )}

      {activeTab === 'comm' && (
        <CommunicationStatusView
          state={state}
          onStateUpdated={setState}
          onOpenEmergency={() => triggerEmergencyProtocol()}
          onOpenSpaceRadiation={() => {
            setActiveHazardId('radiation');
            setActiveTab('hazards');
          }}
          onOpenEnvironment={() => {
            setActiveHazardId('environment');
            setActiveTab('hazards');
          }}
        />
      )}
    </main>

    {/* Subtle Footer Attribution & Data Distinction Notice */}
    <footer className="border-t border-white/[0.07] py-4 px-4 sm:px-6 lg:px-8 text-xs text-[#E5E5E4]/65">
      <div className="max-w-[1440px] mx-auto flex flex-wrap items-center justify-between gap-2">
        <span>
          TARS Care · Autonomous local RAG &amp; SQLite engine ·{' '}
          {provenanceLabel(state.latest_telemetry.provenance)} active
        </span>
        <span>
          Educational / Space Apps prototype only — does not diagnose conditions, prescribe medications, or replace Flight Surgeon care.
        </span>
      </div>
    </footer>

    {/* Crew Baseline Calibration Modal */}
    {baselineOpen && (
      <BaselineModal
        state={state}
        onClose={() => setBaselineOpen(false)}
        onSaved={(updated) => setState(updated)}
      />
    )}

    {/* Interactive SANS Amsler Vision Check Modal */}
    {sansModalOpen && (
      <SansAmslerModal
        missionDay={state.latest_telemetry.mission_day}
        astronautName={state.astronaut.name}
        history={state.sans_assessments || []}
        onClose={() => setSansModalOpen(false)}
        onSaved={(nextState) => setState(nextState)}
      />
    )}

    {/* Reset Demo Database Confirmation Modal */}
    {resetConfirmOpen && (
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="reset-confirm-title"
        className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
      >
        <div className="mc-card max-w-md w-full p-6 space-y-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <h2 id="reset-confirm-title" className="text-lg font-bold text-[#FAF9FA]">
                Reset Mission Database to Synthetic Baseline?
              </h2>
              <p className="text-sm text-[#E5E5E4]/80 mt-1.5">
                This permanently clears user-entered telemetry logs, psychological check-ins, personalized baseline adjustments, and queued Store-and-Forward reports, restoring Sol 155–184 demo data.
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={() => setResetConfirmOpen(false)}
              className="mc-btn-secondary px-4 py-2 text-xs"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={resetLoading}
              onClick={handleConfirmResetDemo}
              className="px-4 py-2 rounded-full bg-red-500/85 hover:bg-red-500 text-white text-xs font-semibold disabled:opacity-50"
            >
              {resetLoading ? 'Resetting...' : 'Yes, Reset Demo Data'}
            </button>
          </div>
        </div>
      </div>
    )}

    {/* Autonomous Emergency Escalation Checklist Modal */}
    {emergencyOpen && (() => {
      const mm = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
      const ss = String(elapsedSec % 60).padStart(2, '0');
      const totalSteps = emergencyProtocol?.immediate_steps?.length || 0;
      const doneCount = Object.values(completedSteps).filter(Boolean).length;
      return (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Autonomous Emergency Escalation Checklist"
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4"
        >
          <div
            className={`max-w-3xl w-full p-5 sm:p-6 space-y-4 max-h-[92vh] overflow-y-auto rounded-2xl transition-colors ${
              highContrastEva
                ? 'bg-black border-2 border-amber-300 text-white shadow-[0_0_40px_rgba(252,211,77,0.28)]'
                : 'mc-card-glow'
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2
                    className={`font-bold ${
                      highContrastEva ? 'text-xl sm:text-2xl text-amber-300' : 'text-xl text-[#FAF9FA]'
                    }`}
                  >
                    Autonomous Emergency Escalation Checklist
                  </h2>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold ${
                      highContrastEva
                        ? 'bg-amber-300 text-black'
                        : 'bg-[#0B0D1A] text-[#A5D8FF] border border-[#A5D8FF]/30'
                    }`}
                  >
                    <Clock className="w-3.5 h-3.5" />
                    <span>T+{mm}:{ss}</span>
                  </span>
                  {totalSteps > 0 && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-200 border border-emerald-400/40">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>
                        {doneCount}/{totalSteps} Done
                      </span>
                    </span>
                  )}
                </div>
                <p className={`text-xs mt-1 ${highContrastEva ? 'text-white/90' : 'text-[#E5E5E4]/80'}`}>
                  Executes instantaneously onboard with deterministic local procedures — zero Earth or LLM link required.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setHighContrastEva((prev) => !prev)}
                  className={`px-3 py-2 rounded-full text-xs font-bold inline-flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF] ${
                    highContrastEva
                      ? 'bg-amber-300 text-black'
                      : 'bg-[#0B0D1A] text-[#FAF9FA] border border-white/15 hover:border-amber-300/60'
                  }`}
                >
                  <Contrast className="w-3.5 h-3.5" />
                  <span>{highContrastEva ? 'EVA High-Contrast ON' : 'EVA High-Contrast'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setEmergencyOpen(false)}
                  className="p-2 rounded-full bg-[#0B0D1A] text-[#E5E5E4] hover:text-[#FAF9FA] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF]"
                  aria-label="Close modal"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Offline Web Speech Readout & Hands-Free Voice Command Controls */}
            <div
              className={`rounded-xl p-3 flex flex-wrap items-center justify-between gap-2 border ${
                highContrastEva
                  ? 'bg-[#0A0A0A] border-white/30'
                  : 'bg-[#0B0D1A] border-white/[0.08]'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={!emergencyProtocol || !isSpeechSynthesisSupported()}
                  onClick={() => speakProtocolSteps('all')}
                  className="px-3 py-2 min-h-[40px] rounded-xl bg-[#181C2E] hover:bg-[#232844] text-xs font-semibold text-[#A5D8FF] border border-[#A5D8FF]/30 inline-flex items-center gap-1.5 disabled:opacity-45"
                >
                  <Volume2 className="w-3.5 h-3.5" />
                  <span>Read All Steps</span>
                </button>
                <button
                  type="button"
                  disabled={!emergencyProtocol || !isSpeechSynthesisSupported()}
                  onClick={() => {
                    const nextIdx = totalSteps > 0 ? (activeStepIdx + 1) % totalSteps : 0;
                    setActiveStepIdx(nextIdx);
                    speakProtocolSteps('current', nextIdx);
                  }}
                  className="px-3 py-2 min-h-[40px] rounded-xl bg-[#181C2E] hover:bg-[#232844] text-xs font-semibold text-[#FAF9FA] border border-white/15 inline-flex items-center gap-1.5 disabled:opacity-45"
                >
                  <Volume2 className="w-3.5 h-3.5" />
                  <span>Next Step Aloud</span>
                </button>
                {voiceSpeaking && (
                  <button
                    type="button"
                    onClick={() => {
                      stopSpeaking();
                      setVoiceSpeaking(false);
                      setVoiceStatusMsg('Stopped voice readout.');
                    }}
                    className="px-3 py-2 min-h-[40px] rounded-xl bg-red-500/20 hover:bg-red-500/30 text-xs font-semibold text-red-200 border border-red-400/40 inline-flex items-center gap-1.5"
                  >
                    <Square className="w-3.5 h-3.5" />
                    <span>Stop</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleToggleVoiceCommand}
                  className={`px-3 py-2 min-h-[40px] rounded-xl text-xs font-semibold inline-flex items-center gap-1.5 border ${
                    voiceListening
                      ? 'bg-emerald-500/25 text-emerald-200 border-emerald-400/60'
                      : 'bg-[#121522] text-[#E5E5E4] border-white/15 hover:border-[#A5D8FF]/45'
                  }`}
                >
                  {voiceListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                  <span>{voiceListening ? 'Stop Mic' : 'Voice Cmd'}</span>
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {[
                  { label: 'Confirm Step', cmd: 'confirm step' },
                  { label: 'Next Step', cmd: 'next step' },
                  { label: '+ Chest Pain', cmd: 'chest pain' },
                ].map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    onClick={() => applyVoiceCommandText(chip.cmd)}
                    className="px-2.5 py-1.5 rounded-lg bg-[#121522] border border-white/10 hover:border-[#A5D8FF]/40 text-[11px] font-medium text-[#E5E5E4]"
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
              {voiceStatusMsg && (
                <div className="w-full text-[11px] text-[#A5D8FF] pt-1">{voiceStatusMsg}</div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              {[
                'Cardiopulmonary & Chest Triage',
                'Radiation SPE Exposure',
                'Cardiovascular / Gravity Adaptation',
                'Habitat CO2 & Respiratory',
                'Acute Fatigue & Isolation',
              ].map((hz) => (
                <button
                  key={hz}
                  type="button"
                  onClick={() => triggerEmergencyProtocol(hz)}
                  className={`px-3.5 py-2 rounded-full text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A5D8FF] ${
                    emergencyHazard === hz
                      ? highContrastEva
                        ? 'bg-amber-300 text-black font-bold'
                        : 'bg-[#EEF0F6] text-[#040404] font-semibold'
                      : 'bg-[#0B0D1A] text-[#E5E5E4] border border-white/15 hover:border-[#A5D8FF]/40'
                  }`}
                >
                  {hz}
                </button>
              ))}
            </div>

            {emergencyError && (
              <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 p-3.5 text-xs text-amber-200">
                Backend sync warning ({emergencyError}) — showing locally cached deterministic emergency checklist below.
              </div>
            )}

            {emergencyLoading && !emergencyProtocol ? (
              <div className="rounded-xl bg-[#0B0D1A] p-4 text-sm text-[#E5E5E4]">
                Loading deterministic onboard triage checklist...
              </div>
            ) : emergencyProtocol ? (
              <div className="space-y-4">
                <div
                  className={`rounded-xl p-4 space-y-1.5 border ${
                    highContrastEva
                      ? 'bg-[#0A0A0A] border-white/35'
                      : 'bg-[#0B0D1A] border-white/[0.08]'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-[#A5D8FF]">
                      {emergencyProtocol.protocol_id} · {emergencyProtocol.protocol_title}
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-[#181C2E] text-[#E5E5E4]">
                      {emergencyProtocol.execution_mode}
                    </span>
                  </div>
                  <div className="text-xs text-[#E5E5E4]/85">
                    Link Status: {emergencyProtocol.earth_comm_status} (Round-trip delay{' '}
                    {emergencyProtocol.round_trip_delay_minutes} min)
                  </div>
                  <div className={`pt-1 font-semibold ${highContrastEva ? 'text-sm text-white' : 'text-xs text-[#FAF9FA]'}`}>
                    Vitals: {emergencyProtocol.vital_signs_summary}
                  </div>
                  {emergencyProtocol.reported_symptoms && emergencyProtocol.reported_symptoms.length > 0 && (
                    <div className="text-xs text-red-300 font-semibold pt-0.5">
                      Active Symptoms: {emergencyProtocol.reported_symptoms.join(', ')}
                    </div>
                  )}
                </div>

                <div className="space-y-2.5">
                  {emergencyProtocol.immediate_steps.map((step, idx) => {
                    const checked = Boolean(completedSteps[idx]);
                    const isActive = idx === activeStepIdx;
                    return (
                      <label
                        key={`${emergencyProtocol.protocol_id}-${idx}`}
                        htmlFor={`emergency-step-${idx}`}
                        onClick={() => setActiveStepIdx(idx)}
                        className={`flex items-start gap-3 rounded-xl px-4 py-3.5 cursor-pointer transition-colors border ${
                          checked
                            ? 'bg-emerald-950/45 border-emerald-400/60 text-emerald-100'
                            : isActive
                              ? highContrastEva
                                ? 'bg-[#111111] border-2 border-amber-300 text-white'
                                : 'bg-[#12182B] border-[#A5D8FF] text-[#FAF9FA]'
                              : highContrastEva
                                ? 'bg-[#050505] border-white/25 text-white'
                                : 'bg-[#0B0D1A] border-white/[0.08] text-[#FAF9FA]'
                        }`}
                      >
                        <input
                          id={`emergency-step-${idx}`}
                          name={`emergency_step_${idx}`}
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setCompletedSteps((prev) => ({
                              ...prev,
                              [idx]: !prev[idx],
                            }))
                          }
                          className="mt-0.5 w-5 h-5 rounded accent-emerald-400 shrink-0 cursor-pointer"
                        />
                        <span
                          className={`${
                            highContrastEva ? 'text-base font-semibold leading-snug' : 'text-sm leading-snug'
                          } ${checked ? 'line-through opacity-80' : ''}`}
                        >
                          {step}
                        </span>
                      </label>
                    );
                  })}
                </div>

                {emergencyProtocol.protocol_gap_notice && (
                  <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-xs text-amber-200 leading-relaxed">
                    <strong>Diagnostic Capability Boundary:</strong> {emergencyProtocol.protocol_gap_notice}
                  </div>
                )}

                <p className="text-xs text-[#E5E5E4]/75">
                  Reference: {emergencyProtocol.supporting_citation} · {emergencyProtocol.safety_disclaimer}
                </p>
              </div>
            ) : (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
                Unable to render checklist payload. Click a category pill above to load deterministic offline emergency steps.
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setEmergencyOpen(false);
                  setActiveTab('comm');
                }}
                className="mc-btn-secondary px-4 py-2.5 text-xs inline-flex items-center gap-1.5"
              >
                <Radio className="w-3.5 h-3.5 text-[#A5D8FF]" />
                <span>View Sync Queue</span>
              </button>
              <button
                type="button"
                onClick={() => setEmergencyOpen(false)}
                className="mc-btn-primary px-6 py-2.5 text-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      );
    })()}
  </div>
);
}
