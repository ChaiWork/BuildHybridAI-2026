// Offline browser Web Speech helpers (zero external cloud endpoints required).

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
}

export function isSpeechRecognitionSupported(): boolean {
  if (typeof window === 'undefined') return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function stopSpeaking(): void {
  if (!isSpeechSynthesisSupported()) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    // Ignore speech synthesis errors on restricted platforms
  }
}

export function speakText(
  text: string,
  options?: { rate?: number; onEnd?: () => void; onError?: () => void },
): boolean {
  if (!isSpeechSynthesisSupported() || !text.trim()) {
    options?.onError?.();
    return false;
  }
  try {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = options?.rate ?? 1.02;
    utt.pitch = 1.0;
    if (options?.onEnd) utt.onend = options.onEnd;
    if (options?.onError) utt.onerror = options.onError;
    window.speechSynthesis.speak(utt);
    return true;
  } catch {
    options?.onError?.();
    return false;
  }
}

export interface ParsedVoiceCommand {
  action:
    | 'NEXT_STEP'
    | 'PREV_STEP'
    | 'READ_STEPS'
    | 'STOP_VOICE'
    | 'CONFIRM_STEP'
    | 'TOGGLE_HIGH_CONTRAST'
    | 'SWITCH_HAZARD'
    | 'ADD_SYMPTOM';
  hazard?: string;
  symptom?: string;
  label: string;
}

export function parseVoiceTriageCommand(transcript: string): ParsedVoiceCommand | null {
  const t = transcript.toLowerCase().trim();
  if (!t) return null;

  if (t.includes('stop speaking') || t === 'stop' || t.includes('mute')) {
    return { action: 'STOP_VOICE', label: 'Stopped voice readout' };
  }
  if (t.includes('next')) {
    return { action: 'NEXT_STEP', label: 'Moved to next triage step' };
  }
  if (t.includes('previous') || t.includes('back')) {
    return { action: 'PREV_STEP', label: 'Moved to previous triage step' };
  }
  if (t.includes('confirm') || t.includes('check') || t.includes('done step')) {
    return { action: 'CONFIRM_STEP', label: 'Confirmed current triage step' };
  }
  if (t.includes('read') || t.includes('repeat') || t.includes('speak')) {
    return { action: 'READ_STEPS', label: 'Reading current emergency step aloud' };
  }
  if (t.includes('contrast') || t.includes('eva mode')) {
    return { action: 'TOGGLE_HIGH_CONTRAST', label: 'Toggled High-Contrast EVA/Critical Mode' };
  }
  if (t.includes('radiation') || t.includes('solar') || t.includes('shelter')) {
    return { action: 'SWITCH_HAZARD', hazard: 'Radiation SPE Exposure', label: 'Switched to Radiation SPE shelter protocol' };
  }
  if (t.includes('chest') || t.includes('heart') || t.includes('palpitation')) {
    return { action: 'ADD_SYMPTOM', symptom: 'Chest pain / discomfort', label: 'Flagged Chest pain / discomfort' };
  }
  if (t.includes('breath') || t.includes('shortness') || t.includes('dyspnea')) {
    return { action: 'ADD_SYMPTOM', symptom: 'Shortness of breath', label: 'Flagged Shortness of breath' };
  }
  if (t.includes('dizz') || t.includes('faint') || t.includes('lightheaded')) {
    return { action: 'ADD_SYMPTOM', symptom: 'Faintness / presyncope', label: 'Flagged Faintness / presyncope' };
  }
  return null;
}

export function startVoiceCommandListener(callbacks: {
  onResult: (transcript: string) => void;
  onError: (message: string) => void;
  onEnd: () => void;
}): (() => void) | null {
  if (!isSpeechRecognitionSupported()) {
    callbacks.onError(
      'Local browser SpeechRecognition engine unavailable here — use manual quick-command chips or touch controls.',
    );
    callbacks.onEnd();
    return null;
  }
  try {
    const w = window as unknown as {
      SpeechRecognition?: new () => {
        lang: string;
        interimResults: boolean;
        maxAlternatives: number;
        onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
        onerror: ((e: { error?: string }) => void) | null;
        onend: (() => void) | null;
        start: () => void;
        stop: () => void;
      };
      webkitSpeechRecognition?: new () => {
        lang: string;
        interimResults: boolean;
        maxAlternatives: number;
        onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
        onerror: ((e: { error?: string }) => void) | null;
        onend: (() => void) | null;
        start: () => void;
        stop: () => void;
      };
    };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) {
      callbacks.onEnd();
      return null;
    }
    const rec = new Ctor();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      const text = event.results?.[0]?.[0]?.transcript || '';
      if (text) callbacks.onResult(text);
    };
    rec.onerror = (evt) => {
      callbacks.onError(`Voice capture error (${evt.error || 'unknown'}). Manual touch controls remain active.`);
    };
    rec.onend = () => callbacks.onEnd();
    rec.start();
    return () => {
      try {
        rec.stop();
      } catch {
        // Ignore stop error if already ended
      }
    };
  } catch {
    callbacks.onError('Unable to initialize local microphone recognition; manual controls remain active.');
    callbacks.onEnd();
    return null;
  }
}
