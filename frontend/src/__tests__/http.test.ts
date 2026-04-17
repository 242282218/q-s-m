import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { globalCache, globalDeduplicator } from '@/composables/useApiCache';
import { request, toQuery } from '@/lib/http';

interface StorageShape {
  clear: () => void;
  getItem: (key: string) => string | null;
  key: (index: number) => string | null;
  length: number;
  removeItem: (key: string) => void;
  setItem: (key: string, value: string) => void;
}

function createStorage(): StorageShape {
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

describe('HTTP Layer Tests', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    globalCache.clear();
    globalDeduplicator.cancelAll();
    vi.restoreAllMocks();

    Object.defineProperty(globalThis, 'localStorage', {
      value: createStorage(),
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    globalCache.clear();
    globalDeduplicator.cancelAll();
    vi.restoreAllMocks();

    Object.defineProperty(globalThis, 'fetch', {
      value: originalFetch,
      configurable: true,
      writable: true,
    });

    if (originalLocalStorage === undefined) {
      delete (globalThis as { localStorage?: Storage }).localStorage;
    } else {
      Object.defineProperty(globalThis, 'localStorage', {
        value: originalLocalStorage,
        configurable: true,
        writable: true,
      });
    }
  });

  it('reuses cached GET responses and skips the second network call', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'OK', data: { items: ['Alien'] } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const first = await request<{ items: string[] }>('/collections');
    const second = await request<{ items: string[] }>('/collections');

    expect(first).toEqual(second);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('raises a controlled ApiError when a successful response is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('plain-text', {
          status: 200,
          headers: { 'content-type': 'text/plain' },
        })
      )
    );

    await expect(request('/plain-text', {}, { cache: false })).rejects.toMatchObject({
      message: '期望 JSON 响应，但收到 text/plain',
      code: -1,
      status: 200,
    });
  });

  it('rejects JSON payloads that do not match the response contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      )
    );

    await expect(request('/bad-shape', {}, { cache: false })).rejects.toMatchObject({
      message: '响应格式不符合约定',
      code: -1,
      status: 200,
    });
  });

  it('serializes query params while dropping nullish and empty-string values', () => {
    expect(
      toQuery({
        q: 'Alien',
        page: 2,
        include_adult: false,
        empty: '',
        nil: null,
        missing: undefined,
      })
    ).toBe('?q=Alien&page=2&include_adult=false');
  });
});
