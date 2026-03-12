import assert from 'node:assert/strict';

import {
  getApiKeyCandidates,
  getConfiguredApiKey,
  setConfiguredApiKey,
  withApiKeyHeader,
} from '../src/lib/api-key.ts';

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

withFreshLocalStorage(() => {
  globalThis.localStorage.setItem('qsm_api_key', 'stored-key');
  const headers = withApiKeyHeader({ 'X-API-Key': 'manual-key' });
  assert.equal(headers.get('X-API-Key'), 'manual-key');
});

withFreshLocalStorage(() => {
  setConfiguredApiKey('fresh-key');
  assert.equal(globalThis.localStorage.getItem('qsm_api_key'), 'fresh-key');
  assert.equal(getConfiguredApiKey(), 'fresh-key');
});

withFreshLocalStorage(() => {
  globalThis.localStorage.setItem('qsm_api_key', 'stored-key');
  assert.deepEqual(getApiKeyCandidates('manual-key'), ['stored-key', 'manual-key']);
});

console.log('api-key tests passed');
