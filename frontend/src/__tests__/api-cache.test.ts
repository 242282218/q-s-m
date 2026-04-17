import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearGlobalCache,
  globalCache,
  MemoryCache,
  RequestDeduplicator,
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
    vi.clearAllMocks();
  });

  afterEach(() => {
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
});
