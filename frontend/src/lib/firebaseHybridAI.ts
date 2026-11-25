/**
 * TARS Care — Unified Firebase AI Logic Hybrid Inference, App Check, Auth,
 * Offline-First Firestore Store-and-Forward, and Remote Config Suite.
 *
 * Dynamically routes spaceflight health & crew companion tasks across:
 * - InferenceMode.ONLY_ON_DEVICE (Chrome Gemini Nano 4): PIN-protected crew journal
 *   & private psychological companion reflections (strict zero-egress privacy) and
 *   Mars Solar Conjunction Blackout operations.
 * - InferenceMode.PREFER_ON_DEVICE (Gemini Nano 4 -> Cloud Gemini fallback):
 *   Citation-grounded NASA/CSA RAG Q&A and structured JSON symptom/vitals parsing.
 * - InferenceMode.PREFER_IN_CLOUD / ONLY_IN_CLOUD: Multi-Sol Earth Flight Surgeon
 *   consultation synthesis when Deep Space Network link is active.
 */

import { FirebaseApp, FirebaseOptions, getApps, initializeApp } from 'firebase/app';
import {
  AppCheck,
  CustomProvider,
  getToken as getAppCheckToken,
  initializeAppCheck,
  ReCaptchaEnterpriseProvider,
  ReCaptchaV3Provider,
} from 'firebase/app-check';
import {
  AI,
  GenerativeModel,
  getAI,
  getGenerativeModel,
  GoogleAIBackend,
  InferenceMode,
  InferenceSource,
  Schema,
} from 'firebase/ai';
import {
  Auth,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInAnonymously,
  signInWithPopup,
  signOut,
  User,
} from 'firebase/auth';
import {
  addDoc,
  collection,
  disableNetwork,
  enableNetwork,
  Firestore,
  initializeFirestore,
  limit,
  memoryLocalCache,
  onSnapshot,
  orderBy,
  persistentLocalCache,
  persistentMultipleTabManager,
  query,
  Unsubscribe,
} from 'firebase/firestore';
import {
  fetchAndActivate,
  getRemoteConfig,
  getValue,
  RemoteConfig,
} from 'firebase/remote-config';

export { InferenceMode, InferenceSource };

export type HybridModeChoice =
  | 'prefer_on_device'
  | 'only_on_device'
  | 'prefer_in_cloud'
  | 'only_in_cloud';

export type ChromeNanoAvailability =
  | 'available'
  | 'downloadable'
  | 'downloading'
  | 'unavailable'
  | 'checking';

export interface FirebaseRuntimeConfigInput {
  apiKey: string;
  authDomain?: string;
  projectId: string;
  storageBucket?: string;
  messagingSenderId?: string;
  appId: string;
  recaptchaSiteKey?: string;
  recaptchaEnterprise?: boolean;
  appCheckDebug?: boolean | string;
  cloudModel?: string;
}

export interface HybridExecutionTelemetry {
  modeRequested: HybridModeChoice;
  sourceActual: 'on_device' | 'in_cloud' | 'deterministic_safety_fallback';
  modelLabel: string;
  latencyMs: number;
  timestampIso: string;
  privacyGuarantee: 'STRICT_ZERO_EGRESS_ON_DEVICE' | 'HYBRID_APP_CHECK_PROTECTED';
  promptTokens?: number;
  candidateTokens?: number;
}

export interface MissionRemoteConfigValues {
  cloudFallbackModel: string;
  defaultInferenceMode: HybridModeChoice;
  radWarnMsv: number;
  co2WarnMmhg: number;
  enforceBlackoutOnDevice: boolean;
  source: 'default' | 'remote' | 'static';
  lastFetchedIso: string | null;
}

export interface FirestoreSyncItem {
  id: string;
  crewId: string;
  crewName: string;
  sol: number;
  category: 'EVA_FIELD_LOG' | 'FLIGHT_SURGEON_CONSULT';
  urgency: string;
  summary: string;
  sourcePlatform: 'WEB_CHROME' | 'ANDROID_COMPANION';
  inferenceSource: string;
  createdAtIso: string;
  pendingCloudSync: boolean;
}

export interface HybridSuiteSnapshot {
  firebaseConfigured: boolean;
  usingSandboxLocalOnly: boolean;
  projectId: string | null;
  appCheckActive: boolean;
  appCheckMode: 'recaptcha_enterprise' | 'recaptcha_v3' | 'debug_token' | 'local_sandbox' | 'uninitialized';
  appCheckVerified: boolean;
  authUserUid: string | null;
  authIsAnonymous: boolean;
  authDisplayName: string | null;
  chromeNanoStatus: ChromeNanoAvailability;
  nanoDownloadProgress: number | null;
  selectedMode: HybridModeChoice;
  cloudModel: string;
  firestoreNetworkEnabled: boolean;
  pendingSyncWrites: number;
  recentSyncItems: FirestoreSyncItem[];
  remoteConfig: MissionRemoteConfigValues;
  lastExecution: HybridExecutionTelemetry | null;
  lastError: string | null;
}

const STORAGE_CONFIG_KEY = 'tarscare_firebase_runtime_cfg_v1';
const STORAGE_MODE_KEY = 'tarscare_hybrid_inference_mode_v1';
const STORAGE_CLOUD_MODEL_KEY = 'tarscare_hybrid_cloud_model_v1';

export const HYBRID_CLOUD_MODELS: { id: string; label: string }[] = [
  { id: 'gemini-3.5-flash-lite', label: 'gemini-3.5-flash-lite (Default Hybrid Cloud)' },
  { id: 'gemini-2.5-flash', label: 'gemini-2.5-flash (Balanced Multimodal)' },
  { id: 'gemini-2.5-flash-lite', label: 'gemini-2.5-flash-lite (Low-Latency Cloud)' },
  { id: 'gemini-2.5-pro', label: 'gemini-2.5-pro (Deep Flight Surgeon Reasoning)' },
];

const PRESCRIPTION_SAFETY_RE =
  /\b(?:take|administer|prescribe|start|dose\s+of)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablet|tablets|capsule|capsules|pill|pills)\b|\b(?:amoxicillin|azithromycin|ciprofloxacin|doxycycline|ibuprofen|acetaminophen|paracetamol|prednisone|alprazolam|sertraline|modafinil|zolpidem|metoprolol|atenolol|propranolol|amiodarone|aspirin|nitroglycerin|tramadol|codeine|diazepam|lorazepam|melatonin)\s+\d+(?:\.\d+)?\s*(?:mg|mcg)\b/i;

export function enforceMedicalSafetyText(rawText: string): { text: string; redacted: boolean } {
  if (!PRESCRIPTION_SAFETY_RE.test(rawText)) {
    return { text: rawText.trim(), redacted: false };
  }
  const cleaned = rawText.replace(
    PRESCRIPTION_SAFETY_RE,
    '[MEDICATION DOSING REDACTED — CONSULT ONBOARD CMO / FLIGHT SURGEON]',
  );
  return {
    text: `${cleaned.trim()}\n\nSafety Gate Notice: Specific medication dosing was automatically redacted per TARS Care autonomous non-prescribing safety rules.`,
    redacted: true,
  };
}

let _app: FirebaseApp | null = null;
let _appCheck: AppCheck | null = null;
let _ai: AI | null = null;
let _auth: Auth | null = null;
let _db: Firestore | null = null;
let _rc: RemoteConfig | null = null;
let _evaUnsub: Unsubscribe | null = null;
let _consultUnsub: Unsubscribe | null = null;
let _evaItems: FirestoreSyncItem[] = [];
let _consultItems: FirestoreSyncItem[] = [];

const _listeners = new Set<(snap: HybridSuiteSnapshot) => void>();

const DEFAULT_REMOTE_CONFIG: MissionRemoteConfigValues = {
  cloudFallbackModel:
    (import.meta.env.VITE_FIREBASE_CLOUD_MODEL as string | undefined)?.trim() ||
    'gemini-3.5-flash-lite',
  defaultInferenceMode: 'prefer_on_device',
  radWarnMsv: 50,
  co2WarnMmhg: 3.0,
  enforceBlackoutOnDevice: true,
  source: 'default',
  lastFetchedIso: null,
};

let _state: HybridSuiteSnapshot = {
  firebaseConfigured: false,
  usingSandboxLocalOnly: true,
  projectId: null,
  appCheckActive: false,
  appCheckMode: 'uninitialized',
  appCheckVerified: false,
  authUserUid: null,
  authIsAnonymous: true,
  authDisplayName: null,
  chromeNanoStatus: 'checking',
  nanoDownloadProgress: null,
  selectedMode: loadSavedMode(),
  cloudModel: loadSavedCloudModel(),
  firestoreNetworkEnabled: true,
  pendingSyncWrites: 0,
  recentSyncItems: [],
  remoteConfig: { ...DEFAULT_REMOTE_CONFIG },
  lastExecution: null,
  lastError: null,
};

function loadSavedMode(): HybridModeChoice {
  try {
    const raw = localStorage.getItem(STORAGE_MODE_KEY);
    if (
      raw === 'prefer_on_device' ||
      raw === 'only_on_device' ||
      raw === 'prefer_in_cloud' ||
      raw === 'only_in_cloud'
    ) {
      return raw;
    }
  } catch {
    // ignore storage errors
  }
  return 'prefer_on_device';
}

function loadSavedCloudModel(): string {
  try {
    const saved = localStorage.getItem(STORAGE_CLOUD_MODEL_KEY);
    if (saved && saved.trim()) return saved.trim();
  } catch {
    // ignore
  }
  return DEFAULT_REMOTE_CONFIG.cloudFallbackModel;
}

function notifyListeners(): void {
  const snapshot: HybridSuiteSnapshot = {
    ..._state,
    recentSyncItems: [..._state.recentSyncItems],
    remoteConfig: { ..._state.remoteConfig },
  };
  _listeners.forEach((fn) => {
    try {
      fn(snapshot);
    } catch {
      // ignore listener errors
    }
  });
}

export function subscribeHybridSuite(listener: (snap: HybridSuiteSnapshot) => void): () => void {
  _listeners.add(listener);
  listener({
    ..._state,
    recentSyncItems: [..._state.recentSyncItems],
    remoteConfig: { ..._state.remoteConfig },
  });
  return () => {
    _listeners.delete(listener);
  };
}

export function getHybridSuiteSnapshot(): HybridSuiteSnapshot {
  return {
    ..._state,
    recentSyncItems: [..._state.recentSyncItems],
    remoteConfig: { ..._state.remoteConfig },
  };
}

export function resolveConfiguredFirebaseInput(): FirebaseRuntimeConfigInput | null {
  try {
    const rawLocal = localStorage.getItem(STORAGE_CONFIG_KEY);
    if (rawLocal) {
      const parsed = JSON.parse(rawLocal) as Partial<FirebaseRuntimeConfigInput>;
      if (parsed.apiKey && parsed.projectId && parsed.appId) {
        return {
          apiKey: parsed.apiKey.trim(),
          authDomain: parsed.authDomain?.trim(),
          projectId: parsed.projectId.trim(),
          storageBucket: parsed.storageBucket?.trim(),
          messagingSenderId: parsed.messagingSenderId?.trim(),
          appId: parsed.appId.trim(),
          recaptchaSiteKey: parsed.recaptchaSiteKey?.trim(),
          recaptchaEnterprise: Boolean(parsed.recaptchaEnterprise),
          appCheckDebug: parsed.appCheckDebug ?? true,
          cloudModel: parsed.cloudModel?.trim(),
        };
      }
    }
  } catch {
    // ignore malformed local config
  }

  const envKey = (import.meta.env.VITE_FIREBASE_API_KEY as string | undefined)?.trim();
  const envProject = (import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined)?.trim();
  const envAppId = (import.meta.env.VITE_FIREBASE_APP_ID as string | undefined)?.trim();
  if (envKey && envProject && envAppId) {
    const rawDebug = (import.meta.env.VITE_FIREBASE_APPCHECK_DEBUG as string | undefined)?.trim();
    const debugVal: boolean | string =
      !rawDebug || rawDebug === 'false'
        ? false
        : rawDebug === 'true'
          ? true
          : rawDebug;
    return {
      apiKey: envKey,
      authDomain: (import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined)?.trim(),
      projectId: envProject,
      storageBucket: (import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined)?.trim(),
      messagingSenderId: (
        import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined
      )?.trim(),
      appId: envAppId,
      recaptchaSiteKey: (
        import.meta.env.VITE_FIREBASE_RECAPTCHA_SITE_KEY as string | undefined
      )?.trim(),
      recaptchaEnterprise:
        (import.meta.env.VITE_FIREBASE_RECAPTCHA_ENTERPRISE as string | undefined)?.trim() ===
        'true',
      appCheckDebug: debugVal,
      cloudModel: (import.meta.env.VITE_FIREBASE_CLOUD_MODEL as string | undefined)?.trim(),
    };
  }
  return null;
}

/**
 * Parses either a JSON object or a JS snippet pasted from the Firebase Console
 * (e.g. `const firebaseConfig = { apiKey: "...", projectId: "...", appId: "..." };`).
 */
export function parseFirebaseConfigSnippet(
  raw: string,
  extra?: { recaptchaSiteKey?: string; appCheckDebug?: boolean | string },
): FirebaseRuntimeConfigInput {
  const trimmed = raw.trim();
  const braceStart = trimmed.indexOf('{');
  const braceEnd = trimmed.lastIndexOf('}');
  const body =
    braceStart >= 0 && braceEnd > braceStart ? trimmed.slice(braceStart, braceEnd + 1) : trimmed;

  let extracted: Record<string, string> = {};
  try {
    extracted = JSON.parse(body);
  } catch {
    const kvRe = /([a-zA-Z0-9_]+)\s*:\s*['"]([^'"]+)['"]/g;
    let match: RegExpExecArray | null;
    while ((match = kvRe.exec(body)) !== null) {
      extracted[match[1]] = match[2];
    }
  }

  if (!extracted.apiKey || !extracted.projectId || !extracted.appId) {
    throw new Error('Firebase config must include apiKey, projectId, and appId.');
  }

  return {
    apiKey: extracted.apiKey.trim(),
    authDomain: extracted.authDomain?.trim() || `${extracted.projectId.trim()}.firebaseapp.com`,
    projectId: extracted.projectId.trim(),
    storageBucket: extracted.storageBucket?.trim(),
    messagingSenderId: extracted.messagingSenderId?.trim(),
    appId: extracted.appId.trim(),
    recaptchaSiteKey: extra?.recaptchaSiteKey?.trim(),
    appCheckDebug: extra?.appCheckDebug ?? true,
  };
}

export async function saveRuntimeFirebaseConfig(cfg: FirebaseRuntimeConfigInput): Promise<void> {
  localStorage.setItem(STORAGE_CONFIG_KEY, JSON.stringify(cfg));
  resetFirebaseInstances();
  await ensureHybridSuiteInitialized();
}

export function clearRuntimeFirebaseConfig(): void {
  localStorage.removeItem(STORAGE_CONFIG_KEY);
  resetFirebaseInstances();
  void ensureHybridSuiteInitialized();
}

function resetFirebaseInstances(): void {
  _evaUnsub?.();
  _consultUnsub?.();
  _evaUnsub = null;
  _consultUnsub = null;
  _evaItems = [];
  _consultItems = [];
  _app = null;
  _appCheck = null;
  _ai = null;
  _auth = null;
  _db = null;
  _rc = null;
}

/**
 * Probes Chrome's built-in Prompt API (`LanguageModel` / `window.ai.languageModel`)
 * powering Gemini Nano 4 on-device inference inside Firebase AI Logic.
 */
export async function probeChromeGeminiNano(): Promise<ChromeNanoAvailability> {
  if (typeof window === 'undefined') {
    _state.chromeNanoStatus = 'unavailable';
    notifyListeners();
    return 'unavailable';
  }
  try {
    const g = window as unknown as {
      LanguageModel?: { availability?: () => Promise<string> };
      ai?: { languageModel?: { capabilities?: () => Promise<{ available?: string }> } };
    };
    if (g.LanguageModel && typeof g.LanguageModel.availability === 'function') {
      const avail = (await g.LanguageModel.availability()).toLowerCase();
      if (avail === 'available' || avail === 'readily') {
        _state.chromeNanoStatus = 'available';
      } else if (avail.includes('download') && avail.includes('ing')) {
        _state.chromeNanoStatus = 'downloading';
      } else if (avail.includes('download') || avail === 'after-download') {
        _state.chromeNanoStatus = 'downloadable';
      } else {
        _state.chromeNanoStatus = 'unavailable';
      }
      notifyListeners();
      return _state.chromeNanoStatus;
    }
    if (g.ai?.languageModel?.capabilities) {
      const caps = await g.ai.languageModel.capabilities();
      const av = (caps?.available || '').toLowerCase();
      _state.chromeNanoStatus =
        av === 'readily' || av === 'available'
          ? 'available'
          : av === 'after-download'
            ? 'downloadable'
            : 'unavailable';
      notifyListeners();
      return _state.chromeNanoStatus;
    }
  } catch {
    // ignore probe errors
  }
  _state.chromeNanoStatus = 'unavailable';
  notifyListeners();
  return 'unavailable';
}

function mergeSyncSnapshots(): void {
  const combined = [..._evaItems, ..._consultItems].sort((a, b) =>
    b.createdAtIso.localeCompare(a.createdAtIso),
  );
  _state.recentSyncItems = combined.slice(0, 12);
  _state.pendingSyncWrites = combined.filter((item) => item.pendingCloudSync).length;
  notifyListeners();
}

function attachFirestoreSyncListeners(db: Firestore): void {
  _evaUnsub?.();
  _consultUnsub?.();

  try {
    const evaQuery = query(collection(db, 'eva_logs'), orderBy('createdAtMs', 'desc'), limit(8));
    _evaUnsub = onSnapshot(
      evaQuery,
      { includeMetadataChanges: true },
      (snap) => {
        _evaItems = snap.docs.map((d) => {
          const data = d.data();
          return {
            id: d.id,
            crewId: String(data.crewId || 'ARES-IV-SUCHAI'),
            crewName: String(data.crewName || 'Crew Member'),
            sol: Number(data.sol || 184),
            category: 'EVA_FIELD_LOG',
            urgency: String(data.urgency || 'NORMAL'),
            summary: String(data.summary || ''),
            sourcePlatform:
              data.sourcePlatform === 'ANDROID_COMPANION' ? 'ANDROID_COMPANION' : 'WEB_CHROME',
            inferenceSource: String(data.inferenceSource || 'on_device'),
            createdAtIso: String(data.createdAtIso || new Date().toISOString()),
            pendingCloudSync: d.metadata.hasPendingWrites,
          };
        });
        mergeSyncSnapshots();
      },
      () => {
        // Firestore rules or unconfigured project — fail gracefully
      },
    );

    const consultQuery = query(
      collection(db, 'consult_packets'),
      orderBy('createdAtMs', 'desc'),
      limit(8),
    );
    _consultUnsub = onSnapshot(
      consultQuery,
      { includeMetadataChanges: true },
      (snap) => {
        _consultItems = snap.docs.map((d) => {
          const data = d.data();
          return {
            id: d.id,
            crewId: String(data.crewId || 'ARES-IV-SUCHAI'),
            crewName: String(data.crewName || 'Crew Member'),
            sol: Number(data.sol || 184),
            category: 'FLIGHT_SURGEON_CONSULT',
            urgency: String(data.urgency || 'WARNING'),
            summary: String(data.summary || ''),
            sourcePlatform:
              data.sourcePlatform === 'ANDROID_COMPANION' ? 'ANDROID_COMPANION' : 'WEB_CHROME',
            inferenceSource: String(data.inferenceSource || 'in_cloud'),
            createdAtIso: String(data.createdAtIso || new Date().toISOString()),
            pendingCloudSync: d.metadata.hasPendingWrites,
          };
        });
        mergeSyncSnapshots();
      },
      () => {
        // ignore permission/offline listener notice
      },
    );
  } catch {
    // ignore listener init errors
  }
}

export async function ensureHybridSuiteInitialized(): Promise<HybridSuiteSnapshot> {
  await probeChromeGeminiNano();
  if (_ai && _app) {
    return getHybridSuiteSnapshot();
  }

  const realCfg = resolveConfiguredFirebaseInput();
  const appName = realCfg ? `tarscare-${realCfg.projectId}` : 'tarscare-local-ondevice-sandbox';

  const existing = getApps().find((a) => a.name === appName);
  const options: FirebaseOptions = realCfg
    ? {
        apiKey: realCfg.apiKey,
        authDomain: realCfg.authDomain || `${realCfg.projectId}.firebaseapp.com`,
        projectId: realCfg.projectId,
        storageBucket: realCfg.storageBucket,
        messagingSenderId: realCfg.messagingSenderId,
        appId: realCfg.appId,
      }
    : {
        // Local-only sandbox allowing Chrome Gemini Nano 4 ONLY_ON_DEVICE execution
        // via firebase/ai even before cloud project credentials are supplied.
        apiKey: 'AIzaSyLocalOnDeviceGeminiNanoSandbox000000',
        projectId: 'tarscare-ondevice-sandbox',
        appId: '1:000000000000:web:0000000000000000000000',
      };

  _app = existing || initializeApp(options, appName);
  _state.firebaseConfigured = Boolean(realCfg);
  _state.usingSandboxLocalOnly = !realCfg;
  _state.projectId = realCfg ? realCfg.projectId : null;

  // 1. Firebase App Check (Required by Firebase AI Logic)
  try {
    if (realCfg) {
      if (realCfg.appCheckDebug && typeof window !== 'undefined') {
        (
          self as unknown as { FIREBASE_APPCHECK_DEBUG_TOKEN?: boolean | string }
        ).FIREBASE_APPCHECK_DEBUG_TOKEN = realCfg.appCheckDebug;
      }
      if (realCfg.recaptchaSiteKey) {
        const provider = realCfg.recaptchaEnterprise
          ? new ReCaptchaEnterpriseProvider(realCfg.recaptchaSiteKey)
          : new ReCaptchaV3Provider(realCfg.recaptchaSiteKey);
        _appCheck = initializeAppCheck(_app, {
          provider,
          isTokenAutoRefreshEnabled: true,
        });
        _state.appCheckMode = realCfg.recaptchaEnterprise
          ? 'recaptcha_enterprise'
          : 'recaptcha_v3';
      } else if (realCfg.appCheckDebug) {
        // When debug token is enabled without a production site key (local development / judging),
        // ReCaptchaV3Provider triggers Firebase's built-in DebugProvider exchange automatically.
        _appCheck = initializeAppCheck(_app, {
          provider: new ReCaptchaV3Provider('6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'),
          isTokenAutoRefreshEnabled: true,
        });
        _state.appCheckMode = 'debug_token';
      }
      _state.appCheckActive = Boolean(_appCheck);
      if (_appCheck) {
        getAppCheckToken(_appCheck, false)
          .then((res) => {
            _state.appCheckVerified = Boolean(res?.token);
            notifyListeners();
          })
          .catch(() => {
            _state.appCheckVerified = false;
            notifyListeners();
          });
      }
    } else {
      _appCheck = initializeAppCheck(_app, {
        provider: new CustomProvider({
          getToken: async () => ({
            token: 'local-on-device-sandbox-token',
            expireTimeMillis: Date.now() + 3600_000,
          }),
        }),
        isTokenAutoRefreshEnabled: false,
      });
      _state.appCheckActive = true;
      _state.appCheckMode = 'local_sandbox';
      _state.appCheckVerified = false;
    }
  } catch {
    // AppCheck already initialized for this FirebaseApp instance
    _state.appCheckActive = true;
  }

  // 2. Firebase AI Logic Service (Gemini Developer API Backend)
  _ai = getAI(_app, { backend: new GoogleAIBackend() });

  // 3. Firebase Auth + Cloud Firestore (Persistent Offline Cache) + Remote Config
  if (realCfg) {
    try {
      _auth = getAuth(_app);
      onAuthStateChanged(_auth, (user: User | null) => {
        _state.authUserUid = user?.uid || null;
        _state.authIsAnonymous = user ? user.isAnonymous : true;
        _state.authDisplayName = user?.displayName || (user ? 'Authenticated Crew Session' : null);
        notifyListeners();
      });
      if (!_auth.currentUser && _state.firestoreNetworkEnabled) {
        signInAnonymously(_auth).catch(() => {
          // Anonymous auth may be disabled or offline; continue seamlessly
        });
      }
    } catch {
      // ignore auth setup errors
    }

    try {
      try {
        _db = initializeFirestore(_app, {
          localCache: persistentLocalCache({
            tabManager: persistentMultipleTabManager(),
          }),
        });
      } catch {
        _db = initializeFirestore(_app, {
          localCache: memoryLocalCache(),
        });
      }
      attachFirestoreSyncListeners(_db);
    } catch {
      // Firestore already initialized
    }

    try {
      _rc = getRemoteConfig(_app);
      _rc.settings.minimumFetchIntervalMillis = 60_000;
      _rc.defaultConfig = {
        cloud_fallback_model: DEFAULT_REMOTE_CONFIG.cloudFallbackModel,
        default_inference_mode: DEFAULT_REMOTE_CONFIG.defaultInferenceMode,
        rad_warn_msv: DEFAULT_REMOTE_CONFIG.radWarnMsv,
        co2_warn_mmhg: DEFAULT_REMOTE_CONFIG.co2WarnMmhg,
        enforce_blackout_on_device: DEFAULT_REMOTE_CONFIG.enforceBlackoutOnDevice,
      };
      if (_state.firestoreNetworkEnabled) {
        void refreshMissionRemoteConfig();
      }
    } catch {
      // ignore remote config init error in non-browser tests
    }
  }

  notifyListeners();
  return getHybridSuiteSnapshot();
}

export async function refreshMissionRemoteConfig(): Promise<MissionRemoteConfigValues> {
  if (!_rc || !_state.firebaseConfigured || !_state.firestoreNetworkEnabled) {
    return _state.remoteConfig;
  }
  try {
    await fetchAndActivate(_rc);
    const model = getValue(_rc, 'cloud_fallback_model').asString() || _state.cloudModel;
    const rawMode = getValue(_rc, 'default_inference_mode').asString() as HybridModeChoice;
    const radWarn = getValue(_rc, 'rad_warn_msv').asNumber() || 50;
    const co2Warn = getValue(_rc, 'co2_warn_mmhg').asNumber() || 3.0;
    const blackoutStrict = getValue(_rc, 'enforce_blackout_on_device').asBoolean();

    _state.remoteConfig = {
      cloudFallbackModel: model,
      defaultInferenceMode:
        rawMode === 'prefer_on_device' ||
        rawMode === 'only_on_device' ||
        rawMode === 'prefer_in_cloud' ||
        rawMode === 'only_in_cloud'
          ? rawMode
          : 'prefer_on_device',
      radWarnMsv: radWarn,
      co2WarnMmhg: co2Warn,
      enforceBlackoutOnDevice: blackoutStrict,
      source: 'remote',
      lastFetchedIso: new Date().toISOString(),
    };
    notifyListeners();
  } catch {
    // Keep cached/default Remote Config when offline
  }
  return _state.remoteConfig;
}

export async function signInCrewWithGoogle(): Promise<void> {
  await ensureHybridSuiteInitialized();
  if (!_auth || !_state.firebaseConfigured) {
    throw new Error('Configure Firebase project credentials first to sign in with Google.');
  }
  const provider = new GoogleAuthProvider();
  await signInWithPopup(_auth, provider);
}

export async function signOutCrew(): Promise<void> {
  if (_auth) {
    await signOut(_auth);
    if (_state.firestoreNetworkEnabled) {
      await signInAnonymously(_auth).catch(() => {});
    }
  }
}

export function setSelectedHybridMode(mode: HybridModeChoice): void {
  _state.selectedMode = mode;
  try {
    localStorage.setItem(STORAGE_MODE_KEY, mode);
  } catch {
    // ignore
  }
  notifyListeners();
}

export function setSelectedCloudModel(modelId: string): void {
  _state.cloudModel = modelId;
  try {
    localStorage.setItem(STORAGE_CLOUD_MODEL_KEY, modelId);
  } catch {
    // ignore
  }
  notifyListeners();
}

/**
 * Links TARS Care's Connected / Delayed / Offline (Conjunction Blackout) state
 * directly to Cloud Firestore's offline persistence network toggle and Hybrid AI routing.
 */
export async function syncFirebaseWithCommMode(
  commMode: 'CONNECTED' | 'DELAYED' | 'OFFLINE',
): Promise<void> {
  await ensureHybridSuiteInitialized();
  const shouldEnableNetwork = commMode !== 'OFFLINE';
  _state.firestoreNetworkEnabled = shouldEnableNetwork;
  if (_db && _state.firebaseConfigured) {
    try {
      if (shouldEnableNetwork) {
        await enableNetwork(_db);
        void refreshMissionRemoteConfig();
      } else {
        await disableNetwork(_db);
      }
    } catch {
      // ignore network state transition race
    }
  }
  notifyListeners();
}

function buildHybridGenerativeModel(
  mode: HybridModeChoice,
  systemInstruction: string,
  structuredSchema?: ReturnType<typeof Schema.object>,
): GenerativeModel {
  if (!_ai) {
    throw new Error('Firebase AI Logic instance is not initialized.');
  }
  const sdkMode: InferenceMode =
    mode === 'only_on_device'
      ? InferenceMode.ONLY_ON_DEVICE
      : mode === 'prefer_in_cloud'
        ? InferenceMode.PREFER_IN_CLOUD
        : mode === 'only_in_cloud'
          ? InferenceMode.ONLY_IN_CLOUD
          : InferenceMode.PREFER_ON_DEVICE;

  // When running in local sandbox without cloud Firebase credentials, avoid hitting fake cloud keys:
  const effectiveMode: InferenceMode =
    _state.usingSandboxLocalOnly && sdkMode !== InferenceMode.ONLY_ON_DEVICE
      ? InferenceMode.ONLY_ON_DEVICE
      : sdkMode;

  return getGenerativeModel(_ai, {
    mode: effectiveMode,
    inCloudParams: {
      model: _state.cloudModel || 'gemini-3.5-flash-lite',
      systemInstruction,
      generationConfig: structuredSchema
        ? {
            maxOutputTokens: 900,
            responseMimeType: 'application/json',
            responseSchema: structuredSchema,
          }
        : {
            maxOutputTokens: 900,
          },
    },
    onDeviceParams: {
      createOptions: {
        initialPrompts: [{ role: 'system', content: [{ type: 'text', value: systemInstruction }] }],
      },
      promptOptions: structuredSchema
        ? {
            responseConstraint: structuredSchema,
          }
        : undefined,
    },
  });
}

/**
 * Must be triggered by a user click/gesture per Chrome Prompt API requirements.
 * Downloads or warms up Chrome's built-in Gemini Nano 4 model through Firebase AI Logic.
 */
export async function warmupOnDeviceGeminiNano(
  onProgress?: (pct: number) => void,
): Promise<{ ok: boolean; message: string }> {
  await ensureHybridSuiteInitialized();
  if (!_ai) {
    return { ok: false, message: 'Firebase AI Logic not initialized.' };
  }
  try {
    _state.lastError = null;
    const model = getGenerativeModel(_ai, {
      mode: InferenceMode.ONLY_ON_DEVICE,
    });
    await model.initializeDeviceModel((progress) => {
      const pct = Math.round(progress * 100);
      _state.nanoDownloadProgress = pct;
      _state.chromeNanoStatus = pct < 100 ? 'downloading' : 'available';
      notifyListeners();
      onProgress?.(pct);
    });
    _state.nanoDownloadProgress = 100;
    await probeChromeGeminiNano();
    return {
      ok: true,
      message: 'On-device Gemini Nano 4 initialized and ready in Chrome via Firebase AI Logic.',
    };
  } catch (err) {
    const msg =
      err instanceof Error
        ? err.message
        : 'Chrome Gemini Nano 4 unavailable on this browser/device — PREFER_ON_DEVICE will seamlessly fall back to Cloud Gemini.';
    _state.lastError = msg;
    await probeChromeGeminiNano();
    return {
      ok: false,
      message: msg,
    };
  }
}

function recordExecution(
  modeRequested: HybridModeChoice,
  sourceActual: 'on_device' | 'in_cloud' | 'deterministic_safety_fallback',
  latencyMs: number,
  privacyGuarantee: 'STRICT_ZERO_EGRESS_ON_DEVICE' | 'HYBRID_APP_CHECK_PROTECTED',
  promptTokens?: number,
  candidateTokens?: number,
): HybridExecutionTelemetry {
  const modelLabel =
    sourceActual === 'on_device'
      ? 'Gemini Nano 4 (On-Device)'
      : sourceActual === 'in_cloud'
        ? `${_state.cloudModel} (Firebase Cloud)`
        : 'Deterministic Offline Safety Engine';
  const exec: HybridExecutionTelemetry = {
    modeRequested,
    sourceActual,
    modelLabel,
    latencyMs,
    timestampIso: new Date().toISOString(),
    privacyGuarantee,
    promptTokens,
    candidateTokens,
  };
  _state.lastExecution = exec;
  _state.lastError = null;
  notifyListeners();
  return exec;
}

/**
 * WORKFLOW 1: Citation-Grounded Spaceflight Medical RAG Synthesis
 * Uses InferenceMode.PREFER_ON_DEVICE by default (or ONLY_ON_DEVICE in Blackout).
 */
export async function runHybridMedicalRAG(params: {
  question: string;
  commMode: 'CONNECTED' | 'DELAYED' | 'OFFLINE';
  astronautSummary: string;
  citations: { doc_id: string; agency: string; title: string; excerpt: string }[];
  fallbackAnswer: string;
}): Promise<{
  answer: string;
  engineMode: string;
  modelUsed: string;
  latencyMs: number;
  telemetry: HybridExecutionTelemetry;
}> {
  await ensureHybridSuiteInitialized();
  const isOfflineBlackout =
    params.commMode === 'OFFLINE' && _state.remoteConfig.enforceBlackoutOnDevice;
  const effectiveMode: HybridModeChoice = isOfflineBlackout
    ? 'only_on_device'
    : _state.selectedMode;

  const systemInstruction = [
    'You are TARS Care, an autonomous spaceflight health decision-support assistant grounded strictly in NASA and CSA research.',
    'Rules:',
    '1. Cite relevant source IDs in square brackets such as [NASA-RADLAB-01] or [CSA-TBONE-01].',
    '2. Keep physical absorbed radiation dose (Gy / mGy) strictly separate from biologically weighted dose (Sv / mSv).',
    '3. Never diagnose psychiatric disorders or infections, and NEVER prescribe medication dosages or surgical procedures.',
    '4. Answer concisely in 3-5 clear bullet points tailored to the crew member baseline.',
  ].join('\n');

  const evidenceBlock = params.citations
    .slice(0, 4)
    .map((c) => `[${c.doc_id}] (${c.agency} — ${c.title}): ${c.excerpt}`)
    .join('\n\n');

  const prompt = [
    `Crew & Telemetry Context: ${params.astronautSummary}`,
    `Link State: ${params.commMode}`,
    `Retrieved NASA/CSA Evidence:\n${evidenceBlock || 'No direct document excerpt matched.'}`,
    `Astronaut Question: ${params.question}`,
    'Synthesize calm, citation-backed guidance strictly from the evidence above.',
  ].join('\n\n');

  const t0 = performance.now();
  try {
    const model = buildHybridGenerativeModel(effectiveMode, systemInstruction);
    const result = await model.generateContent(prompt);
    const latencyMs = Math.max(1, Math.round(performance.now() - t0));
    const rawText = result.response.text();
    const { text: safeText } = enforceMedicalSafetyText(rawText);

    const actualSource: 'on_device' | 'in_cloud' =
      result.response.inferenceSource === InferenceSource.ON_DEVICE ? 'on_device' : 'in_cloud';

    const telemetry = recordExecution(
      effectiveMode,
      actualSource,
      latencyMs,
      actualSource === 'on_device'
        ? 'STRICT_ZERO_EGRESS_ON_DEVICE'
        : 'HYBRID_APP_CHECK_PROTECTED',
      result.response.usageMetadata?.promptTokenCount,
      result.response.usageMetadata?.candidatesTokenCount,
    );

    return {
      answer: safeText,
      engineMode:
        actualSource === 'on_device'
          ? 'FIREBASE_AI_LOGIC_ON_DEVICE'
          : 'FIREBASE_AI_LOGIC_CLOUD_FALLBACK',
      modelUsed: telemetry.modelLabel,
      latencyMs,
      telemetry,
    };
  } catch (err) {
    const latencyMs = Math.max(1, Math.round(performance.now() - t0));
    _state.lastError = err instanceof Error ? err.message : String(err);
    const telemetry = recordExecution(
      effectiveMode,
      'deterministic_safety_fallback',
      latencyMs,
      'STRICT_ZERO_EGRESS_ON_DEVICE',
    );
    return {
      answer: params.fallbackAnswer,
      engineMode: 'DETERMINISTIC_OFFLINE_SAFETY_FALLBACK',
      modelUsed: telemetry.modelLabel,
      latencyMs,
      telemetry,
    };
  }
}

/**
 * WORKFLOW 2: Privacy-Locked On-Device Psychological Companion & PIN Journal Reflection
 * Strictly enforces InferenceMode.ONLY_ON_DEVICE so raw crew mental-health reflections
 * NEVER transmit over the network or leave the local browser/device.
 */
export async function runPrivateOnDeviceReflection(params: {
  astronautName: string;
  sol: number;
  exerciseContraindicated: boolean;
  userText: string;
  kind: 'COMPANION_CHAT' | 'JOURNAL_REFLECTION';
}): Promise<{
  ok: boolean;
  reply: string;
  latencyMs: number;
  engineLabel: string;
  errorReason?: string;
}> {
  await ensureHybridSuiteInitialized();
  const systemInstruction = [
    `You are TARS Care Personal Companion supporting astronaut ${params.astronautName} on Sol ${params.sol}.`,
    'CRITICAL PRIVACY & SAFETY RULES:',
    '- You are running strictly ON-DEVICE (InferenceMode.ONLY_ON_DEVICE) for crew mental-health privacy.',
    '- Offer warm, calm, non-diagnostic reflective support in 3-4 concise sentences.',
    '- Never diagnose psychiatric conditions and never prescribe medications.',
    params.exerciseContraindicated
      ? '- IMPORTANT: High-exertion exercise is currently CONTRAINDICATED due to physiological vitals; recommend only restful coping (breathing, music, journaling, speaking with CMO).'
      : '- Suggest 1-2 gentle, practical habitat coping steps.',
  ].join('\n');

  const prompt =
    params.kind === 'JOURNAL_REFLECTION'
      ? `Provide a brief, compassionate private reflection and 2 gentle takeaways on this crew journal entry:\n\n"${params.userText}"`
      : `Crew member message: "${params.userText}"`;

  const t0 = performance.now();
  try {
    if (!_ai) throw new Error('Firebase AI Logic not initialized.');
    const model = getGenerativeModel(_ai, {
      mode: InferenceMode.ONLY_ON_DEVICE,
      onDeviceParams: {
        createOptions: {
          initialPrompts: [
            { role: 'system', content: [{ type: 'text', value: systemInstruction }] },
          ],
        },
      },
    });
    const result = await model.generateContent(prompt);
    const latencyMs = Math.max(1, Math.round(performance.now() - t0));
    const { text: safeReply } = enforceMedicalSafetyText(result.response.text());
    recordExecution('only_on_device', 'on_device', latencyMs, 'STRICT_ZERO_EGRESS_ON_DEVICE');
    return {
      ok: true,
      reply: safeReply,
      latencyMs,
      engineLabel: 'FIREBASE_ONLY_ON_DEVICE · Gemini Nano 4 (Zero-Egress Private)',
    };
  } catch (err) {
    const latencyMs = Math.max(1, Math.round(performance.now() - t0));
    const reason =
      err instanceof Error
        ? err.message
        : 'On-device Gemini Nano 4 not ready in Chrome; cloud fallback intentionally blocked to protect crew privacy.';
    return {
      ok: false,
      reply: '',
      latencyMs,
      engineLabel: 'OFFLINE_DETERMINISTIC_PRIVATE_FALLBACK',
      errorReason: reason,
    };
  }
}

export interface ParsedFreeformAssessment {
  matchedSymptoms: string[];
  vitalsPatch: Partial<{
    heart_rate_bpm: number;
    systolic_bp_mmhg: number;
    diastolic_bp_mmhg: number;
    spo2_pct: number;
    respiratory_rate_bpm: number;
    body_temp_c: number;
    sleep_duration_hrs: number;
    co2_mmhg: number;
  }>;
  summaryNote: string;
  inferenceSource: 'on_device' | 'in_cloud';
  latencyMs: number;
}

/**
 * WORKFLOW 3: Hybrid Structured Output (`Schema.object`) Symptom & Vitals Extractor
 * Parses freeform astronaut voice/text notes into typed TARS Care telemetry & symptom chips.
 */
export async function extractStructuredSymptomsAndVitals(
  rawNote: string,
  allowedSymptoms: string[],
  commMode: 'CONNECTED' | 'DELAYED' | 'OFFLINE',
): Promise<ParsedFreeformAssessment> {
  await ensureHybridSuiteInitialized();

  const intakeSchema = Schema.object({
    properties: {
      matchedSymptoms: Schema.array({
        description: `Exact symptom labels matched from: ${allowedSymptoms.join(', ')}`,
        items: Schema.string(),
      }),
      heart_rate_bpm: Schema.number({ description: 'Heart rate in BPM if stated, else 0' }),
      systolic_bp_mmhg: Schema.number({ description: 'Systolic BP in mmHg if stated, else 0' }),
      diastolic_bp_mmhg: Schema.number({ description: 'Diastolic BP in mmHg if stated, else 0' }),
      spo2_pct: Schema.number({ description: 'SpO2 percentage if stated, else 0' }),
      body_temp_c: Schema.number({ description: 'Body temperature in Celsius if stated, else 0' }),
      sleep_duration_hrs: Schema.number({ description: 'Sleep hours if stated, else 0' }),
      co2_mmhg: Schema.number({ description: 'Cabin CO2 in mmHg if stated, else 0' }),
      summaryNote: Schema.string({
        description: 'Concise one-line clinical intake note without medication advice.',
      }),
    },
    optionalProperties: [
      'heart_rate_bpm',
      'systolic_bp_mmhg',
      'diastolic_bp_mmhg',
      'spo2_pct',
      'body_temp_c',
      'sleep_duration_hrs',
      'co2_mmhg',
    ],
  });

  const mode: HybridModeChoice =
    commMode === 'OFFLINE' && _state.remoteConfig.enforceBlackoutOnDevice
      ? 'only_on_device'
      : 'prefer_on_device';

  const systemInstruction = `Extract structured astronaut vitals and exact symptom checklist items from the crew log. Only select symptoms from this exact list: ${JSON.stringify(
    allowedSymptoms,
  )}. Use 0 for any vital sign not explicitly mentioned.`;

  const t0 = performance.now();
  const model = buildHybridGenerativeModel(mode, systemInstruction, intakeSchema);
  const result = await model.generateContent(`Crew freeform log: "${rawNote}"`);
  const latencyMs = Math.max(1, Math.round(performance.now() - t0));
  const parsed = JSON.parse(result.response.text()) as Record<string, unknown>;

  const validSet = new Set(allowedSymptoms);
  const matchedSymptoms = Array.isArray(parsed.matchedSymptoms)
    ? parsed.matchedSymptoms
        .map((s) => String(s))
        .filter((s) => validSet.has(s))
    : [];

  const vitalsPatch: ParsedFreeformAssessment['vitalsPatch'] = {};
  const numericBounds: Record<keyof ParsedFreeformAssessment['vitalsPatch'], [number, number]> = {
    heart_rate_bpm: [35, 210],
    systolic_bp_mmhg: [65, 220],
    diastolic_bp_mmhg: [40, 140],
    spo2_pct: [70, 100],
    respiratory_rate_bpm: [6, 50],
    body_temp_c: [34, 42],
    sleep_duration_hrs: [0.5, 16],
    co2_mmhg: [0.2, 15],
  };

  (Object.keys(numericBounds) as Array<keyof typeof numericBounds>).forEach((k) => {
    const val = Number(parsed[k]);
    const [lo, hi] = numericBounds[k];
    if (Number.isFinite(val) && val >= lo && val <= hi) {
      vitalsPatch[k] = val;
    }
  });

  const actualSource: 'on_device' | 'in_cloud' =
    result.response.inferenceSource === InferenceSource.ON_DEVICE ? 'on_device' : 'in_cloud';

  recordExecution(
    mode,
    actualSource,
    latencyMs,
    actualSource === 'on_device' ? 'STRICT_ZERO_EGRESS_ON_DEVICE' : 'HYBRID_APP_CHECK_PROTECTED',
  );

  return {
    matchedSymptoms,
    vitalsPatch,
    summaryNote: enforceMedicalSafetyText(String(parsed.summaryNote || rawNote)).text,
    inferenceSource: actualSource,
    latencyMs,
  };
}

/**
 * WORKFLOW 4: Cloud-Preferred Flight Surgeon Consult Synthesis + Firestore Store-and-Forward Queue
 * Uses InferenceMode.PREFER_IN_CLOUD when Earth link is active, automatically falling back to
 * on-device Gemini Nano 4 if disconnected, and persists the packet into Cloud Firestore's
 * offline-capable `consult_packets` collection.
 */
export async function synthesizeAndQueueFlightSurgeonBrief(params: {
  crewId: string;
  crewName: string;
  sol: number;
  urgency: string;
  commMode: 'CONNECTED' | 'DELAYED' | 'OFFLINE';
  consultMarkdown: string;
  cmoNotes: string;
}): Promise<{
  aiBrief: string;
  inferenceSource: 'on_device' | 'in_cloud' | 'deterministic_safety_fallback';
  latencyMs: number;
  queuedInFirestore: boolean;
  pendingCloudSync: boolean;
}> {
  await ensureHybridSuiteInitialized();
  const mode: HybridModeChoice =
    params.commMode === 'OFFLINE' ? 'only_on_device' : 'prefer_in_cloud';

  const systemInstruction = [
    'You are assisting the onboard Crew Medical Officer preparing an asynchronous Earth Flight Surgeon consultation brief.',
    'Summarize key baseline deviations, prioritize 3 focused questions for terrestrial specialists, preserve mGy vs mSv unit separation, and never prescribe medication dosages.',
  ].join('\n');

  const t0 = performance.now();
  let aiBrief = '';
  let actualSource: 'on_device' | 'in_cloud' | 'deterministic_safety_fallback' =
    'deterministic_safety_fallback';

  try {
    const model = buildHybridGenerativeModel(mode, systemInstruction);
    const result = await model.generateContent(
      `CMO Notes: ${params.cmoNotes || 'Routine longitudinal review'}\n\nConsult Packet:\n${params.consultMarkdown.slice(0, 3500)}`,
    );
    aiBrief = enforceMedicalSafetyText(result.response.text()).text;
    actualSource =
      result.response.inferenceSource === InferenceSource.ON_DEVICE ? 'on_device' : 'in_cloud';
  } catch (err) {
    _state.lastError = err instanceof Error ? err.message : String(err);
    aiBrief = [
      `• Sol ${params.sol} Store-and-Forward Brief (${params.urgency}): Telemetry & baseline audit packaged locally.`,
      '• Key Review Request: Correlate recent cardiovascular/environmental deltas with onboard countermeasures.',
      '• Safety Boundary: Private crew behavioral journals excluded; awaiting Flight Surgeon review.',
    ].join('\n');
  }

  const latencyMs = Math.max(1, Math.round(performance.now() - t0));
  recordExecution(
    mode,
    actualSource,
    latencyMs,
    actualSource === 'on_device' ? 'STRICT_ZERO_EGRESS_ON_DEVICE' : 'HYBRID_APP_CHECK_PROTECTED',
  );

  let queuedInFirestore = false;
  if (_db && _state.firebaseConfigured) {
    try {
      await addDoc(collection(_db, 'consult_packets'), {
        crewId: params.crewId,
        crewName: params.crewName,
        sol: params.sol,
        urgency: params.urgency,
        summary: aiBrief.slice(0, 500),
        cmoNotes: params.cmoNotes.slice(0, 400),
        sourcePlatform: 'WEB_CHROME',
        inferenceSource: actualSource,
        is_private_journal: false,
        createdAtIso: new Date().toISOString(),
        createdAtMs: Date.now(),
      });
      queuedInFirestore = true;
    } catch {
      queuedInFirestore = false;
    }
  }

  return {
    aiBrief,
    inferenceSource: actualSource,
    latencyMs,
    queuedInFirestore,
    pendingCloudSync: !_state.firestoreNetworkEnabled,
  };
}

/**
 * Publishes an EVA field check-in to Firestore (`eva_logs`) so Web Chrome and
 * the Native Android EVA Companion share a unified offline-first telemetry stream.
 */
export async function logCrossPlatformEvaEvent(params: {
  crewId: string;
  crewName: string;
  sol: number;
  urgency: string;
  summary: string;
  inferenceSource: string;
}): Promise<boolean> {
  await ensureHybridSuiteInitialized();
  if (!_db || !_state.firebaseConfigured) return false;
  try {
    await addDoc(collection(_db, 'eva_logs'), {
      ...params,
      sourcePlatform: 'WEB_CHROME',
      is_private_journal: false,
      createdAtIso: new Date().toISOString(),
      createdAtMs: Date.now(),
    });
    return true;
  } catch {
    return false;
  }
}

