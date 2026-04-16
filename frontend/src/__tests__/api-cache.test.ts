import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request } from '@/shared/lib/http';
import { globalCache, MemoryCache, RequestDeduplicator } from '@/composables/useApiCache';
import { getHomeFeed } from '@/api';

vi.mock('@/shared/lib/http', () => ({
  request: vi.fn(),
}));

describe('API Caching and Deduplication', () => {
  let testCache: MemoryCache<unknown>;
  let testDeduplicator: RequestDeduplicator<unknown>;

  beforeEach(() => {
    testCache = new MemoryCache(100);
    testDeduplicator = new RequestDeduplicator<unknown>();
    globalCache.clear();
    vi.clearAllMocks();
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
  });

  describe('API Functions', () => {
    it('getHomeFeed should call the API endpoint', async () => {
      const mockResponse = {
        code: 0,
        message: 'success',
        data: { hero_items: [], sections: {}, section_order: [] },
      };

      (request as vi.MockedFunction<typeof request>).mockResolvedValue(mockResponse);

      const result = await getHomeFeed();

      expect(request).toHaveBeenCalledTimes(1);
      expect(result).toEqual(mockResponse);
    });
  });
});
