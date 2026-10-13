import React, { useEffect, useState } from 'react';

type Provider = 'gemini' | 'ollama';

interface ModelConfig {
  provider: Provider;
  geminiApiKey: string;
  ollamaEndpoint: string;
  ollamaModel: string;
}

const MODEL_CONFIG_KEY = 'mirrorme_model_config';
const HANDSHAKE_SESSION_KEY = 'mirrorme_handshake_session_id';
const MEMORY_APPROVAL_KEY = 'mirrorme_memory_policy_approved';

type HandshakeState = 'NO_SESSION' | 'CHALLENGE_ISSUED' | 'VERIFIED_LOCAL_SESSION' | 'EXPIRED' | 'ERROR';

interface HandshakeChallenge {
  session_id: string;
  nonce: string;
  expires_at_unix: number;
}

interface HandshakeStatus {
  state: HandshakeState;
  message: string;
}

const DEFAULT_BRIDGE_ENDPOINT = 'http://localhost:8765';
const DEFAULT_OLLAMA_MODEL = 'mirrorme:latest';

const DEFAULT_CONFIG: ModelConfig = {
  provider: 'ollama',
  geminiApiKey: '',
  ollamaEndpoint: DEFAULT_BRIDGE_ENDPOINT,
  ollamaModel: DEFAULT_OLLAMA_MODEL,
};

function normalizeStoredConfig(parsed: Partial<ModelConfig>): ModelConfig {
  const normalized: ModelConfig = {
    provider: parsed.provider === 'gemini' ? 'gemini' : 'ollama',
    geminiApiKey: parsed.geminiApiKey ?? '',
    ollamaEndpoint: parsed.ollamaEndpoint?.trim() || DEFAULT_BRIDGE_ENDPOINT,
    ollamaModel: parsed.ollamaModel?.trim() || DEFAULT_OLLAMA_MODEL,
  };

  if (
    normalized.provider === 'ollama' &&
    normalized.ollamaEndpoint === 'http://localhost:11434' &&
    normalized.ollamaModel === 'llama3.1:8b'
  ) {
    return DEFAULT_CONFIG;
  }

  return normalized;
}

const Settings: React.FC = () => {
  const [config, setConfig] = useState<ModelConfig>(DEFAULT_CONFIG);
  const [savedAt, setSavedAt] = useState<string>('');
  const [challenge, setChallenge] = useState<HandshakeChallenge | null>(null);
  const [handshake, setHandshake] = useState<HandshakeStatus>({
    state: 'NO_SESSION',
    message: 'No local session has been confirmed.',
  });
  const [memoryApproved, setMemoryApproved] = useState<boolean>(
    () => typeof window !== 'undefined' && window.localStorage.getItem(MEMORY_APPROVAL_KEY) === 'true'
  );

  const bridgeBase = config.ollamaEndpoint.replace(/\/$/, '') || DEFAULT_BRIDGE_ENDPOINT;

  const updateHandshakeStatus = (state: HandshakeState, message: string) => {
    setHandshake({ state, message });
  };

  const fetchHandshakeStatus = async (sessionId: string): Promise<void> => {
    try {
      const response = await fetch(`${bridgeBase}/api/handshake/status?session_id=${encodeURIComponent(sessionId)}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'handshake_status_failed');
      }
      const session = data.session;
      if (session?.state === 'VERIFIED_LOCAL_SESSION') {
        updateHandshakeStatus('VERIFIED_LOCAL_SESSION', 'Local session confirmed through the bridge.');
      } else if (session?.state === 'CHALLENGE_ISSUED') {
        updateHandshakeStatus('CHALLENGE_ISSUED', 'Challenge issued. Confirm the session to complete handshake.');
      } else if (session?.state === 'EXPIRED') {
        updateHandshakeStatus('EXPIRED', 'The handshake challenge expired. Request a new one.');
      } else {
        updateHandshakeStatus('ERROR', 'Unexpected handshake status returned by the bridge.');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      updateHandshakeStatus('ERROR', `Handshake status check failed: ${message}`);
      window.localStorage.removeItem(HANDSHAKE_SESSION_KEY);
      setChallenge(null);
    }
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;

    try {
      const rawConfig = window.localStorage.getItem(MODEL_CONFIG_KEY);
      if (rawConfig) {
        const parsed = JSON.parse(rawConfig) as Partial<ModelConfig>;
        setConfig(normalizeStoredConfig(parsed));
      }
    } catch {
      window.localStorage.removeItem(MODEL_CONFIG_KEY);
    }

    const storedSessionId = window.localStorage.getItem(HANDSHAKE_SESSION_KEY);
    if (storedSessionId) {
      void fetchHandshakeStatus(storedSessionId);
    }
  }, []);

  const saveConfig = () => {
    window.localStorage.setItem(MODEL_CONFIG_KEY, JSON.stringify(config));
    setSavedAt(new Date().toLocaleTimeString());
  };

  const useLocalDefaults = () => {
    setConfig(DEFAULT_CONFIG);
    window.localStorage.setItem(MODEL_CONFIG_KEY, JSON.stringify(DEFAULT_CONFIG));
    setSavedAt(new Date().toLocaleTimeString());
  };

  const startHandshake = async () => {
    updateHandshakeStatus('NO_SESSION', 'Requesting handshake challenge from local bridge...');
    try {
      const response = await fetch(`${bridgeBase}/api/handshake/challenge`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'handshake_challenge_failed');
      }
      setChallenge({
        session_id: data.session_id,
        nonce: data.nonce,
        expires_at_unix: data.expires_at_unix,
      });
      updateHandshakeStatus('CHALLENGE_ISSUED', 'Challenge issued. Confirm the local session to finish the handshake.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      updateHandshakeStatus('ERROR', `Handshake challenge failed: ${message}`);
      setChallenge(null);
    }
  };

  const verifyHandshake = async () => {
    if (!challenge) return;

    updateHandshakeStatus('CHALLENGE_ISSUED', 'Verifying handshake with local bridge...');
    try {
      const response = await fetch(`${bridgeBase}/api/handshake/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: challenge.session_id,
          nonce: challenge.nonce,
          operator: 'Local Operator',
          confirmation_phrase: 'CONFIRM_LOCAL_MIRRORME',
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'handshake_verify_failed');
      }
      window.localStorage.setItem(HANDSHAKE_SESSION_KEY, data.session_id);
      updateHandshakeStatus('VERIFIED_LOCAL_SESSION', 'Local session verified. You may now enable memory approval.');
      setChallenge(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      updateHandshakeStatus('ERROR', `Handshake verification failed: ${message}`);
    }
  };

  const updateMemoryApproval = (approved: boolean) => {
    setMemoryApproved(approved);
    window.localStorage.setItem(MEMORY_APPROVAL_KEY, approved ? 'true' : 'false');
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h2 className="text-3xl font-bold text-slate-100 mb-2">Engine Configuration</h2>
      <p className="text-slate-400 mb-8">Configure the local MirrorME runtime and simulation parameters.</p>

      <div className="space-y-6">
        <section className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4">Inference Model</h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-400">Provider</label>
              <select
                value={config.provider}
                onChange={(e) => setConfig(prev => ({ ...prev, provider: e.target.value as Provider }))}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              >
                <option value="ollama">Ollama (Local, no API charge)</option>
                <option value="gemini">Gemini (Cloud)</option>
              </select>
            </div>

            {config.provider === 'gemini' && (
              <div className="space-y-2">
                <label className="text-xs font-medium text-slate-400">Gemini API Key (optional override)</label>
                <input
                  type="password"
                  value={config.geminiApiKey}
                  onChange={(e) => setConfig(prev => ({ ...prev, geminiApiKey: e.target.value }))}
                  placeholder="AIza..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
                />
              </div>
            )}

            {config.provider === 'ollama' && (
              <>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-400">MirrorME Bridge Endpoint</label>
                  <input
                    type="text"
                    value={config.ollamaEndpoint}
                    onChange={(e) => setConfig(prev => ({ ...prev, ollamaEndpoint: e.target.value }))}
                    placeholder="http://localhost:8765"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-400">Ollama Model</label>
                  <input
                    type="text"
                    value={config.ollamaModel}
                    onChange={(e) => setConfig(prev => ({ ...prev, ollamaModel: e.target.value }))}
                    placeholder="llama3.1:8b"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </>
            )}
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={saveConfig}
              className="px-4 py-2 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-bold hover:bg-cyan-500/20 transition-all uppercase"
            >
              Save Model Config
            </button>
            <button
              type="button"
              onClick={useLocalDefaults}
              className="px-4 py-2 border border-slate-700 rounded-lg text-xs font-bold text-slate-300 hover:bg-slate-800 transition-all uppercase"
            >
              Use Local MirrorME Defaults
            </button>
            {savedAt && <span className="text-[11px] text-slate-500">Saved at {savedAt}</span>}
          </div>

          <p className="text-xs text-slate-500 mt-4">
            Default route: browser UI → localhost:8765 bridge → localhost:11434 Ollama → mirrorme.
          </p>
        </section>

        <section className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4">Local Session Handshake</h3>
          <p className="text-xs text-slate-400 mb-4">
            Confirms a temporary session with the local bridge. It does not prove identity, account ownership, or consciousness.
          </p>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="px-2 py-1 rounded border border-cyan-500/30 text-cyan-400 text-[10px] font-bold">
                {handshake.state}
              </span>
              <span className="text-xs text-slate-400">{handshake.message}</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="button" onClick={startHandshake} className="px-4 py-2 border border-slate-700 rounded-lg text-xs font-bold text-slate-300 hover:bg-slate-800">
                Request Challenge
              </button>
              <button type="button" disabled={!challenge} onClick={verifyHandshake} className="px-4 py-2 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-bold disabled:opacity-40">
                Confirm Local Session
              </button>
            </div>
          </div>
          <label className="mt-4 flex items-start gap-3 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={memoryApproved}
              disabled={handshake.state !== 'VERIFIED_LOCAL_SESSION'}
              onChange={(event) => updateMemoryApproval(event.target.checked)}
              className="mt-0.5"
            />
            <span>
              I explicitly approve future local persistent-memory features under a documented retention and deletion policy.
              No memory storage is enabled by this checkbox alone.
            </span>
          </label>
        </section>

        <section className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4">Neural Parameters</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-400">Gamma-Sync Threshold</label>
              <input type="range" className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-500" />
              <div className="flex justify-between text-[10px] text-slate-600 font-bold uppercase">
                <span>Low Chaos</span>
                <span>High Coherence</span>
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-400">Psi-Snap Frequency (Hz)</label>
              <input type="number" defaultValue={60} className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500" />
            </div>
          </div>
        </section>

        <section className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
          <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest mb-4">Storage Layer</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-slate-950 rounded-xl border border-slate-800">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-500">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 1.105 2.239 2 5 2s5-.895 5-2V7M4 7c0 1.105 2.239 2 5 2s5-.895 5-2M4 7c0-1.105 2.239-2 5-2s5 .895 5 2m0 5c0 1.105-2.239 2-5 2s-5-.895-5-2" /></svg>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-200">Postgres Connector</h4>
                  <p className="text-xs text-slate-500">Truth-layer for relational cognitive artifacts.</p>
                </div>
              </div>
              <span className="px-2 py-1 bg-green-500/10 text-green-500 text-[10px] font-bold rounded border border-green-500/20">CONNECTED</span>
            </div>
            <div className="flex items-center justify-between p-4 bg-slate-950 rounded-xl border border-slate-800 opacity-60">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center text-orange-500">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-200">S3 / MinIO Object Store</h4>
                  <p className="text-xs text-slate-500">Blob storage for frame arrays and videos.</p>
                </div>
              </div>
              <span className="px-2 py-1 bg-slate-800 text-slate-500 text-[10px] font-bold rounded border border-slate-700 uppercase">Disabled</span>
            </div>
          </div>
        </section>

        <section className="bg-red-500/5 border border-red-500/20 p-6 rounded-2xl">
          <h3 className="text-sm font-bold text-red-400 uppercase tracking-widest mb-4">Danger Zone</h3>
          <p className="text-xs text-slate-500 mb-4">These actions are irreversible and will wipe truth-layer data.</p>
          <div className="flex gap-4">
            <button className="px-4 py-2 bg-red-500/10 text-red-500 border border-red-500/20 rounded-lg text-xs font-bold hover:bg-red-500/20 transition-all uppercase">
              Purge Simulation Cache
            </button>
            <button className="px-4 py-2 border border-slate-700 rounded-lg text-xs font-bold text-slate-400 hover:bg-slate-800 transition-all uppercase">
              Reset Workspace
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

export default Settings;

