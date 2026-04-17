import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/sse', () => ({
  consumeSse: vi.fn().mockResolvedValue(undefined),
}));

import { startVerifySse } from '@/api';
import { ApiError, cancelAllHttpRequests, request } from '@/lib/http';

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

describe('api auth and timeout', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();

    Object.defineProperty(globalThis, 'localStorage', {
      value: createStorage(),
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();

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

  it('adds X-API-Key to regular requests from runtime config', async () => {
    globalThis.localStorage.setItem('qsm_api_key', 'secret-key');

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 0, message: 'OK', data: { ok: true } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await request('/secure', { method: 'POST', body: JSON.stringify({}) }, { cache: false });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get('X-API-Key')).toBe('secret-key');
  });

  it('adds X-API-Key to SSE requests from the same runtime config', async () => {
    globalThis.localStorage.setItem('qsm_api_key', 'secret-key');

    const fetchMock = vi.fn().mockResolvedValue(
      new Response('', {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await startVerifySse({}, () => {});

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get('X-API-Key')).toBe('secret-key');
  });

  it('times out the retry attempt with a fresh timeout budget', async () => {
    let attempt = 0;
    const fetchMock = vi
      .fn()
      .mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
        attempt += 1;

        if (attempt === 1) {
          return Promise.resolve(
            new Response(JSON.stringify({ code: 503, message: 'retry', data: null }), {
              status: 503,
              headers: { 'content-type': 'application/json' },
            })
          );
        }

        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true }
          );
        });
      });
    vi.stubGlobal('fetch', fetchMock);

    const outcome = await Promise.race([
      request('/retry', { method: 'POST', body: JSON.stringify({}) }, { cache: false, timeout: 20 })
        .then(() => 'resolved')
        .catch((error) => (error instanceof ApiError ? 'rejected' : 'other')),
      new Promise((resolve) => setTimeout(() => resolve('timedout'), 900)),
    ]);

    expect(outcome).toBe('rejected');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('propagates global request cancellation as AbortError instead of timeout', async () => {
    const fetchMock = vi.fn().mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('Aborted', 'AbortError')),
          { once: true }
        );
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const pending = request('/cancel-me', { method: 'GET' }, { cache: false, timeout: 5000 });
    await Promise.resolve();

    cancelAllHttpRequests();

    const outcome = await Promise.race([
      pending
        .then(() => 'resolved')
        .catch((error) =>
          error instanceof DOMException && error.name === 'AbortError' ? 'aborted' : 'other'
        ),
      new Promise((resolve) => setTimeout(() => resolve('timedout'), 200)),
    ]);

    expect(outcome).toBe('aborted');
  });
});
