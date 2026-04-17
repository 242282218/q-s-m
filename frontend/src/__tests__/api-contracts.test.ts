import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const httpMocks = vi.hoisted(() => ({
  request: vi.fn(),
}));

const sseMocks = vi.hoisted(() => ({
  consumeSse: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/shared/lib/http', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/http')>('@/shared/lib/http');
  return {
    ...actual,
    request: httpMocks.request,
  };
});

vi.mock('@/shared/lib/sse', () => ({
  consumeSse: sseMocks.consumeSse,
}));

import {
  getCollectionsCursor,
  getSettingsWithApiKey,
  saveResource,
  startRenameSse,
} from '@/api';

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

describe('API wrapper contracts', () => {
  const originalFetch = globalThis.fetch;
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(globalThis, 'localStorage', {
      value: createStorage(),
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
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

  it('clamps collection cursor limits and includes the cursor in the query string', async () => {
    httpMocks.request.mockResolvedValue({
      code: 0,
      message: 'OK',
      data: { items: [], pagination: { limit: 100, has_more: false, next_cursor: null } },
    });

    await getCollectionsCursor('next-cursor', 999);

    expect(httpMocks.request).toHaveBeenCalledWith(
      '/collections/cursor?limit=100&sort_by=saved_at&order=desc&cursor=next-cursor'
    );
  });

  it('passes explicit API keys through wrapper-specific request headers', async () => {
    httpMocks.request.mockResolvedValue({
      code: 0,
      message: 'OK',
      data: {},
    });

    await getSettingsWithApiKey('secret-key');

    expect(httpMocks.request).toHaveBeenCalledWith('/settings', {
      headers: { 'X-API-Key': 'secret-key' },
    });
  });

  it('injects the default transfer directory when saving a resource', async () => {
    httpMocks.request.mockResolvedValue({
      code: 0,
      message: 'OK',
      data: { saved_files: [], task_id: 'task-1', collection_id: null, collection_created: false },
    });

    await saveResource({
      link: 'https://example.com/share',
      media_type: 'movie',
      title: 'Alien',
    });

    expect(httpMocks.request).toHaveBeenCalledWith('/quark/transfer', {
      method: 'POST',
      body: JSON.stringify({
        to_dir_fid: '0',
        link: 'https://example.com/share',
        media_type: 'movie',
        title: 'Alien',
      }),
    });
  });

  it('surfaces SSE API errors without delegating to the stream consumer', async () => {
    globalThis.localStorage.setItem('qsm_api_key', 'secret-key');
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 5031, message: 'rename failed' }), {
        status: 503,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(startRenameSse({ collection_id: 7 }, () => {})).rejects.toMatchObject({
      message: 'rename failed',
      code: 5031,
      status: 503,
    });
    expect(sseMocks.consumeSse).not.toHaveBeenCalled();
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get('X-API-Key')).toBe('secret-key');
  });
});
