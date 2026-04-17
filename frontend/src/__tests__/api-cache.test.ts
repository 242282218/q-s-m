import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cachedFetch,
  cancelAllGlobalRequests,
  clearGlobalCache,
  globalCache,
  globalDeduplicator,
  MemoryCache,
  RequestDeduplicator,
  useApiCache,
} from '@/composables/useApiCache';
import { getCacheStats, getHomeFeed } from '@/api';

describe('API Caching and Deduplication', () => {
  let testCache: MemoryCache<unknown>;
  let testDeduplicator: RequestDeduplicator<unknown>;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    testCache = new MemoryCache(100);
    testDeduplicator = new RequestDeduplicator<unknown>();
    globalCache.clear();
    globalDeduplicator.cancelAll();
    vi.clearAllMocks();
  });

  afterEach(() => {
    globalDeduplicator.cancelAll();
    vi.useRealTimers();
    Object.defineProperty(globalThis, 'fetch', {
      value: originalFetch,
      configurable: true,
      writable: true,
    });
  });

  describe('MemoryCache', () => {
    it('should store and retrieve values', () => {
      testCache.set('test-key', { data: 'test' }, 60000);
      const result = testCache.get('test-key');
      expect(result).toEqual({ data: 'test' });
    });

    it('should return null for expired entries', () => {
      vi.useFakeTimers();
      testCache.set('expiring-key', { data: 'test' }, 100);

      vi.advanceTimersByTime(101);

      const result = testCache.get('expiring-key');
      expect(result).toBeNull();

      vi.useRealTimers();
    });

    it('should evict oldest entry when max size exceeded', () => {
      const smallCache = new MemoryCache(10);

      for (let i = 0; i < 12; i++) {
        smallCache.set(`key-${i}`, { data: i }, 60000);
      }

      const firstResult = smallCache.get('key-0');
      expect(firstResult).toBeNull();

      const lastResult = smallCache.get('key-11');
      expect(lastResult).not.toBeNull();
    });
  });

  describe('Request Deduplicator', () => {
    it('should prevent duplicate requests', async () => {
      const mockFetcher = vi.fn(() => Promise.resolve('result'));

      const promises = [
        testDeduplicator.getOrCreate('same-key', mockFetcher),
        testDeduplicator.getOrCreate('same-key', mockFetcher),
        testDeduplicator.getOrCreate('same-key', mockFetcher),
      ];

      const results = await Promise.all(promises);

      expect(mockFetcher).toHaveBeenCalledTimes(1);
      expect(results).toEqual(['result', 'result', 'result']);
    });

    it('should allow different keys to execute separately', async () => {
      const mockFetcher = vi.fn(() => Promise.resolve('result'));

      await Promise.all([
        testDeduplicator.getOrCreate('key-1', mockFetcher),
        testDeduplicator.getOrCreate('key-2', mockFetcher),
        testDeduplicator.getOrCreate('key-3', mockFetcher),
      ]);

      expect(mockFetcher).toHaveBeenCalledTimes(3);
    });

    it('should cancel a pending request and clear tracking state', async () => {
      const pending = testDeduplicator.getOrCreate('slow-key', (signal) => {
        return new Promise((_, reject) => {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      });

      expect(testDeduplicator.has('slow-key')).toBe(true);
      expect(testDeduplicator.size()).toBe(1);

      testDeduplicator.cancel('slow-key');

      await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
      expect(testDeduplicator.has('slow-key')).toBe(false);
      expect(testDeduplicator.size()).toBe(0);
    });
  });

  describe('Global Cache Integration', () => {
    it('should use global cache for caching', () => {
      globalCache.set('global-test', { data: 'global' }, 60000);
      const result = globalCache.get('global-test');
      expect(result).toEqual({ data: 'global' });
    });

    it('should clear global cache', () => {
      globalCache.set('to-clear', { data: 'test' }, 60000);
      globalCache.clear();
      const result = globalCache.get('to-clear');
      expect(result).toBeNull();
    });

    it('should clear only cache entries matching a regex pattern', () => {
      globalCache.set('user:1', { data: 'user' }, 60000);
      globalCache.set('movie:1', { data: 'movie' }, 60000);

      clearGlobalCache('^user:');

      expect(globalCache.get('user:1')).toBeNull();
      expect(globalCache.get('movie:1')).toEqual({ data: 'movie' });
    });

    it('should cache fetch responses, support force refresh, and surface HTTP errors', async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ data: 'cached' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          })
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ data: 'fresh' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          })
        )
        .mockResolvedValueOnce(
          new Response('nope', { status: 503, statusText: 'Service Unavailable' })
        );
      vi.stubGlobal('fetch', fetchMock);

      const first = await cachedFetch<{ data: string }>('/cached-endpoint');
      const second = await cachedFetch<{ data: string }>('/cached-endpoint');
      const refreshed = await cachedFetch<{ data: string }>('/cached-endpoint', {
        forceRefresh: true,
      });

      expect(first).toEqual({ data: 'cached' });
      expect(second).toEqual({ data: 'cached' });
      expect(refreshed).toEqual({ data: 'fresh' });
      expect(fetchMock).toHaveBeenCalledTimes(2);

      await expect(
        cachedFetch('/broken-endpoint', {
          forceRefresh: true,
        })
      ).rejects.toThrow('HTTP 503: Service Unavailable');
    });

    it('should cancel pending global requests through the public wrapper', async () => {
      const pending = globalDeduplicator.getOrCreate('global-slow', (signal) => {
        return new Promise((_, reject) => {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      });

      cancelAllGlobalRequests();

      await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
      expect(globalDeduplicator.size()).toBe(0);
    });
  });

  describe('API Functions', () => {
    it('getHomeFeed should reuse the shared HTTP cache and update cache stats', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 0,
            message: 'success',
            data: { hero_items: [], sections: {}, section_order: [], generated_at: '' },
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }
        )
      );
      vi.stubGlobal('fetch', fetchMock);

      const first = await getHomeFeed();
      const second = await getHomeFeed();

      expect(first).toEqual(second);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(getCacheStats()).toMatchObject({ hits: 1, misses: 1 });
    });
  });

  describe('useApiCache composable', () => {
    it('should reuse local cache, honor forceRefresh, and expose manual cache helpers', async () => {
      const cache = useApiCache<string>({ defaultTtl: 60000 });
      const fetcher = vi
        .fn<() => Promise<string>>()
        .mockResolvedValueOnce('Alien')
        .mockResolvedValueOnce('Aliens');

      const first = await cache.execute('movie:42', fetcher);
      const second = await cache.execute('movie:42', fetcher);
      const refreshed = await cache.execute('movie:42', fetcher, { forceRefresh: true });

      cache.setCache('manual', 'Blade Runner', 60000);

      expect(first).toBe('Alien');
      expect(second).toBe('Alien');
      expect(refreshed).toBe('Aliens');
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(cache.data.value).toBe('Aliens');
      expect(cache.error.value).toBeNull();
      expect(cache.getCache('manual')).toBe('Blade Runner');
      expect(cache.hasCache('manual')).toBe(true);
      expect(cache.getCacheSize()).toBe(2);

      cache.clearCache('manual');
      expect(cache.hasCache('manual')).toBe(false);

      cache.clearCache();
      expect(cache.getCacheSize()).toBe(0);
    });

    it('should abort pending local requests when cancelAll is invoked', async () => {
      const cache = useApiCache<string>();

      const pending = cache.execute('slow-movie', (signal) => {
        return new Promise((_, reject) => {
          signal.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
      });

      expect(cache.loading.value).toBe(true);

      cache.cancelAll();

      await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
      expect(cache.loading.value).toBe(false);
      expect(cache.error.value).toMatchObject({ name: 'AbortError' });
    });
  });
});
