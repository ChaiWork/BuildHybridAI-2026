import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Cloud,
  Cpu,
  KeyRound,
  Lock,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { FullSystemState, LocalAIStatus } from '../types';
import {
  clearRuntimeFirebaseConfig,
  ensureHybridSuiteInitialized,
  HYBRID_CLOUD_MODELS,
  HybridModeChoice,
  HybridSuiteSnapshot,
  parseFirebaseConfigSnippet,
  saveRuntimeFirebaseConfig,
  setSelectedCloudModel,
  setSelectedHybridMode,
  signInCrewWithGoogle,
  signOutCrew,
  subscribeHybridSuite,
  warmupOnDeviceGeminiNano,
} from '../lib/firebaseHybridAI';

interface AIProviderSwitcherProps {
  aiStatus?: LocalAIStatus;
  variant?: 'toolbar' | 'sidebar' | 'panel';
  collapsed?: boolean;
  onStateUpdated?: (next: FullSystemState) => void;
  onNotice?: (msg: string | null) => void;
}

const MODE_META: {
  id: HybridModeChoice;
  shortLabel: string;
  fullLabel: string;
  desc: string;
}[] = [
  {
    id: 'prefer_on_device',
    shortLabel: 'Prefer On-Device',
    fullLabel: 'PREFER_ON_DEVICE (Gemini Nano 4 → Cloud Fallback)',
    desc: 'Runs free & private on Chrome Gemini Nano 4 first; seamlessly falls back to Cloud Gemini when unavailable.',
  },
  {
    id: 'only_on_device',
    shortLabel: 'Only On-Device',
    fullLabel: 'ONLY_ON_DEVICE (Strict Local · Zero Egress)',
    desc: 'Forces local Gemini Nano 4 execution only — guaranteed zero cloud transmission for blackout & private journals.',
  },
  {
    id: 'prefer_in_cloud',
    shortLabel: 'Prefer Cloud',
    fullLabel: 'PREFER_IN_CLOUD (Cloud Gemini → Local Fallback)',
    desc: 'Prioritizes Cloud Gemini for deep synthesis; falls back to on-device Gemini Nano 4 if link drops.',
  },
  {
    id: 'only_in_cloud',
    shortLabel: 'Only Cloud',
    fullLabel: 'ONLY_IN_CLOUD (Cloud Gemini Direct)',
    desc: 'Routes directly to Cloud Gemini via Firebase AI Logic + App Check.',
  },
];

export const AIProviderSwitcher: React.FC<AIProviderSwitcherProps> = ({
  variant = 'toolbar',
  collapsed = false,
  onNotice,
}) => {
  const [snap, setSnap] = useState<HybridSuiteSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [rawSnippet, setRawSnippet] = useState('');
  const [recaptchaKey, setRecaptchaKey] = useState('');
  const [debugTokenEnabled, setDebugTokenEnabled] = useState(true);

  useEffect(() => {
    const unsub = subscribeHybridSuite(setSnap);
    void ensureHybridSuiteInitialized();
    return unsub;
  }, []);

  const emit = (msg: string | null) => {
    onNotice?.(msg);
  };

  const activeMode: HybridModeChoice = snap?.selectedMode || 'prefer_on_device';
  const isOnDevicePrimary =
    activeMode === 'prefer_on_device' || activeMode === 'only_on_device';

  const nanoBadge = (() => {
    const st = snap?.chromeNanoStatus || 'checking';
    if (st === 'available') return 'Nano 4 Ready';
    if (st === 'downloading') {
      return `Nano 4 Downloading ${snap?.nanoDownloadProgress ?? 0}%`;
    }
    if (st === 'downloadable') return 'Nano 4 Downloadable';
    if (st === 'checking') return 'Checking Nano 4...';
    return snap?.firebaseConfigured ? 'Nano N/A → Cloud Fallback' : 'Nano N/A · Offline Safety';
  })();

  const handleModeSelect = (nextMode: HybridModeChoice) => {
    setSelectedHybridMode(nextMode);
    const meta = MODE_META.find((m) => m.id === nextMode);
    emit(`Firebase AI Logic routing set to ${meta?.fullLabel || nextMode}.`);
  };

  const handleWarmupNano = async () => {
    setBusy(true);
    emit(null);
    try {
      const res = await warmupOnDeviceGeminiNano();
      emit(res.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveFirebaseConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    emit(null);
    try {
      const parsed = parseFirebaseConfigSnippet(rawSnippet, {
        recaptchaSiteKey: recaptchaKey,
        appCheckDebug: debugTokenEnabled,
      });
      await saveRuntimeFirebaseConfig(parsed);
      setRawSnippet('');
      setShowConfigModal(false);
      emit(
        `Connected Firebase project "${parsed.projectId}" with App Check, AI Logic Hybrid SDK, Firestore Offline Cache & Remote Config.`,
      );
    } catch (err) {
      emit(err instanceof Error ? err.message : 'Invalid Firebase config snippet.');
    } finally {
      setBusy(false);
    }
  };

  if (variant === 'sidebar') {
    if (collapsed) {
      const next: HybridModeChoice = isOnDevicePrimary ? 'prefer_in_cloud' : 'prefer_on_device';
      return (
        <button
          type="button"
          onClick={() => handleModeSelect(next)}
          title={`Firebase Hybrid AI: ${activeMode} (${nanoBadge}) — click to toggle`}
          aria-label="Toggle Firebase Hybrid AI inference mode"
          className="w-full flex items-center justify-center p-2 rounded-xl bg-[#0B0D1A] border border-white/[0.1] text-[#A5D8FF] hover:border-[#A5D8FF]/45 transition-colors"
        >
          {isOnDevicePrimary ? <Cpu className="w-4 h-4" /> : <Cloud className="w-4 h-4" />}
        </button>
      );
    }

    return (
      <div className="space-y-1.5">
        <div
          role="group"
          aria-label="Firebase AI Logic Hybrid Inference Mode"
          className="grid grid-cols-2 rounded-full bg-[#0B0D1A] border border-white/[0.1] p-0.5"
        >
          <button
            type="button"
            aria-pressed={isOnDevicePrimary}
            onClick={() => handleModeSelect('prefer_on_device')}
            className={`px-2 py-1 rounded-full text-[11px] font-medium inline-flex items-center justify-center gap-1 transition-colors ${
              isOnDevicePrimary
                ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                : 'text-[#E5E5E4]/75 hover:text-[#FAF9FA]'
            }`}
          >
            <Cpu className="w-3 h-3 shrink-0" />
            <span>On-Device</span>
          </button>
          <button
            type="button"
            aria-pressed={!isOnDevicePrimary}
            onClick={() => handleModeSelect('prefer_in_cloud')}
            className={`px-2 py-1 rounded-full text-[11px] font-medium inline-flex items-center justify-center gap-1 transition-colors ${
              !isOnDevicePrimary
                ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                : 'text-[#E5E5E4]/75 hover:text-[#FAF9FA]'
            }`}
          >
            <Cloud className="w-3 h-3 shrink-0" />
            <span>Cloud AI</span>
          </button>
        </div>
        <div
          className="text-[11px] text-[#A5D8FF]/90 truncate text-center flex items-center justify-center gap-1"
          title={`Firebase AI Logic · ${activeMode} · ${nanoBadge}`}
        >
          <Sparkles className="w-3 h-3 shrink-0" />
          <span className="truncate">{nanoBadge}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {/* 4-Mode Firebase AI Logic InferenceMode Selector */}
        <select
          id={`firebase-hybrid-mode-${variant}`}
          name="firebase_hybrid_mode"
          value={activeMode}
          onChange={(e) => handleModeSelect(e.target.value as HybridModeChoice)}
          aria-label="Select Firebase AI Logic InferenceMode"
          className="rounded-full bg-[#0B0D1A] border border-[#A5D8FF]/40 px-3.5 py-1.5 text-xs font-semibold text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none"
        >
          {MODE_META.map((m) => (
            <option key={m.id} value={m.id}>
              {m.fullLabel}
            </option>
          ))}
        </select>

        {/* Cloud Fallback Model Selector */}
        {activeMode !== 'only_on_device' && (
          <select
            id={`firebase-cloud-model-${variant}`}
            name="firebase_cloud_model"
            value={snap?.cloudModel || 'gemini-3.5-flash-lite'}
            onChange={(e) => {
              setSelectedCloudModel(e.target.value);
              emit(`Firebase Cloud fallback model set to ${e.target.value}.`);
            }}
            aria-label="Select Firebase Cloud Gemini fallback model"
            className="rounded-full bg-[#0B0D1A] border border-white/15 px-3 py-1.5 text-xs text-[#E5E5E4] focus:border-[#A5D8FF] focus:outline-none max-w-[235px]"
          >
            {HYBRID_CLOUD_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        )}

        {/* Warm Up Chrome Gemini Nano 4 Button */}
        <button
          type="button"
          disabled={busy}
          onClick={handleWarmupNano}
          className="px-3 py-1.5 rounded-full bg-[#0B0D1A] border border-white/15 text-xs text-[#E5E5E4] hover:border-[#A5D8FF]/50 inline-flex items-center gap-1.5 transition-colors"
          title="Initialize or download Chrome built-in Gemini Nano 4 via Firebase AI Logic"
        >
          <RefreshCw className={`w-3 h-3 text-[#A5D8FF] ${busy ? 'animate-spin' : ''}`} />
          <span>{nanoBadge}</span>
        </button>

        {/* App Check + Project Config Trigger */}
        <button
          type="button"
          onClick={() => setShowConfigModal((v) => !v)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium inline-flex items-center gap-1.5 border transition-colors ${
            snap?.firebaseConfigured
              ? 'bg-emerald-500/15 border-emerald-500/35 text-emerald-200'
              : 'bg-[#0B0D1A] border-amber-400/35 text-amber-200 hover:border-amber-300'
          }`}
          title="Configure Firebase Project, App Check & Crew Auth"
        >
          {snap?.firebaseConfigured ? (
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
          ) : (
            <KeyRound className="w-3.5 h-3.5 text-amber-300" />
          )}
          <span>
            {snap?.firebaseConfigured
              ? `Firebase · ${snap.projectId}`
              : 'Firebase Config (Local Nano Sandbox)'}
          </span>
        </button>

        {/* Last Runtime Execution Source Pill */}
        {snap?.lastExecution && (
          <div
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#121522] border border-[#A5D8FF]/30 text-[11px] text-[#A5D8FF]"
            title={`Privacy: ${snap.lastExecution.privacyGuarantee}`}
          >
            {snap.lastExecution.sourceActual === 'on_device' ? (
              <Lock className="w-3 h-3 text-emerald-300" />
            ) : (
              <Cloud className="w-3 h-3 text-[#A5D8FF]" />
            )}
            <span>
              Last: {snap.lastExecution.modelLabel} · {snap.lastExecution.latencyMs} ms
            </span>
          </div>
        )}
      </div>

      {/* Runtime Firebase Project, App Check & Auth Configuration Panel */}
      {showConfigModal && (
        <div className="rounded-2xl bg-[#0B0D1A] border border-[#A5D8FF]/35 p-4 space-y-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-semibold text-[#FAF9FA] flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-[#A5D8FF]" />
                <span>Firebase AI Logic · App Check · Auth · Firestore Setup</span>
              </div>
              <p className="text-[#E5E5E4]/75 mt-0.5">
                Set <code className="text-[#A5D8FF]">VITE_FIREBASE_*</code> in{' '}
                <code className="text-[#A5D8FF]">frontend/.env.local</code> or paste your public Web{' '}
                <code className="text-[#A5D8FF]">firebaseConfig</code> object below (stored in browser{' '}
                <code>localStorage</code> only — never committed to git).
              </p>
            </div>
            {snap?.firebaseConfigured && (
              <div className="flex items-center gap-2">
                {snap.authIsAnonymous ? (
                  <button
                    type="button"
                    onClick={() =>
                      signInCrewWithGoogle().catch((e) =>
                        emit(e instanceof Error ? e.message : 'Google Sign-In failed.'),
                      )
                    }
                    className="mc-btn-secondary px-3 py-1.5 text-xs"
                  >
                    Sign In Crew (Google)
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void signOutCrew()}
                    className="mc-btn-secondary px-3 py-1.5 text-xs"
                  >
                    Sign Out ({snap.authDisplayName})
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    clearRuntimeFirebaseConfig();
                    emit('Cleared browser Firebase config override.');
                  }}
                  className="px-3 py-1.5 rounded-full border border-white/15 text-[#E5E5E4]/80 hover:text-[#FAF9FA]"
                >
                  Reset Override
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-xl bg-[#121522] p-2.5 border border-white/[0.06]">
              <span className="text-[#8E95A8] block">App Check Attestation</span>
              <strong className="text-[#FAF9FA]">
                {snap?.appCheckMode === 'local_sandbox'
                  ? 'Sandbox (Configure Project for Cloud)'
                  : `${snap?.appCheckMode} ${snap?.appCheckVerified ? '· Token Verified' : ''}`}
              </strong>
            </div>
            <div className="rounded-xl bg-[#121522] p-2.5 border border-white/[0.06]">
              <span className="text-[#8E95A8] block">Firebase Crew Auth</span>
              <strong className="text-[#FAF9FA]">
                {snap?.authUserUid
                  ? `${snap.authIsAnonymous ? 'Anonymous Crew' : snap.authDisplayName} (${snap.authUserUid.slice(0, 8)}…)`
                  : 'Offline Local Crew'}
              </strong>
            </div>
            <div className="rounded-xl bg-[#121522] p-2.5 border border-white/[0.06]">
              <span className="text-[#8E95A8] block">Remote Config Policy</span>
              <strong className="text-[#FAF9FA]">
                CO₂ {snap?.remoteConfig.co2WarnMmhg} mmHg · Rad {snap?.remoteConfig.radWarnMsv} mSv (
                {snap?.remoteConfig.source})
              </strong>
            </div>
          </div>

          <form onSubmit={handleSaveFirebaseConfig} className="space-y-2.5">
            <textarea
              rows={3}
              value={rawSnippet}
              onChange={(e) => setRawSnippet(e.target.value)}
              placeholder='Paste const firebaseConfig = { apiKey: "...", authDomain: "...", projectId: "...", appId: "..." };'
              aria-label="Firebase Web configuration snippet"
              className="w-full rounded-xl bg-[#121522] border border-white/15 p-2.5 font-mono text-xs text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none"
            />
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                value={recaptchaKey}
                onChange={(e) => setRecaptchaKey(e.target.value)}
                placeholder="Optional: reCAPTCHA v3 / Enterprise site key"
                className="flex-1 min-w-[220px] rounded-full bg-[#121522] border border-white/15 px-3.5 py-1.5 text-xs text-[#FAF9FA]"
              />
              <label className="inline-flex items-center gap-1.5 text-[#E5E5E4] cursor-pointer">
                <input
                  type="checkbox"
                  checked={debugTokenEnabled}
                  onChange={(e) => setDebugTokenEnabled(e.target.checked)}
                />
                <span>Enable App Check Debug Token (Local / Judge Testing)</span>
              </label>
              <button
                type="submit"
                disabled={busy || !rawSnippet.trim()}
                className="mc-btn-primary px-4 py-1.5 text-xs inline-flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Connect Firebase</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
