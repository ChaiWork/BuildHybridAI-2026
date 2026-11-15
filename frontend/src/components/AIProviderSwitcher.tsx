import React, { useState } from 'react';
import { Cloud, Cpu, KeyRound, RefreshCw } from 'lucide-react';
import { FullSystemState, LocalAIStatus } from '../types';
import { updateLocalAIConfig, warmupLocalAI } from './uiHelpers';

interface AIProviderSwitcherProps {
  aiStatus?: LocalAIStatus;
  variant?: 'toolbar' | 'sidebar' | 'panel';
  collapsed?: boolean;
  onStateUpdated?: (next: FullSystemState) => void;
  onNotice?: (msg: string | null) => void;
}

/**
 * Unified switcher between Local LLM (Ollama / offline RAG) and External API LLM (Groq Cloud).
 * Keeps sidebar footprint compact while providing full model selection and API testing in AI views.
 */
export const AIProviderSwitcher: React.FC<AIProviderSwitcherProps> = ({
  aiStatus,
  variant = 'toolbar',
  collapsed = false,
  onStateUpdated,
  onNotice,
}) => {
  const [busy, setBusy] = useState(false);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [keyInput, setKeyInput] = useState('');

  const provider: 'local' | 'api' = aiStatus?.llm_provider === 'api' ? 'api' : 'local';
  const llmEnabled = aiStatus?.llm_enabled ?? true;
  const localModels =
    aiStatus?.installed_chat_models && aiStatus.installed_chat_models.length > 0
      ? aiStatus.installed_chat_models
      : aiStatus?.ollama_model
        ? [aiStatus.ollama_model]
        : [];
  const apiCatalog = aiStatus?.api_model_catalog || [];
  const apiModels =
    apiCatalog.length > 0
      ? apiCatalog.map((m) => ({ id: m.id, label: m.label }))
      : (aiStatus?.available_api_models || ['qwen/qwen3.8-27b']).map((id) => ({
          id,
          label: id === 'qwen/qwen3.8-27b' ? `${id} (Recommended)` : id,
        }));

  const activeModel =
    provider === 'api'
      ? aiStatus?.api_model || apiModels[0]?.id || 'qwen/qwen3.8-27b'
      : aiStatus?.ollama_model || localModels[0] || '';

  const emitNotice = (msg: string | null) => {
    if (onNotice) onNotice(msg);
  };

  const handleSwitchProvider = async (nextProvider: 'local' | 'api') => {
    if (busy) return;
    setBusy(true);
    emitNotice(null);
    try {
      const next = await updateLocalAIConfig(
        { llm_provider: nextProvider, llm_enabled: true },
        onStateUpdated,
      );
      if (nextProvider === 'api') {
        if (next.api_blocked_blackout) {
          emitNotice(
            'Switched preference to API LLM (Groq), currently paused because Link Status is OFFLINE Blackout.',
          );
        } else if (!next.api_key_configured) {
          emitNotice('Switched to API LLM, but no GROQ_API_KEY is configured yet.');
        } else {
          emitNotice(`Switched to Groq API LLM (${next.api_model || 'qwen/qwen3.8-27b'}).`);
        }
      } else {
        emitNotice(
          next.ollama_available
            ? `Switched to Local LLM (Ollama · ${next.ollama_model}).`
            : 'Switched to Local LLM mode (Ollama offline — using deterministic offline RAG fallback).',
        );
      }
    } catch (err) {
      emitNotice(err instanceof Error ? err.message : 'Unable to switch LLM provider.');
    } finally {
      setBusy(false);
    }
  };

  const handleModelChange = async (modelName: string) => {
    setBusy(true);
    emitNotice(null);
    try {
      if (provider === 'api') {
        await updateLocalAIConfig({ selected_api_model: modelName }, onStateUpdated);
        emitNotice(`Active Groq API model switched to ${modelName}.`);
      } else {
        await updateLocalAIConfig({ selected_model: modelName }, onStateUpdated);
        emitNotice(`Active local Ollama model switched to ${modelName}.`);
      }
    } catch (err) {
      emitNotice(err instanceof Error ? err.message : 'Unable to switch model.');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleLLM = async () => {
    setBusy(true);
    emitNotice(null);
    try {
      const nextEnabled = !llmEnabled;
      await updateLocalAIConfig({ llm_enabled: nextEnabled }, onStateUpdated);
      emitNotice(
        nextEnabled
          ? `${provider === 'api' ? 'Groq API' : 'Local Ollama'} synthesis enabled alongside grounded NASA/CSA RAG.`
          : 'Deterministic offline RAG mode active (generative LLM paused).',
      );
    } catch (err) {
      emitNotice(err instanceof Error ? err.message : 'Unable to update AI synthesis mode.');
    } finally {
      setBusy(false);
    }
  };

  const handleWarmup = async () => {
    setBusy(true);
    emitNotice(null);
    try {
      const res = await warmupLocalAI(activeModel || null, onStateUpdated, provider);
      emitNotice(res.message);
    } catch (err) {
      emitNotice(err instanceof Error ? err.message : 'Engine verification failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = keyInput.trim();
    if (!cleaned) return;
    setBusy(true);
    emitNotice(null);
    try {
      const next = await updateLocalAIConfig(
        { groq_api_key: cleaned, llm_provider: 'api', llm_enabled: true },
        onStateUpdated,
      );
      setKeyInput('');
      setShowKeyForm(false);
      emitNotice(`Groq API key saved (${next.api_key_status}). Active model: ${next.api_model}.`);
    } catch (err) {
      emitNotice(err instanceof Error ? err.message : 'Unable to save Groq API key.');
    } finally {
      setBusy(false);
    }
  };

  const statusLabel = (() => {
    if (!llmEnabled) {
      return aiStatus?.sentence_transformers_cached
        ? 'Offline Semantic RAG'
        : 'Deterministic Offline RAG';
    }
    if (provider === 'api') {
      if (aiStatus?.api_blocked_blackout) return 'API Paused (Blackout) · Offline RAG';
      if (aiStatus?.api_available) return `Groq API (${aiStatus?.api_model || 'qwen/qwen3.8-27b'})`;
      return 'API Key Missing · Offline RAG';
    }
    if (aiStatus?.ollama_available) {
      return `Local Ollama (${aiStatus?.ollama_model})`;
    }
    return aiStatus?.sentence_transformers_cached
      ? 'Offline Semantic RAG'
      : 'Deterministic Offline RAG';
  })();

  if (variant === 'sidebar') {
    if (collapsed) {
      const nextMode = provider === 'api' ? 'local' : 'api';
      return (
        <button
          type="button"
          disabled={busy}
          onClick={() => handleSwitchProvider(nextMode)}
          title={`AI Mode: ${provider === 'api' ? 'API LLM (Groq)' : 'Local LLM'} — click to switch`}
          aria-label={`Switch AI mode (currently ${provider === 'api' ? 'API LLM' : 'Local LLM'})`}
          className="w-full flex items-center justify-center p-2 rounded-xl bg-[#0B0D1A] border border-white/[0.1] text-[#A5D8FF] hover:border-[#A5D8FF]/45 transition-colors disabled:opacity-60"
        >
          {provider === 'api' ? <Cloud className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
        </button>
      );
    }

    return (
      <div className="space-y-1.5">
        <div
          role="group"
          aria-label="Switch between Local LLM and API LLM"
          className="grid grid-cols-2 rounded-full bg-[#0B0D1A] border border-white/[0.1] p-0.5"
        >
          <button
            type="button"
            disabled={busy}
            aria-pressed={provider === 'local'}
            onClick={() => handleSwitchProvider('local')}
            className={`px-2 py-1 rounded-full text-[11px] font-medium inline-flex items-center justify-center gap-1 transition-colors ${
              provider === 'local'
                ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                : 'text-[#E5E5E4]/75 hover:text-[#FAF9FA]'
            }`}
          >
            <Cpu className="w-3 h-3 shrink-0" />
            <span>Local LLM</span>
          </button>
          <button
            type="button"
            disabled={busy}
            aria-pressed={provider === 'api'}
            onClick={() => handleSwitchProvider('api')}
            className={`px-2 py-1 rounded-full text-[11px] font-medium inline-flex items-center justify-center gap-1 transition-colors ${
              provider === 'api'
                ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                : 'text-[#E5E5E4]/75 hover:text-[#FAF9FA]'
            }`}
          >
            <Cloud className="w-3 h-3 shrink-0" />
            <span>API LLM</span>
          </button>
        </div>
        <div className="text-[11px] text-[#E5E5E4]/65 truncate text-center" title={statusLabel}>
          {statusLabel}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Segmented Local LLM <-> API LLM Switch */}
      <div
        role="group"
        aria-label="Select AI LLM provider"
        className="inline-flex items-center rounded-full bg-[#0B0D1A] border border-white/15 p-0.5"
      >
        <button
          type="button"
          disabled={busy}
          aria-pressed={provider === 'local'}
          onClick={() => handleSwitchProvider('local')}
          className={`px-3 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${
            provider === 'local'
              ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
              : 'text-[#E5E5E4]/80 hover:text-[#FAF9FA]'
          }`}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>Local LLM</span>
        </button>
        <button
          type="button"
          disabled={busy}
          aria-pressed={provider === 'api'}
          onClick={() => handleSwitchProvider('api')}
          className={`px-3 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${
            provider === 'api'
              ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
              : 'text-[#E5E5E4]/80 hover:text-[#FAF9FA]'
          }`}
        >
          <Cloud className="w-3.5 h-3.5" />
          <span>API LLM</span>
        </button>
      </div>

      {/* Provider-specific Model Picker */}
      {provider === 'api' && apiModels.length > 0 && (
        <select
          id={`api-model-select-${variant}`}
          name="groq_chat_model"
          value={activeModel}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={busy}
          aria-label="Select Groq API LLM model"
          className="rounded-full bg-[#0B0D1A] border border-white/15 px-3 py-1.5 text-xs text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none max-w-[260px]"
        >
          {apiModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      )}

      {provider === 'local' && localModels.length > 0 && (
        <select
          id={`local-model-select-${variant}`}
          name="ollama_chat_model"
          value={activeModel}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={busy}
          aria-label="Select local Ollama model"
          className="rounded-full bg-[#0B0D1A] border border-white/15 px-3 py-1.5 text-xs text-[#FAF9FA] focus:border-[#A5D8FF] focus:outline-none max-w-[220px]"
        >
          {localModels.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      )}

      {/* Enable / Pause Synthesis */}
      <button
        type="button"
        disabled={busy}
        onClick={handleToggleLLM}
        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
          llmEnabled && aiStatus?.llm_active
            ? 'bg-[#A5D8FF]/15 border-[#A5D8FF]/45 text-[#A5D8FF]'
            : 'bg-[#0B0D1A] border-white/15 text-[#E5E5E4]/85 hover:border-[#A5D8FF]/40'
        }`}
      >
        {llmEnabled ? 'LLM: On' : 'LLM: Paused'}
      </button>

      {/* Warm Up / Test Button */}
      {(provider === 'api' ? aiStatus?.api_available : aiStatus?.ollama_available) && (
        <button
          type="button"
          disabled={busy}
          onClick={handleWarmup}
          className="px-3 py-1.5 rounded-full bg-[#0B0D1A] border border-white/15 text-xs text-[#E5E5E4] hover:border-[#A5D8FF]/45 inline-flex items-center gap-1.5"
        >
          <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} />
          <span>{provider === 'api' ? 'Test API' : 'Warm Up'}</span>
        </button>
      )}

      {/* Live Status Pill */}
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#0B0D1A] border border-[#A5D8FF]/30 text-xs text-[#A5D8FF]">
        {provider === 'api' ? <Cloud className="w-3.5 h-3.5" /> : <Cpu className="w-3.5 h-3.5" />}
        <span>{statusLabel}</span>
      </div>

      {/* Optional Key Config Button in Panel Mode */}
      {variant === 'panel' && (
        <button
          type="button"
          onClick={() => setShowKeyForm((prev) => !prev)}
          className="px-3 py-1.5 rounded-full bg-[#0B0D1A] border border-white/15 text-xs text-[#E5E5E4]/85 hover:border-[#A5D8FF]/45 inline-flex items-center gap-1.5"
        >
          <KeyRound className="w-3 h-3 text-[#A5D8FF]" />
          <span>{showKeyForm ? 'Hide Key' : 'Groq Key'}</span>
        </button>
      )}

      {variant === 'panel' && showKeyForm && (
        <form onSubmit={handleSaveKey} className="w-full flex flex-wrap items-center gap-2 pt-2">
          <input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="Paste GROQ_API_KEY (stored locally on backend only)..."
            aria-label="Groq API key"
            className="flex-1 min-w-[220px] rounded-full bg-[#0B0D1A] border border-white/15 px-3.5 py-1.5 text-xs text-[#FAF9FA] placeholder:text-[#E5E5E4]/45 focus:border-[#A5D8FF] focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || keyInput.trim().length < 10}
            className="mc-btn-primary px-4 py-1.5 text-xs"
          >
            Save Groq Key
          </button>
          {aiStatus?.api_key_source === 'LOCAL_CONFIG' && (
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const next = await updateLocalAIConfig({ clear_groq_api_key: true }, onStateUpdated);
                  emitNotice(`Cleared custom key override (source: ${next.api_key_source}).`);
                } finally {
                  setBusy(false);
                }
              }}
              className="mc-btn-secondary px-3 py-1.5 text-xs"
            >
              Reset Override
            </button>
          )}
        </form>
      )}
    </div>
  );
};
