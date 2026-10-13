import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const MODEL_CONFIG_KEY = 'mirrorme_model_config';
const SELECTION_KEY = 'vireax_chat_selection';
const LOOPBACK_DEFAULT = 'http://localhost:8765';
const MAX_MODELS = 4;
const MAX_TASK_CHARS = 20_000;

interface Turn {
  round: number;
  model: string;
  role: string;
  output: string;
  output_sha256: string;
}

interface ConverseResult {
  ok: true;
  session_id: string;
  status: string;
  models: string[];
  max_rounds: number;
  audit_head_hash: string;
  turns: Turn[];
}

interface Exchange {
  id: string;
  task: string;
  startedAt: number;
  elapsedMs?: number;
  result?: ConverseResult;
  error?: string;
}

const readBridgeEndpoint = (): string => {
  try {
    const raw = window.localStorage.getItem(MODEL_CONFIG_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { ollamaEndpoint?: unknown };
      if (typeof parsed.ollamaEndpoint === 'string' && parsed.ollamaEndpoint.trim()) {
        return parsed.ollamaEndpoint.trim().replace(/\/$/, '');
      }
    }
  } catch {
    // Fall back to the loopback default.
  }
  return LOOPBACK_DEFAULT;
};

const readSelection = (): { models: string[]; rounds: number } | null => {
  try {
    const raw = window.localStorage.getItem(SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { models?: unknown; rounds?: unknown };
    const models = Array.isArray(parsed.models) ? parsed.models.filter((m): m is string => typeof m === 'string') : [];
    const rounds = typeof parsed.rounds === 'number' && parsed.rounds >= 1 && parsed.rounds <= 3 ? parsed.rounds : 2;
    return { models, rounds };
  } catch {
    return null;
  }
};

const shortHash = (value: string): string => (value.length > 22 ? `${value.slice(0, 14)}…${value.slice(-6)}` : value);

const isLocalOrigin = (origin: string): boolean => /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);

const bridgeCommand = (models: string[]): string => {
  const picks = models.length >= 2 ? models.slice(0, 2) : ['mkultra:0.3', 'mkultra:0.4'];
  const parts = ['python local_bridge/mirrorme_bridge.py', ...picks.map((m) => `--vireax-model ${m}`)];
  const origin = window.location.origin;
  if (!isLocalOrigin(origin)) parts.push(`--allowed-origin ${origin}`);
  return parts.join(' ');
};

const describeError = async (response: Response): Promise<string> => {
  try {
    const data = (await response.json()) as { error?: string; detail?: string; hint?: string };
    return [data.detail || data.error || `HTTP ${response.status}`, data.hint].filter(Boolean).join(' — ');
  } catch {
    return `HTTP ${response.status}`;
  }
};

const RoleBadge: React.FC<{ role: string }> = ({ role }) => {
  const independent = role === 'independent_analyst';
  return (
    <span
      className={`text-[10px] uppercase tracking-widest font-bold px-2 py-0.5 rounded-full border ${
        independent ? 'border-cyan-500/40 text-cyan-300 bg-cyan-500/10' : 'border-amber-500/40 text-amber-300 bg-amber-500/10'
      }`}
    >
      {independent ? 'Independent analysis' : 'Critical review'}
    </span>
  );
};

const ExchangeView: React.FC<{ exchange: Exchange; now: number }> = ({ exchange, now }) => {
  const rounds = useMemo(() => {
    const grouped = new Map<number, Turn[]>();
    for (const turn of exchange.result?.turns ?? []) {
      grouped.set(turn.round, [...(grouped.get(turn.round) ?? []), turn]);
    }
    return [...grouped.entries()].sort(([a], [b]) => a - b);
  }, [exchange.result]);

  const pending = !exchange.result && !exchange.error;
  const seconds = Math.round(((exchange.elapsedMs ?? now - exchange.startedAt) as number) / 1000);

  return (
    <article className="space-y-4">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-cyan-600/20 border border-cyan-500/30 px-4 py-3 text-sm text-slate-100 whitespace-pre-wrap break-words">
          {exchange.task}
        </div>
      </div>

      {pending && (
        <div className="flex items-center gap-3 text-sm text-slate-400" role="status">
          <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          Models are working… {seconds}s
        </div>
      )}

      {exchange.error && (
        <div className="border border-rose-500/30 bg-rose-500/10 text-rose-300 rounded-xl p-4 text-sm break-words">
          {exchange.error}
        </div>
      )}

      {rounds.map(([round, turns]) => (
        <section key={round} className="space-y-3">
          <p className="text-[11px] uppercase tracking-[0.25em] text-slate-500 font-bold">
            Round {round} · {round === 1 ? 'each model answers alone' : 'each model reviews earlier rounds'}
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {turns.map((turn) => (
              <div key={`${turn.round}-${turn.model}`} className="bg-slate-900 border border-slate-800 rounded-2xl p-4 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <span className="font-mono text-sm font-bold text-slate-100 break-all">{turn.model}</span>
                  <RoleBadge role={turn.role} />
                </div>
                <div className="text-sm text-slate-300 whitespace-pre-wrap break-words leading-relaxed">{turn.output}</div>
                <p className="mt-3 font-mono text-[10px] text-slate-600" title={turn.output_sha256}>
                  {shortHash(turn.output_sha256)}
                </p>
              </div>
            ))}
          </div>
        </section>
      ))}

      {exchange.result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 border-t border-slate-800 pt-3">
          <span className="text-amber-300/80 font-bold uppercase tracking-widest">{exchange.result.status}</span>
          <span>Model agreement is not verification.</span>
          <span className="font-mono" title={exchange.result.audit_head_hash}>
            audit {shortHash(exchange.result.audit_head_hash)}
          </span>
          {exchange.elapsedMs !== undefined && <span>{Math.round(exchange.elapsedMs / 1000)}s</span>}
        </div>
      )}
    </article>
  );
};

const Vireax: React.FC = () => {
  const [endpoint] = useState(readBridgeEndpoint);
  const [installed, setInstalled] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(() => readSelection()?.models ?? []);
  const [rounds, setRounds] = useState<number>(() => readSelection()?.rounds ?? 2);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [draft, setDraft] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = exchanges.some((e) => !e.result && !e.error);

  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const response = await fetch(`${endpoint}/api/vireax/models`);
      if (!response.ok) throw new Error(await describeError(response));
      const data = (await response.json()) as { models: string[]; default_models: string[] };
      setInstalled(data.models);
      setSelected((current) => {
        const kept = current.filter((m) => data.models.includes(m));
        if (kept.length >= 2) return kept;
        const defaults = data.default_models.filter((m) => data.models.includes(m));
        return (defaults.length >= 2 ? defaults : data.models).slice(0, 2);
      });
      setBridgeError(null);
    } catch (error) {
      setInstalled([]);
      setBridgeError(error instanceof TypeError ? 'bridge_unreachable' : (error as Error).message);
    } finally {
      setLoadingModels(false);
    }
  }, [endpoint]);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  useEffect(() => {
    try {
      window.localStorage.setItem(SELECTION_KEY, JSON.stringify({ models: selected, rounds }));
    } catch {
      // Storage is a convenience only.
    }
  }, [selected, rounds]);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [exchanges]);

  const toggleModel = (model: string) => {
    setSelected((current) =>
      current.includes(model)
        ? current.filter((m) => m !== model)
        : current.length >= MAX_MODELS
          ? current
          : [...current, model],
    );
  };

  const send = async () => {
    const task = draft.trim();
    if (!task || busy || selected.length < 2) return;
    const id = `${Date.now()}`;
    const startedAt = Date.now();
    setExchanges((list) => [...list, { id, task, startedAt }]);
    setDraft('');
    const finish = (patch: Partial<Exchange>) =>
      setExchanges((list) => list.map((e) => (e.id === id ? { ...e, ...patch, elapsedMs: Date.now() - startedAt } : e)));
    try {
      const response = await fetch(`${endpoint}/api/vireax/converse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, models: selected, max_rounds: rounds }),
      });
      if (!response.ok) {
        finish({ error: await describeError(response) });
        return;
      }
      finish({ result: (await response.json()) as ConverseResult });
    } catch {
      finish({ error: `Could not reach the local bridge at ${endpoint}. Is it running?` });
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void send();
    }
  };

  const canSend = !busy && selected.length >= 2 && draft.trim().length > 0 && draft.length <= MAX_TASK_CHARS;
  const sendHint =
    selected.length < 2 ? 'Pick at least two models' : busy ? 'Waiting for the models…' : 'Ctrl/⌘ + Enter to send';

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto flex flex-col gap-5 min-h-full">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-cyan-500 font-bold">Bounded multi-model review</p>
          <h2 className="text-2xl sm:text-3xl font-black text-slate-100 mt-2">VIREAX Chat</h2>
          <p className="text-sm text-slate-400 mt-2 max-w-3xl">
            Ask once. Each model answers alone, then reviews the others. Runs on your own machine through the local bridge;
            nothing is sent to cloud models. Each question is a fresh session.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadModels()}
          disabled={loadingModels}
          className="self-start sm:self-auto px-4 py-2 rounded-lg border border-cyan-500/30 text-cyan-400 text-xs font-bold hover:bg-cyan-500/10 disabled:opacity-40"
        >
          {loadingModels ? 'Checking…' : 'Reconnect'}
        </button>
      </header>

      {bridgeError ? (
        <div className="border border-amber-500/30 bg-amber-500/10 rounded-xl p-4 text-sm text-amber-200 space-y-2">
          <p>
            {bridgeError === 'bridge_unreachable'
              ? `The local bridge isn't reachable at ${endpoint}. Start it on this computer, then press Reconnect:`
              : bridgeError}
          </p>
          <code className="block bg-slate-950/60 rounded-lg p-3 font-mono text-xs text-slate-200 break-all">
            {bridgeCommand(selected)}
          </code>
          {!isLocalOrigin(window.location.origin) && (
            <p className="text-xs text-amber-200/70">
              Using the hosted site needs Chrome, Edge or Firefox; Safari blocks HTTPS pages from calling localhost.
            </p>
          )}
        </div>
      ) : (
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-widest text-slate-500 font-bold mr-1">Models</span>
            {installed.length === 0 && !loadingModels && (
              <span className="text-sm text-slate-400">No Ollama models found. Pull some with `ollama pull`.</span>
            )}
            {installed.map((model) => {
              const on = selected.includes(model);
              return (
                <button
                  key={model}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleModel(model)}
                  disabled={busy || (!on && selected.length >= MAX_MODELS)}
                  className={`px-3 py-1.5 rounded-full border font-mono text-xs transition-colors disabled:opacity-40 ${
                    on
                      ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200'
                      : 'border-slate-700 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {model}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-widest text-slate-500 font-bold mr-1">Rounds</span>
            {[1, 2, 3].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={rounds === n}
                onClick={() => setRounds(n)}
                disabled={busy}
                className={`w-9 h-8 rounded-lg border text-xs font-bold disabled:opacity-40 ${
                  rounds === n ? 'border-cyan-400 bg-cyan-500/15 text-cyan-200' : 'border-slate-700 text-slate-400'
                }`}
              >
                {n}
              </button>
            ))}
            <span className="text-xs text-slate-500 ml-1">
              {selected.length} models × {rounds} rounds = {selected.length * rounds} calls
            </span>
          </div>
        </section>
      )}

      <div className="flex-1 space-y-8">
        {exchanges.length === 0 && !bridgeError && (
          <p className="text-sm text-slate-500 text-center py-10">Ask VIREAX a question to start.</p>
        )}
        {exchanges.map((exchange) => (
          <ExchangeView key={exchange.id} exchange={exchange} now={now} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="sticky bottom-0 bg-slate-950/90 backdrop-blur pt-2 pb-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <div className="flex gap-2 items-end">
          <label htmlFor="vireax-task" className="sr-only">
            Question for VIREAX
          </label>
          <textarea
            id="vireax-task"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            rows={3}
            maxLength={MAX_TASK_CHARS}
            placeholder="Ask VIREAX…"
            className="flex-1 resize-y min-h-[3.5rem] max-h-64 rounded-xl bg-slate-900 border border-slate-700 focus:border-cyan-500 focus:outline-none px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600"
          />
          <button
            type="submit"
            disabled={!canSend}
            className="px-5 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-bold disabled:opacity-40 disabled:hover:bg-cyan-600"
          >
            Send
          </button>
        </div>
        <p className="text-[11px] text-slate-500 mt-1.5">{sendHint}</p>
      </form>
    </div>
  );
};

export default Vireax;
