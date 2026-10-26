import React, { useMemo, useState } from 'react';

type EvidenceClass = 'observation' | 'inference' | 'hypothesis' | 'simulation' | 'unknown' | 'contradicted';

interface LedgerEntry {
  sequence: number;
  eventId: string;
  source: string;
  classification: EvidenceClass;
  confidence: number;
  timestamp: string;
  contentDigest: string;
  beforeDigest: string | null;
  afterDigest: string;
  previousEntryDigest: string;
  entryDigest: string;
}

const GENESIS = 'GENESIS';
const encoder = new TextEncoder();
const hex = (bytes: ArrayBuffer) => Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
const digest = async (value: string) => `sha256:${hex(await crypto.subtle.digest('SHA-256', encoder.encode(value)))}`;
const canonical = (value: unknown) => JSON.stringify(value, Object.keys(value as object).sort());

async function hashObject(value: Record<string, unknown>): Promise<string> {
  // This object is flat, so sorting its top-level keys produces a stable representation.
  const stable = Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)));
  return digest(JSON.stringify(stable));
}

const evidenceClasses: EvidenceClass[] = ['observation', 'inference', 'hypothesis', 'simulation', 'unknown', 'contradicted'];

const badgeClass: Record<EvidenceClass, string> = {
  observation: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200',
  inference: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
  hypothesis: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  simulation: 'border-violet-500/30 bg-violet-500/10 text-violet-200',
  unknown: 'border-slate-600 bg-slate-800 text-slate-300',
  contradicted: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
};

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <label className="block space-y-1.5">
    <span className="text-[11px] uppercase tracking-widest font-bold text-slate-400">{label}</span>
    {children}
  </label>
);

const VireaxContinuum: React.FC = () => {
  const [eventId, setEventId] = useState('');
  const [source, setSource] = useState('operator');
  const [classification, setClassification] = useState<EvidenceClass>('observation');
  const [confidence, setConfidence] = useState(0.7);
  const [content, setContent] = useState('');
  const [beforeState, setBeforeState] = useState('');
  const [afterState, setAfterState] = useState('');
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [verified, setVerified] = useState<boolean | null>(null);

  const lastState = entries.length ? entries[entries.length - 1].afterDigest : null;
  const duplicateId = entries.some((entry) => entry.eventId === eventId.trim());
  const canAppend = !!eventId.trim() && !!source.trim() && !!content.trim() && !!afterState.trim()
    && !duplicateId && !busy && (entries.length > 0 ? beforeState.trim() === lastState : !beforeState.trim());

  const summary = useMemo(() => ({
    total: entries.length,
    observations: entries.filter((entry) => entry.classification === 'observation').length,
    inferences: entries.filter((entry) => entry.classification === 'inference').length,
    hypotheses: entries.filter((entry) => entry.classification === 'hypothesis').length,
  }), [entries]);

  const append = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canAppend) return;
    setBusy(true);
    setNotice('');
    try {
      const beforeDigest = beforeState.trim() ? await digest(beforeState.trim()) : null;
      const afterDigest = await digest(afterState.trim());
      const contentDigest = await digest(content);
      const previousEntryDigest = entries.length ? entries[entries.length - 1].entryDigest : GENESIS;
      const timestamp = new Date().toISOString();
      const sequence = entries.length;
      const payload = {
        sequence, eventId: eventId.trim(), source: source.trim(), classification, confidence,
        timestamp, contentDigest, beforeDigest, afterDigest, previousEntryDigest,
      };
      const entryDigest = await hashObject(payload as unknown as Record<string, unknown>);
      setEntries((current) => [...current, { ...payload, afterDigest, beforeDigest, contentDigest, previousEntryDigest, entryDigest }]);
      setEventId('');
      setContent('');
      setBeforeState(afterState);
      setNotice('Entry added to this session. No persistent memory was written.');
      setVerified(null);
    } catch {
      setNotice('Web Crypto is unavailable in this context. Use a secure browser context and try again.');
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      let previousEntryDigest = GENESIS;
      let previousStateDigest: string | null = null;
      let valid = true;
      for (let index = 0; index < entries.length; index += 1) {
        const entry = entries[index];
        if (entry.sequence !== index || entry.previousEntryDigest !== previousEntryDigest || entry.beforeDigest !== previousStateDigest) {
          valid = false;
          break;
        }
        const payload = {
          sequence: entry.sequence, eventId: entry.eventId, source: entry.source,
          classification: entry.classification, confidence: entry.confidence, timestamp: entry.timestamp,
          contentDigest: entry.contentDigest, beforeDigest: entry.beforeDigest, afterDigest: entry.afterDigest,
          previousEntryDigest: entry.previousEntryDigest,
        };
        if (await hashObject(payload as unknown as Record<string, unknown>) !== entry.entryDigest) {
          valid = false;
          break;
        }
        previousEntryDigest = entry.entryDigest;
        previousStateDigest = entry.afterDigest;
      }
      setVerified(valid);
      setNotice(valid
        ? 'Integrity check passed for the entries currently held in this browser session. This does not prove truth or authorship.'
        : 'Integrity check failed: a chain or state link does not match.');
    } catch {
      setVerified(false);
      setNotice('Integrity verification failed because Web Crypto is unavailable.');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    if (!window.confirm('Clear the in-memory continuum ledger for this session? This cannot be undone.')) return;
    setEntries([]);
    setBeforeState('');
    setAfterState('');
    setVerified(null);
    setNotice('Session ledger cleared. No persistent memory was written.');
  };

  const inputClass = 'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none';
  const short = (value: string) => value === GENESIS ? GENESIS : `${value.slice(0, 15)}…${value.slice(-8)}`;

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 md:p-7">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.24em] text-cyan-400">VIREÁX / Observer Lab</div>
          <h1 className="mt-2 text-2xl font-semibold text-white md:text-3xl">Continuum Observer</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            Track state transitions with provenance, explicit evidence labels, and a verifiable hash chain.
            This is a local session tool—not a consciousness detector.
          </p>
        </div>
        <span className="w-fit rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-200">
          Session only · not persisted
        </span>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ['Entries', summary.total.toString()],
          ['Observations', summary.observations.toString()],
          ['Inferences', summary.inferences.toString()],
          ['Hypotheses', summary.hypotheses.toString()],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
          </div>
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <form onSubmit={append} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-5">
          <div>
            <h2 className="text-base font-semibold text-white">Record a transition</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">Only content digests are stored in the ledger; state text remains in these form fields until you clear or leave the page.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Event ID">
              <input className={inputClass} value={eventId} onChange={(e) => setEventId(e.target.value)} maxLength={120} placeholder="event-001" required />
            </Field>
            <Field label="Source">
              <input className={inputClass} value={source} onChange={(e) => setSource(e.target.value)} maxLength={120} required />
            </Field>
          </div>
          <Field label="Evidence classification">
            <select className={inputClass} value={classification} onChange={(e) => setClassification(e.target.value as EvidenceClass)}>
              {evidenceClasses.map((item) => <option key={item} value={item}>{item.toUpperCase()}</option>)}
            </select>
          </Field>
          <Field label={`Confidence · ${Math.round(confidence * 100)}% (recorded self-assessment)`}>
            <input type="range" min="0" max="1" step="0.05" value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} className="w-full accent-cyan-400" />
          </Field>
          <Field label="Event / claim content">
            <textarea className={inputClass} value={content} onChange={(e) => setContent(e.target.value)} rows={3} maxLength={5000} placeholder="What was observed or inferred?" required />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={entries.length ? 'Previous state (must match)' : 'Initial state (leave blank)'}>
              <input className={inputClass} value={beforeState} onChange={(e) => setBeforeState(e.target.value)} maxLength={2000} placeholder={entries.length ? 'Previous state representation' : 'No prior state'} />
            </Field>
            <Field label="Next state">
              <input className={inputClass} value={afterState} onChange={(e) => setAfterState(e.target.value)} maxLength={2000} placeholder="New state representation" required />
            </Field>
          </div>
          {duplicateId && <p className="text-xs text-rose-300">This event ID is already used in this session.</p>}
          {entries.length > 0 && beforeState.trim() !== lastState && <p className="text-xs text-amber-200">State continuity check: previous state must exactly match the last recorded state.</p>}
          {entries.length === 0 && beforeState.trim() && <p className="text-xs text-amber-200">The first entry must have no previous state.</p>}
          <button type="submit" disabled={!canAppend} className="w-full rounded-lg bg-cyan-500 px-4 py-3 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40">
            {busy ? 'Processing…' : 'Hash and record transition'}
          </button>
          <p className="text-[11px] leading-5 text-slate-500">Uses browser SHA-256. The chain is held in memory and will be lost on reload. No network call is made by this page.</p>
        </form>

        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-5">
            <div>
              <h2 className="font-semibold text-white">Continuity ledger</h2>
              <p className="mt-1 text-xs text-slate-500">Each entry links to its predecessor and the previous state digest.</p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => void verify()} disabled={busy || entries.length === 0} className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 hover:border-cyan-500 disabled:opacity-40">Verify chain</button>
              <button type="button" onClick={reset} disabled={busy || entries.length === 0} className="rounded-lg border border-rose-500/30 px-3 py-2 text-xs font-bold text-rose-200 hover:bg-rose-500/10 disabled:opacity-40">Clear</button>
            </div>
          </div>

          {verified !== null && <div role="status" className={`rounded-xl border p-3 text-sm ${verified ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200' : 'border-rose-500/30 bg-rose-500/10 text-rose-200'}`}>{verified ? 'Integrity check passed' : 'Integrity check failed'}</div>}
          {notice && <p role="status" className="text-xs leading-5 text-slate-400">{notice}</p>}

          {entries.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-700 p-10 text-center">
              <div className="text-2xl text-slate-600">⟡</div>
              <p className="mt-3 text-sm font-semibold text-slate-300">No transitions recorded</p>
              <p className="mt-1 text-xs text-slate-500">Add a first event to initialise the chain.</p>
            </div>
          ) : (
            <ol className="space-y-3">
              {[...entries].reverse().map((entry) => (
                <li key={entry.eventId} className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-400">#{String(entry.sequence + 1).padStart(3, '0')}</span>
                      <span className="font-semibold text-white">{entry.eventId}</span>
                    </div>
                    <span className={`rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${badgeClass[entry.classification]}`}>{entry.classification}</span>
                  </div>
                  <p className="mt-3 break-words text-sm text-slate-300">{entry.source} · confidence {Math.round(entry.confidence * 100)}%</p>
                  <div className="mt-3 grid gap-2 text-[10px] text-slate-500 sm:grid-cols-2">
                    <div><span className="text-slate-400">State</span><div className="mt-1 break-all font-mono">{short(entry.beforeDigest ?? GENESIS)} → {short(entry.afterDigest)}</div></div>
                    <div><span className="text-slate-400">Entry hash</span><div className="mt-1 break-all font-mono">{short(entry.entryDigest)}</div></div>
                  </div>
                  <time className="mt-3 block text-[10px] text-slate-600">{entry.timestamp}</time>
                </li>
              ))}
            </ol>
          )}

          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
            <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">Interpretation boundary</h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              A valid hash chain shows internal consistency of this session's recorded sequence. It cannot prove the claims are true,
              the source is authentic, the state encoding is meaningful, or that an AI experiences continuity or consciousness.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
};

export default VireaxContinuum;
