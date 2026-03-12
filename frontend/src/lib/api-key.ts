const API_KEY_STORAGE_KEY = 'qsm_api_key';

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

export function getConfiguredApiKey(): string | null {
  return readStoredApiKey() ?? normalizeApiKey(import.meta.env.VITE_API_KEY);
}

export function withApiKeyHeader(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  const apiKey = getConfiguredApiKey();

  if (apiKey) {
    merged.set('X-API-Key', apiKey);
  }

  return merged;
}
