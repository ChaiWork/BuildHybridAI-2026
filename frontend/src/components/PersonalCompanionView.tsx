import React, { useState } from 'react';
import {
  MessageSquareHeart,
  BookOpen,
  ShieldCheck,
  Lock,
  Send,
  Sparkles,
  Plus,
  Edit3,
  Trash2,
  Search,
  HeartHandshake,
  AlertTriangle,
  CheckCircle2,
  Sliders,
  Smile,
  Calendar,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import {
  FullSystemState,
  JournalEntryRecord,
} from '../types';

interface Props {
  state: FullSystemState;
  apiBase: string;
  onStateUpdate: (newState: FullSystemState) => void;
  initialTab?: 'companion' | 'journal' | 'privacy';
}

const EXAMPLE_CONVERSATION_STARTERS = [
  { label: 'Daily Check-In', text: 'How are you feeling today?', mode: 'DAILY_CHECK_IN' },
  { label: 'Difficult Mission Day', text: 'Today was a difficult mission day.', mode: 'COMPANION_CHAT' },
  { label: 'Missing Family', text: 'I miss my family on Earth.', mode: 'COMPANION_CHAT' },
  { label: 'Sleep Trouble', text: 'I cannot sleep properly.', mode: 'COMPANION_CHAT' },
  { label: 'Guided Reflection', text: 'Help me reflect on what happened today.', mode: 'GUIDED_REFLECTION' },
  {
    label: 'Something Positive',
    text: 'Tell me something interesting or suggest something positive to do.',
    mode: 'COMPANION_CHAT',
  },
];

export const PersonalCompanionView: React.FC<Props> = ({
  state,
  apiBase,
  onStateUpdate,
  initialTab = 'companion',
}) => {
  const companionState = state.companion_state;
  const [activeTab, setActiveTab] = useState<'companion' | 'journal' | 'privacy'>(initialTab);
  const [busy, setBusy] = useState<boolean>(false);
  const [banner, setBanner] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Sync tab if parent switches between 'companion' and 'journal'
  React.useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Companion Chat State
  const activeConv = companionState?.conversations?.[0] || null;
  const [selectedConvUid, setSelectedConvUid] = useState<string | null>(
    activeConv?.conversation_uid || null
  );
  const [chatInput, setChatInput] = useState<string>('');
  const [chatMode, setChatMode] = useState<string>('COMPANION_CHAT');
  const [escalationBanner, setEscalationBanner] = useState<any | null>(null);

  // Journal Form State
  const [editingEntryUid, setEditingEntryUid] = useState<string | null>(null);
  const [journalForm, setJournalForm] = useState({
    title: '',
    content: '',
    mood: 'Positive',
    feelings: ['Calm'] as string[],
    tagsInput: 'Daily Reflection, Habitat Life',
    guided_prompt: '',
    allow_ai_access: false,
  });

  // Journal Search & Filter State
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [moodFilter, setMoodFilter] = useState<string>('ALL');
  const [feelingFilter, setFeelingFilter] = useState<string>('ALL');
  const [solFilter, setSolFilter] = useState<string>('');

  // Quick Mood Check-In State
  const [checkinForm, setCheckinForm] = useState({
    mood: 'Positive',
    feelings: ['Calm', 'Motivated'] as string[],
    note: '',
  });

  if (!companionState) {
    return (
      <div className="mc-card p-6 text-sm text-[#8E95A8]">
        Loading TARSCARE Personal Companion &amp; Private Journal...
      </div>
    );
  }

  const {
    feature_title,
    privacy_settings,
    guided_reflection_prompts,
    mood_levels,
    feeling_tags,
    journal_entries,
    mood_checkins,
    mood_trend,
    conversations,
    local_ai_status,
    non_diagnostic_disclaimer,
  } = companionState;

  const currentConversation =
    conversations.find((c) => c.conversation_uid === selectedConvUid) ||
    conversations[0] ||
    null;

  const toggleFeelingInList = (list: string[], f: string): string[] =>
    list.includes(f) ? list.filter((x) => x !== f) : [...list, f];

  const handleSendChat = async (textOverride?: string, modeOverride?: string) => {
    const messageText = (textOverride ?? chatInput).trim();
    if (!messageText) return;
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch(`${apiBase}/api/companion/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText,
          conversation_uid: currentConversation?.conversation_uid || null,
          mode: modeOverride || chatMode,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Companion request failed');
      if (data.state) onStateUpdate(data.state);
      if (data.conversation_uid) setSelectedConvUid(data.conversation_uid);
      if (data.escalation_info?.triggered) {
        setEscalationBanner(data.escalation_info);
      }
      if (!textOverride) setChatInput('');
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Unable to send message' });
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerSafetyEscalation = async () => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch(`${apiBase}/api/companion/escalate-support`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summary_note:
            'Astronaut activated onboard Crew Medical Officer & psychological support protocol from TARSCARE Companion.',
          queue_urgent_report: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Escalation failed');
      if (data.state) onStateUpdate(data.state);
      setBanner({
        type: 'ok',
        text: `Activated ${data.procedure_note}. Notified ${data.contact_role} and queued an URGENT support notice in the Communication Message Centre.`,
      });
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Error triggering support escalation' });
    } finally {
      setBusy(false);
    }
  };

  const handleSaveJournalEntry = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!journalForm.content.trim()) return;
    setBusy(true);
    setBanner(null);
    const parsedTags = journalForm.tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      if (editingEntryUid) {
        const res = await fetch(`${apiBase}/api/journal/entries/${editingEntryUid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: journalForm.title || `Sol ${state.latest_telemetry.mission_day} Reflection`,
            content: journalForm.content,
            mood: journalForm.mood,
            feelings: journalForm.feelings,
            tags: parsedTags,
            guided_prompt: journalForm.guided_prompt,
            allow_ai_access: journalForm.allow_ai_access,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to update journal entry');
        if (data.state) onStateUpdate(data.state);
        setEditingEntryUid(null);
        setBanner({ type: 'ok', text: `Updated private journal entry "${data.entry.title}".` });
      } else {
        const res = await fetch(`${apiBase}/api/journal/entries`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: journalForm.title || `Sol ${state.latest_telemetry.mission_day} Personal Reflection`,
            content: journalForm.content,
            mood: journalForm.mood,
            feelings: journalForm.feelings,
            tags: parsedTags,
            guided_prompt: journalForm.guided_prompt,
            is_private: true,
            allow_ai_access: journalForm.allow_ai_access,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save journal entry');
        if (data.state) onStateUpdate(data.state);
        setBanner({
          type: 'ok',
          text: `Saved private journal entry "${data.entry.title}" locally on spacecraft storage.`,
        });
      }
      setJournalForm({
        title: '',
        content: '',
        mood: 'Positive',
        feelings: ['Calm'],
        tagsInput: 'Daily Reflection',
        guided_prompt: '',
        allow_ai_access: false,
      });
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Error saving journal entry' });
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteJournal = async (entry: JournalEntryRecord) => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch(`${apiBase}/api/journal/entries/${entry.entry_uid}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete entry');
      if (data.state) onStateUpdate(data.state);
      setBanner({ type: 'ok', text: `Deleted journal entry "${entry.title}".` });
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Error deleting entry' });
    } finally {
      setBusy(false);
    }
  };

  const handleRecordMoodCheckIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch(`${apiBase}/api/companion/mood-checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(checkinForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to log mood check-in');
      if (data.state) onStateUpdate(data.state);
      setCheckinForm({ ...checkinForm, note: '' });
      setBanner({
        type: 'ok',
        text: `Logged self-reported mood check-in (${data.checkin.mood}) without altering physiological telemetry.`,
      });
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Error recording mood' });
    } finally {
      setBusy(false);
    }
  };

  const handleUpdatePrivacy = async (updates: Partial<typeof privacy_settings>) => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch(`${apiBase}/api/companion/privacy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update privacy settings');
      if (data.state) onStateUpdate(data.state);
      setBanner({
        type: 'ok',
        text: 'Updated personal privacy and AI companion context permissions.',
      });
    } catch (err: any) {
      setBanner({ type: 'err', text: err.message || 'Error updating privacy' });
    } finally {
      setBusy(false);
    }
  };

  const filteredJournals = journal_entries.filter((j) => {
    if (moodFilter !== 'ALL' && j.mood !== moodFilter) return false;
    if (
      feelingFilter !== 'ALL' &&
      !j.feelings.includes(feelingFilter) &&
      !j.tags.includes(feelingFilter)
    ) {
      return false;
    }
    if (solFilter.trim() && String(j.mission_day) !== solFilter.trim()) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const hay = `${j.title} ${j.content} ${j.tags.join(' ')} ${j.feelings.join(' ')} ${j.mood}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="mc-card p-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5 mb-2">
              <h1 className="text-2xl font-bold text-[#FAF9FA] tracking-tight">
                {feature_title}
              </h1>
              <span className="mc-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                <Lock className="w-3 h-3" />
                100% Local Private Storage
              </span>
              <span className="mc-pill bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/30">
                {local_ai_status?.ollama_available
                  ? `Local Ollama (${local_ai_status.ollama_model})`
                  : 'Offline Companion Engine Ready'}
              </span>
            </div>
            <p className="text-sm text-[#E5E5E4] max-w-3xl">
              {non_diagnostic_disclaimer}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleTriggerSafetyEscalation}
              disabled={busy}
              className="mc-btn-secondary text-xs flex items-center gap-1.5 border border-amber-500/30 text-amber-200"
            >
              <HeartHandshake className="w-3.5 h-3.5 text-amber-300" />
              Contact Crew Medical Officer / Support
            </button>
          </div>
        </div>

        {/* Sub-Tabs */}
        <div className="flex flex-wrap items-center gap-2 mt-5 pt-4 border-t border-[#222638]">
          {[
            { id: 'companion', label: 'AI Companion Conversation', icon: MessageSquareHeart },
            { id: 'journal', label: `My Journal (${journal_entries.length}) & Mood Tracker`, icon: BookOpen },
            { id: 'privacy', label: 'Privacy & AI Consent Settings', icon: ShieldCheck },
          ].map((t) => {
            const Icon = t.icon;
            const active = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id as any)}
                className={`px-4 py-2 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 ${
                  active
                    ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                    : 'bg-white/[0.04] text-[#E5E5E4] hover:bg-white/[0.08]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Feedback Banner */}
      {banner && (
        <div
          className={`mc-card p-4 flex items-center justify-between text-sm ${
            banner.type === 'ok'
              ? 'border-emerald-500/40 text-emerald-200'
              : 'border-rose-500/40 text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2">
            {banner.type === 'ok' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{banner.text}</span>
          </div>
          <button
            onClick={() => setBanner(null)}
            className="text-xs text-[#8E95A8] hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Psychological Safety Escalation Banner (if triggered) */}
      {escalationBanner && (
        <div className="mc-card p-5 border border-rose-500/50 bg-rose-950/20 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-rose-200 flex items-center gap-2">
              <HeartHandshake className="w-5 h-5 text-rose-400" />
              Immediate Onboard Crew Support &amp; Safety Protocol Activated
            </h2>
            <span className="mc-pill bg-rose-500/20 text-rose-200 border border-rose-400/40">
              {escalationBanner.procedure_note}
            </span>
          </div>
          <p className="text-xs text-[#FAF9FA]">
            Designated Onboard Support Contact: <strong>{escalationBanner.contact_role}</strong> · Earth Link:{' '}
            {escalationBanner.earth_comm_summary}
          </p>
          <ul className="text-xs text-[#E5E5E4] space-y-1">
            {(escalationBanner.recommended_steps || []).map((st: string, idx: number) => (
              <li key={idx}>• {st}</li>
            ))}
          </ul>
          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleTriggerSafetyEscalation}
              className="mc-btn-primary text-xs px-4 py-2"
            >
              Prepare Urgent Support Report for CMO &amp; Mission Control
            </button>
            <button
              onClick={() => setEscalationBanner(null)}
              className="mc-btn-secondary text-xs px-3 py-2"
            >
              Acknowledge
            </button>
          </div>
        </div>
      )}

      {/* TAB 1: CONVERSATIONAL AI COMPANION */}
      {activeTab === 'companion' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Chat Column */}
          <div className="lg:col-span-2 mc-card p-6 flex flex-col justify-between space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-[#222638]">
              <div>
                <h2 className="text-lg font-semibold text-[#FAF9FA]">
                  Conversational AI Companion
                </h2>
                <p className="text-xs text-[#8E95A8]">
                  Journal Context Sharing:{' '}
                  <strong className="text-[#E5E5E4]">
                    {privacy_settings.allow_ai_journal_context ? 'Enabled (With Consent)' : 'Disabled (Private)'}
                  </strong>{' '}
                  · Exercise Hold:{' '}
                  <strong className="text-[#E5E5E4]">
                    {state.assessment.exercise_contraindicated ? 'Active (Restful coping only)' : 'Nominal'}
                  </strong>
                </p>
              </div>
              <button
                onClick={() => setActiveTab('privacy')}
                className="mc-btn-secondary text-xs flex items-center gap-1"
              >
                <Sliders className="w-3.5 h-3.5" />
                Privacy Consent
              </button>
            </div>

            {/* Quick Conversation Starters */}
            <div className="space-y-2">
              <span className="text-xs text-[#8E95A8] block">
                Start a conversation or choose a supportive topic:
              </span>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_CONVERSATION_STARTERS.map((st) => (
                  <button
                    key={st.label}
                    disabled={busy}
                    onClick={() => {
                      setChatMode(st.mode);
                      handleSendChat(st.text, st.mode);
                    }}
                    className="px-3 py-1.5 rounded-full text-xs bg-[#0B0D1A] hover:bg-white/[0.08] text-[#E5E5E4] border border-[#222638] transition-all"
                  >
                    &ldquo;{st.text}&rdquo;
                  </button>
                ))}
              </div>
            </div>

            {/* Messages Thread */}
            <div className="space-y-4 max-h-[440px] overflow-y-auto pr-1 py-2">
              {(currentConversation?.messages || []).map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div
                    key={msg.message_uid}
                    className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    <div
                      className={`max-w-[88%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                        isUser
                          ? 'bg-[#A5D8FF]/15 text-[#FAF9FA]'
                          : 'bg-[#0B0D1A]/90 text-[#E5E5E4]'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3 mb-1 text-[11px] text-[#8E95A8]">
                        <span className="font-semibold text-[#FAF9FA]">
                          {isUser ? state.astronaut.name : 'TARSCARE Companion'}
                        </span>
                        <span>{isUser ? 'Crew' : msg.engine_used}</span>
                      </div>
                      <div className="whitespace-pre-line">{msg.content}</div>

                      {!isUser && msg.suggested_coping && msg.suggested_coping.length > 0 && (
                        <div className="mt-3 pt-2.5 border-t border-[#222638]">
                          <span className="text-[11px] font-medium text-[#A5D8FF] block mb-1">
                            Suggested Restful &amp; Supportive Activities (Non-Medical):
                          </span>
                          <ul className="space-y-1 text-[11px] text-[#E5E5E4]">
                            {msg.suggested_coping.map((c, idx) => (
                              <li key={idx}>• {c}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Chat Input Box */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendChat();
              }}
              className="pt-3 border-t border-[#222638] flex flex-col sm:flex-row gap-2"
            >
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Write freely to your onboard companion (works 100% offline)..."
                className="flex-1 rounded-xl bg-[#0B0D1A] border border-[#222638] px-4 py-2.5 text-xs text-[#FAF9FA]"
              />
              <button
                type="submit"
                disabled={busy || !chatInput.trim()}
                className="mc-btn-primary px-5 py-2.5 text-xs flex items-center justify-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5" />
                {busy ? 'Responding...' : 'Send'}
              </button>
            </form>
          </div>

          {/* Right Column: Daily Mood Check-In & Guided Reflection Prompts */}
          <div className="space-y-6">
            <div className="mc-card p-6">
              <h2 className="text-base font-semibold text-[#FAF9FA] mb-1 flex items-center gap-2">
                <Smile className="w-4 h-4 text-[#A5D8FF]" />
                Optional Daily Mood Check-In
              </h2>
              <p className="text-xs text-[#8E95A8] mb-3">
                Self-reported reflection only — never overwrites physiological vital signs or generates clinical diagnoses.
              </p>
              <form onSubmit={handleRecordMoodCheckIn} className="space-y-3 text-xs">
                <div>
                  <label className="block text-[#E5E5E4] mb-1.5">How is your mood right now?</label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {mood_levels.map((ml) => (
                      <button
                        type="button"
                        key={ml}
                        onClick={() => setCheckinForm({ ...checkinForm, mood: ml })}
                        className={`px-2.5 py-1.5 rounded-lg text-xs transition-all ${
                          checkinForm.mood === ml
                            ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                            : 'bg-[#0B0D1A] text-[#E5E5E4] hover:bg-white/[0.06]'
                        }`}
                      >
                        {ml}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-[#E5E5E4] mb-1.5">Optional Feelings</label>
                  <div className="flex flex-wrap gap-1.5">
                    {feeling_tags.map((ft) => {
                      const active = checkinForm.feelings.includes(ft);
                      return (
                        <button
                          type="button"
                          key={ft}
                          onClick={() =>
                            setCheckinForm({
                              ...checkinForm,
                              feelings: toggleFeelingInList(checkinForm.feelings, ft),
                            })
                          }
                          className={`px-2.5 py-1 rounded-full text-[11px] ${
                            active
                              ? 'bg-[#A5D8FF]/20 text-[#A5D8FF] border border-[#A5D8FF]/40'
                              : 'bg-[#0B0D1A] text-[#8E95A8]'
                          }`}
                        >
                          {ft}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="block text-[#E5E5E4] mb-1">Brief Note (Optional)</label>
                  <input
                    type="text"
                    value={checkinForm.note}
                    onChange={(e) => setCheckinForm({ ...checkinForm, note: e.target.value })}
                    placeholder="e.g., Quiet evening after EVA prep"
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                  />
                </div>

                <button type="submit" disabled={busy} className="mc-btn-secondary w-full py-2">
                  Save Self-Reported Mood Check-In
                </button>
              </form>
            </div>

            {/* Guided Reflection Prompts */}
            <div className="mc-card p-6">
              <h2 className="text-base font-semibold text-[#FAF9FA] mb-1 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#A5D8FF]" />
                Guided Reflection Prompts
              </h2>
              <p className="text-xs text-[#8E95A8] mb-3">
                Click any question to discuss with the AI Companion or open in My Journal.
              </p>
              <div className="space-y-2 text-xs">
                {guided_reflection_prompts.slice(0, 6).map((prompt) => (
                  <div
                    key={prompt}
                    className="p-2.5 rounded-lg bg-[#0B0D1A]/60 flex items-center justify-between gap-2"
                  >
                    <span className="text-[#E5E5E4]">{prompt}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => handleSendChat(prompt, 'GUIDED_REFLECTION')}
                        className="px-2 py-1 rounded bg-white/[0.06] hover:bg-white/[0.12] text-[11px] text-[#A5D8FF]"
                      >
                        Chat
                      </button>
                      <button
                        onClick={() => {
                          setJournalForm({ ...journalForm, guided_prompt: prompt });
                          setActiveTab('journal');
                        }}
                        className="px-2 py-1 rounded bg-white/[0.06] hover:bg-white/[0.12] text-[11px] text-[#E5E5E4]"
                      >
                        Journal
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: MY JOURNAL & MOOD TRENDS */}
      {activeTab === 'journal' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Create / Edit Journal Entry Form */}
            <div className="mc-card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-[#FAF9FA]">
                  {editingEntryUid ? 'Edit Private Journal Entry' : 'Write in My Journal'}
                </h2>
                {editingEntryUid && (
                  <button
                    onClick={() => {
                      setEditingEntryUid(null);
                      setJournalForm({
                        title: '',
                        content: '',
                        mood: 'Positive',
                        feelings: ['Calm'],
                        tagsInput: 'Daily Reflection',
                        guided_prompt: '',
                        allow_ai_access: false,
                      });
                    }}
                    className="text-xs text-[#8E95A8] hover:text-white"
                  >
                    Cancel Edit
                  </button>
                )}
              </div>
              <p className="text-xs text-[#8E95A8]">
                Write freely or pick an optional reflection question. Entries are stored privately on local spacecraft SQLite storage.
              </p>

              <form onSubmit={handleSaveJournalEntry} className="space-y-3 text-xs">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">
                    Optional Guided Reflection Prompt
                  </label>
                  <select
                    value={journalForm.guided_prompt}
                    onChange={(e) =>
                      setJournalForm({ ...journalForm, guided_prompt: e.target.value })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  >
                    <option value="">Free-form writing (No prompt selected)</option>
                    {guided_reflection_prompts.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[#E5E5E4] mb-1">Entry Title</label>
                  <input
                    type="text"
                    value={journalForm.title}
                    onChange={(e) => setJournalForm({ ...journalForm, title: e.target.value })}
                    placeholder={`Sol ${state.latest_telemetry.mission_day} Personal Reflection`}
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>

                <div>
                  <label className="block text-[#E5E5E4] mb-1">Your Private Reflection *</label>
                  <textarea
                    rows={5}
                    required
                    value={journalForm.content}
                    onChange={(e) => setJournalForm({ ...journalForm, content: e.target.value })}
                    placeholder="Write about your day, emotions, mission challenges, homesickness, crew moments, or personal achievements..."
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[#E5E5E4] mb-1">Optional Mood</label>
                    <select
                      value={journalForm.mood}
                      onChange={(e) => setJournalForm({ ...journalForm, mood: e.target.value })}
                      className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                    >
                      <option value="">None</option>
                      {mood_levels.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[#E5E5E4] mb-1">Tags (comma-separated)</label>
                    <input
                      type="text"
                      value={journalForm.tagsInput}
                      onChange={(e) =>
                        setJournalForm({ ...journalForm, tagsInput: e.target.value })
                      }
                      className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[#E5E5E4] mb-1">Optional Feelings</label>
                  <div className="flex flex-wrap gap-1.5">
                    {feeling_tags.map((ft) => {
                      const active = journalForm.feelings.includes(ft);
                      return (
                        <button
                          type="button"
                          key={ft}
                          onClick={() =>
                            setJournalForm({
                              ...journalForm,
                              feelings: toggleFeelingInList(journalForm.feelings, ft),
                            })
                          }
                          className={`px-2 py-1 rounded-full text-[11px] ${
                            active
                              ? 'bg-[#A5D8FF]/20 text-[#A5D8FF] border border-[#A5D8FF]/40'
                              : 'bg-[#0B0D1A] text-[#8E95A8]'
                          }`}
                        >
                          {ft}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <label className="flex items-center gap-2 text-[#E5E5E4] pt-1">
                  <input
                    type="checkbox"
                    checked={journalForm.allow_ai_access}
                    onChange={(e) =>
                      setJournalForm({ ...journalForm, allow_ai_access: e.target.checked })
                    }
                  />
                  Allow AI Companion to reference this entry (requires global consent enabled)
                </label>

                <button type="submit" disabled={busy} className="mc-btn-primary w-full py-2.5">
                  {editingEntryUid ? 'Update Journal Entry' : 'Save Private Journal Entry'}
                </button>
              </form>
            </div>

            {/* Journal Entries List & Search/Filters */}
            <div className="lg:col-span-2 space-y-6">
              {/* Self-Reported Mood Trend Chart */}
              <div className="mc-card p-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
                  <div>
                    <h2 className="text-base font-semibold text-[#FAF9FA]">
                      Self-Reported Mood &amp; Wellbeing Trend
                    </h2>
                    <p className="text-xs text-[#8E95A8]">
                      1 = Very Low · 2 = Low · 3 = Neutral · 4 = Positive · 5 = Very Positive (Self-Reported Only)
                    </p>
                  </div>
                  <span className="mc-pill bg-white/5 text-[#8E95A8]">
                    {mood_checkins.length} Check-Ins Logged
                  </span>
                </div>
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={mood_trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#222638" />
                      <XAxis
                        dataKey="sol"
                        stroke="#8E95A8"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `Sol ${v}`}
                      />
                      <YAxis
                        domain={[1, 5]}
                        ticks={[1, 2, 3, 4, 5]}
                        stroke="#8E95A8"
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#121522',
                          borderColor: '#222638',
                          borderRadius: '12px',
                          fontSize: '12px',
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="mood_numeric"
                        name="Mood Level"
                        stroke="#A5D8FF"
                        fill="#A5D8FF"
                        fillOpacity={0.18}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Search & Filter Entries */}
              <div className="mc-card p-6 space-y-4">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <h2 className="text-lg font-semibold text-[#FAF9FA]">
                    Previous Journal Entries ({filteredJournals.length})
                  </h2>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-[#8E95A8] absolute left-2.5 top-2" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search entries..."
                        className="pl-8 pr-3 py-1.5 rounded-lg bg-[#0B0D1A] border border-[#222638] text-[#FAF9FA]"
                      />
                    </div>
                    <select
                      value={moodFilter}
                      onChange={(e) => setMoodFilter(e.target.value)}
                      className="rounded-lg bg-[#0B0D1A] border border-[#222638] px-2.5 py-1.5 text-[#FAF9FA]"
                    >
                      <option value="ALL">All Moods</option>
                      {mood_levels.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                    <select
                      value={feelingFilter}
                      onChange={(e) => setFeelingFilter(e.target.value)}
                      className="rounded-lg bg-[#0B0D1A] border border-[#222638] px-2.5 py-1.5 text-[#FAF9FA]"
                    >
                      <option value="ALL">All Feelings</option>
                      {feeling_tags.map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      value={solFilter}
                      onChange={(e) => setSolFilter(e.target.value)}
                      placeholder="Sol #"
                      className="w-20 rounded-lg bg-[#0B0D1A] border border-[#222638] px-2.5 py-1.5 text-[#FAF9FA]"
                    />
                  </div>
                </div>

                <div className="divide-y divide-[#222638]">
                  {filteredJournals.map((entry) => (
                    <div key={entry.entry_uid} className="py-4 first:pt-0 last:pb-0 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold text-[#FAF9FA]">
                              {entry.title}
                            </span>
                            <span className="mc-pill bg-white/5 text-[#E5E5E4]">
                              Sol {entry.mission_day}
                            </span>
                            {entry.mood && (
                              <span className="mc-pill bg-[#A5D8FF]/15 text-[#A5D8FF]">
                                {entry.mood}
                              </span>
                            )}
                            <span className="mc-pill bg-emerald-500/10 text-emerald-300">
                              Private Local Record
                            </span>
                          </div>
                          {entry.guided_prompt && (
                            <div className="text-[11px] text-[#8E95A8] italic mt-0.5">
                              Prompt: &ldquo;{entry.guided_prompt}&rdquo;
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={() => {
                              setEditingEntryUid(entry.entry_uid);
                              setJournalForm({
                                title: entry.title,
                                content: entry.content,
                                mood: entry.mood || 'Positive',
                                feelings: entry.feelings || [],
                                tagsInput: (entry.tags || []).join(', '),
                                guided_prompt: entry.guided_prompt || '',
                                allow_ai_access: entry.allow_ai_access,
                              });
                            }}
                            title="Edit Entry"
                            className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.1] text-[#E5E5E4]"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteJournal(entry)}
                            title="Delete Entry"
                            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      <p className="text-xs text-[#E5E5E4] leading-relaxed whitespace-pre-line">
                        {entry.content}
                      </p>

                      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#8E95A8]">
                        <div className="flex flex-wrap gap-1.5">
                          {entry.feelings.map((f) => (
                            <span key={f} className="px-2 py-0.5 rounded bg-[#0B0D1A] text-[#A5D8FF]">
                              {f}
                            </span>
                          ))}
                          {entry.tags.map((t) => (
                            <span key={t} className="px-2 py-0.5 rounded bg-[#0B0D1A] text-[#8E95A8]">
                              #{t}
                            </span>
                          ))}
                        </div>
                        <span>{entry.created_at.slice(0, 16).replace('T', ' ')} UTC</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: PRIVACY & AI CONSENT SETTINGS */}
      {activeTab === 'privacy' && (
        <div className="mc-card p-6 max-w-3xl space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-[#FAF9FA]">
              Personal Journal Privacy &amp; AI Companion Data Controls
            </h2>
            <p className="text-xs text-[#8E95A8] mt-1">
              Journal entries and AI companion conversations are stored locally on spacecraft SQLite storage. They are never silently transmitted to external cloud servers.
            </p>
          </div>

          <div className="divide-y divide-[#222638] text-xs">
            <div className="py-3.5 flex items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-[#FAF9FA]">
                  Allow AI Companion to Reference My Private Journal Entries
                </div>
                <div className="text-[#8E95A8]">
                  Default is OFF. When enabled, the onboard AI Companion may reference approved journal reflections for continuity.
                </div>
              </div>
              <input
                type="checkbox"
                checked={privacy_settings.allow_ai_journal_context}
                onChange={(e) =>
                  handleUpdatePrivacy({ allow_ai_journal_context: e.target.checked })
                }
                className="w-4 h-4"
              />
            </div>

            <div className="py-3.5 flex items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-[#FAF9FA]">
                  Allow AI Companion to Reference Self-Reported Mood Check-Ins
                </div>
                <div className="text-[#8E95A8]">
                  Helps the companion tailor supportive check-ins to your recent self-reported mood.
                </div>
              </div>
              <input
                type="checkbox"
                checked={privacy_settings.allow_ai_mood_context}
                onChange={(e) =>
                  handleUpdatePrivacy({ allow_ai_mood_context: e.target.checked })
                }
                className="w-4 h-4"
              />
            </div>

            <div className="py-3.5 flex items-center justify-between gap-4">
              <div>
                <div className="font-semibold text-[#FAF9FA]">
                  Store Companion Conversation History Locally
                </div>
                <div className="text-[#8E95A8]">
                  Keep past companion sessions saved in your local crew profile.
                </div>
              </div>
              <input
                type="checkbox"
                checked={privacy_settings.store_companion_history}
                onChange={(e) =>
                  handleUpdatePrivacy({ store_companion_history: e.target.checked })
                }
                className="w-4 h-4"
              />
            </div>
          </div>

          <div className="p-4 rounded-xl bg-[#0B0D1A]/70 text-xs space-y-1">
            <div className="font-semibold text-[#FAF9FA]">
              Configured Onboard Psychological Safety Escalation Contact
            </div>
            <div className="text-[#E5E5E4]">
              Role: <strong>{privacy_settings.escalation_contact_role}</strong>
            </div>
            <div className="text-[#8E95A8]">{privacy_settings.escalation_procedure_note}</div>
          </div>
        </div>
      )}
    </div>
  );
};
