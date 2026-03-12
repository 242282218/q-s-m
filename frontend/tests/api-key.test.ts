import { describe, expect, it } from 'vitest';

import {
  getApiKeyCandidates,
  getConfiguredApiKey,
  setConfiguredApiKey,
  withApiKeyHeader,
} from '../src/shared/lib/api-key';

function createStorage() {
  const store = new Map<string, string>();

  return {
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    get length() {
      return store.size;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
  };
}

function withFreshLocalStorage<T>(callback: () => T) {
  const originalLocalStorage = globalThis.localStorage;

  Object.defineProperty(globalThis, 'localStorage', {
    value: createStorage(),
    configurable: true,
    writable: true,
  });

  try {
    return callback();
  } finally {
    if (originalLocalStorage === undefined) {
      delete (globalThis as { localStorage?: Storage }).localStorage;
    } else {
      Object.defineProperty(globalThis, 'localStorage', {
        value: originalLocalStorage,
        configurable: true,
        writable: true,
      });
    }
  }
}

describe('api-key helpers', () => {
  it('preserves a manually provided header', () => {
    withFreshLocalStorage(() => {
      globalThis.localStorage.setItem('qsm_api_key', 'stored-key');
      const headers = withApiKeyHeader({ 'X-API-Key': 'manual-key' });
      expect(headers.get('X-API-Key')).toBe('manual-key');
    });
  });

  it('stores and reads the configured api key', () => {
    withFreshLocalStorage(() => {
      setConfiguredApiKey('fresh-key');
      expect(globalThis.localStorage.getItem('qsm_api_key')).toBe('fresh-key');
      expect(getConfiguredApiKey()).toBe('fresh-key');
    });
  });

  it('returns unique api key candidates in lookup order', () => {
    withFreshLocalStorage(() => {
      globalThis.localStorage.setItem('qsm_api_key', 'stored-key');
      expect(getApiKeyCandidates('manual-key')).toEqual(['stored-key', 'manual-key']);
    });
  });
});
