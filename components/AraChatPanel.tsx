import React, { useRef, useState } from 'react';
import { Message, Role } from '../types';

const BRIDGE_URL = 'http://127.0.0.1:8765';
const MAX_MESSAGES = 20;
const MAX_MESSAGE_CHARS = 12_000;
const MAX_TOTAL_CHARS = 30_000;

type AraReply = {
  ok?: boolean;
  status?: string;
  answer?: string;
  provider?: string;
  model?: string;
  audit?: { response_hash?: string; persisted?: boolean };
  memory_written?: boolean;
  external_action_performed?: boolean;
  error?: string;
};

const AraChatPanel: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [lastStatus, setLastStatus] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const addNotice = (content: string, status: Message['status'] = 'sent') => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: Role.ASSISTANT,
      content,
      timestamp: new Date(),
      status,
    }]);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || busy) return;
    if (!consent) {
      setError('Consent is required before sending any conversation content to ARA.');
      return;
    }
    if (text.length > MAX_MESSAGE_CHARS) {
      setError(`Message too long: maximum ${MAX_MESSAGE_CHARS.toLocaleString()} characters.`);
      return;
    }

    const history = [...messages.filter(m => m.role === Role.USER || m.role === Role.ASSISTANT), {
      id: crypto.randomUUID(),
      role: Role.USER,
      content: text,
      timestamp: new Date(),
      status: 'sent' as const,
    }];
    if (history.length > MAX_MESSAGES) {
      setError(`Conversation limit reached (${MAX_MESSAGES} messages). Start a new ARA chat to continue.`);
      return;
    }
    const totalChars = history.reduce((sum, item) => sum + item.content.length, 0);
    if (totalChars > MAX_TOTAL_CHARS) {
      setError(`Conversation exceeds the ${MAX_TOTAL_CHARS.toLocaleString()} character limit. Start a new ARA chat.`);
      return;
    }

    setError('');
    setInput('');
    setBusy(true);
    setMessages(history.map(m => ({
      ...m,
      role: m.role as Role,
      status: m.status as Message['status'],
    })));
    setLastStatus('Sending to the configured ARA backend…');

    try {
      const response = await fetch(`${BRIDGE_URL}/api/ara/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          allow_ara: true,
          conversation_id: 'mirrorme-ara-ui',
          messages: history.map(m => ({
            role: m.role === Role.USER ? 'user' : 'assistant',
            content: m.content,
          })),
        }),
      });
      const result = await response.json().catch(() => ({} as AraReply)) as AraReply;
      if (!response.ok) {
        const knownErrors: Record<string, string> = {
          explicit_ara_consent_required: 'The backend rejected the request because consent was not supplied.',
          ara_provider_request_failed: 'ARA provider request failed. Check the local bridge and trusted provider configuration.',
          ara_chat_unavailable: 'ARA chat is unavailable in this bridge build.',
          ara_chat_requires_loopback_binding: 'ARA chat requires the bridge to bind to a loopback address.',
          invalid_json: 'The backend rejected the request as invalid JSON.',
          request_body_too_large: 'The request exceeded the bridge body-size limit.',
        };
        throw new Error(knownErrors[result.error || ''] || `ARA request failed (HTTP ${response.status}). Check the local bridge logs.`);
      }
      if (typeof result.answer !== 'string' || !result.answer) {
        throw new Error('ARA returned an invalid response shape.');
      }
      const hash = result.audit?.response_hash;
      addNotice(`${result.answer}\n\n[Status: ${result.status || 'completed_unverified'}; provider: ${result.provider || 'configured ARA'}; integrity hash: ${hash || 'not supplied'}; memory written: ${String(result.memory_written === true)}; external action: ${String(result.external_action_performed === true)}]\nModel output is not verified evidence.`);
      setLastStatus('Response received · completed_unverified');
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Unknown ARA request error.';
      setError(message);
      setLastStatus('Request failed');
      addNotice(`ARA request failed: ${message}`, 'failed');
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    }
  };

  return (
    <section className="h-full min-h-[520px] flex flex-col bg-slate-950 border border-cyan-900/40 rounded-xl overflow-hidden">
      <header className="p-4 border-b border-slate-800">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-black uppercase tracking-widest text-cyan-400">ARA · Dane Model</h3>
            <p className="text-xs text-slate-500 mt-1">Backend route · request-scoped · no memory writes</p>
          </div>
          <span className="text-[10px] uppercase tracking-wider text-amber-400 border border-amber-700/50 rounded px-2 py-1">Unverified output</span>
        </div>
        <label className="mt-4 flex items-start gap-2 text-xs text-slate-300 cursor-pointer">
          <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5 accent-cyan-500" />
          <span>I consent to sending this chat history to the ARA provider configured in the local backend. Do not include sensitive data unless appropriate.</span>
        </label>
      </header>

      <div ref={scrollRef} className="flex-1 min-h-[220px] overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-sm text-slate-500">Ask ARA to critique a hypothesis, identify assumptions, or propose falsification tests. Nothing is sent until you enable consent and submit a message.</p>
        )}
        {messages.map(m => (
          <div key={m.id} className={`max-w-[95%] rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap ${m.role === Role.USER ? 'ml-auto bg-slate-800 border-slate-700 text-slate-100' : 'bg-slate-900 border-slate-800 text-slate-300'}`}>
            <div>{m.content}</div>
            <div className={`mt-2 text-[9px] uppercase tracking-wider ${m.status === 'failed' ? 'text-rose-400' : 'text-slate-600'}`}>{m.role === Role.USER ? 'You' : 'ARA / system'} · {m.status}</div>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-800 p-4 space-y-3">
        {error && <p role="alert" className="text-xs text-rose-300 bg-rose-950/30 border border-rose-900/50 rounded p-2">{error}</p>}
        <p aria-live="polite" className="text-[10px] text-slate-500">{lastStatus} {input.length > 0 ? `· ${input.length.toLocaleString()} characters` : ''}</p>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend(); } }}
          placeholder="Ask ARA to challenge an assumption…"
          maxLength={MAX_MESSAGE_CHARS + 1}
          rows={3}
          disabled={busy}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-sm text-slate-100 resize-y focus:outline-none focus:border-cyan-500 disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] text-slate-600">Max 20 messages · 30,000 total characters · no durable history</p>
          <button onClick={() => void handleSend()} disabled={busy || !input.trim()} className="rounded-lg bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 px-4 py-2 text-xs font-bold text-white">
            {busy ? 'Sending…' : 'Send to ARA'}
          </button>
        </div>
      </div>
    </section>
  );
};

export default AraChatPanel;
