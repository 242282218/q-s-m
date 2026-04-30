const API_KEY_STORAGE_KEY = 'qsm_api_key';
const DEV_LOCAL_API_KEY = 'test-api-key-for-local-verification-only';

function isLocalDevelopment(): boolean {
  return (
    import.meta.env.DEV && ['127.0.0.1', 'localhost'].includes(globalThis.location?.hostname || '')
  );
}

function getLocalDevelopmentApiKey(): string | null {
  return isLocalDevelopment() ? DEV_LOCAL_API_KEY : null;
}

function normalizeApiKey(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function readStoredApiKey(): string | null {
  try {
    return normalizeApiKey(globalThis.localStorage?.getItem(API_KEY_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function setConfiguredApiKey(value: string | null | undefined): void {
  const normalized = normalizeApiKey(value);

  try {
    if (!normalized) {
      globalThis.localStorage?.removeItem(API_KEY_STORAGE_KEY);
      return;
    }

    globalThis.localStorage?.setItem(API_KEY_STORAGE_KEY, normalized);
  } catch {
    // Ignore storage failures and keep runtime behavior non-fatal.
  }
}

export function hasStoredApiKey(): boolean {
  return readStoredApiKey() !== null;
}

export function getConfiguredApiKey(): string | null {
  return (
    readStoredApiKey() ??
    getLocalDevelopmentApiKey() ??
    normalizeApiKey(import.meta.env.VITE_API_KEY)
  );
}

export function getApiKeyCandidates(explicitApiKey?: string | null): string[] {
  const candidates: string[] = [];

  for (const candidate of [
    readStoredApiKey(),
    normalizeApiKey(explicitApiKey),
    getLocalDevelopmentApiKey(),
    normalizeApiKey(import.meta.env.VITE_API_KEY),
  ]) {
    if (!candidate || candidates.includes(candidate)) {
      continue;
    }
    candidates.push(candidate);
  }

  return candidates;
}

export function withApiKeyHeader(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  if (merged.has('X-API-Key')) {
    return merged;
  }

  const apiKey = getConfiguredApiKey();

  if (apiKey) {
    merged.set('X-API-Key', apiKey);
  }

  return merged;
}
