export interface LocalRuntimeModelConfig {
  provider: 'gemini' | 'ollama';
  geminiApiKey?: string;
  ollamaEndpoint: string;
  ollamaModel: string;
}

export const LOCAL_RUNTIME_CONFIG_KEY = 'mirrorme_model_config';
export const MKULTRA_LOCAL_CONFIG: LocalRuntimeModelConfig = {
  provider: 'ollama',
  geminiApiKey: '',
  ollamaEndpoint: 'http://localhost:8765',
  ollamaModel: 'mkultra:0.3',
};

const LEGACY_LOCAL_MODELS = new Set(['mirrorme', 'llama3.1:8b']);
const LEGACY_LOCAL_ENDPOINTS = new Set([
  'http://localhost:8765',
  'http://127.0.0.1:8765',
  'http://localhost:11434',
  'http://127.0.0.1:11434',
]);

function isLegacyDefault(config: Partial<LocalRuntimeModelConfig>): boolean {
  const providerLooksLocal =
    config.provider === undefined ||
    config.provider === 'ollama' ||
    (config.provider === 'gemini' && !config.geminiApiKey);
  const endpoint = config.ollamaEndpoint?.replace(/\/$/, '');
  const endpointLooksDefault = !endpoint || LEGACY_LOCAL_ENDPOINTS.has(endpoint);
  const modelLooksDefault = !config.ollamaModel || LEGACY_LOCAL_MODELS.has(config.ollamaModel);

  return providerLooksLocal && endpointLooksDefault && modelLooksDefault;
}

/**
 * Seed or migrate only the repository's historical local defaults.
 * Explicit custom endpoints, models, and cloud selections are preserved.
 */
export function bootstrapLocalRuntimeConfig(): void {
  if (typeof window === 'undefined') return;

  try {
    const raw = window.localStorage.getItem(LOCAL_RUNTIME_CONFIG_KEY);
    if (!raw) {
      window.localStorage.setItem(LOCAL_RUNTIME_CONFIG_KEY, JSON.stringify(MKULTRA_LOCAL_CONFIG));
      return;
    }

    const parsed = JSON.parse(raw) as Partial<LocalRuntimeModelConfig>;
    if (isLegacyDefault(parsed)) {
      window.localStorage.setItem(LOCAL_RUNTIME_CONFIG_KEY, JSON.stringify(MKULTRA_LOCAL_CONFIG));
    }
  } catch {
    window.localStorage.setItem(LOCAL_RUNTIME_CONFIG_KEY, JSON.stringify(MKULTRA_LOCAL_CONFIG));
  }
}

const LOOPBACK_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/;

/**
 * Resolve the bridge URL for this page.
 *
 * The stored default points at localhost, which is only right on the computer that
 * runs the bridge. When the page itself was served over plain HTTP from another
 * address (for example a phone opening http://100.x.y.z:3000 over Tailscale), the
 * bridge is on that same machine, so a loopback setting is replaced with the page's
 * host. An explicitly configured non-loopback endpoint is always kept.
 */
export function resolveBridgeEndpoint(stored: string | undefined, location: Pick<Location, 'protocol' | 'hostname'>): string {
  const endpoint = (stored ?? '').trim().replace(/\/$/, '') || MKULTRA_LOCAL_CONFIG.ollamaEndpoint;
  let storedHost = '';
  try {
    storedHost = new URL(endpoint).hostname;
  } catch {
    return endpoint;
  }
  const pageIsRemoteHttp = location.protocol === 'http:' && !LOOPBACK_HOST.test(location.hostname);
  if (pageIsRemoteHttp && LOOPBACK_HOST.test(storedHost)) {
    const port = new URL(endpoint).port || '8765';
    return `http://${location.hostname}:${port}`;
  }
  return endpoint;
}
