import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request } from '@/lib/http';
import { 
  cachedRequest, 
  enhancedCache, 
  requestDeduplicator, 
  getHomeFeed, 
  getCollections,
  getMetrics,
  getHealth
} from '@/api';

// Mock the http module
vi.mock('@/lib/http', () => ({
  request: vi.fn(),
}));

describe('API Caching and Deduplication', () => {
  beforeEach(() => {
    // Clear cache before each test
    enhancedCache.clear();
    vi.clearAllMocks();
  });

  describe('EnhancedCache', () => {
    it('should store and retrieve values', () => {
      enhancedCache.set('test-key', { data: 'test' }, 60000);
      const result = enhancedCache.get('test-key');
      expect(result).toEqual({ data: 'test' });
    });

    it('should return null for expired entries', () => {
      vi.useFakeTimers();
      enhancedCache.set('expiring-key', { data: 'test' }, 100); // 100ms TTL
      
      // Advance time past expiration
      vi.advanceTimersByTime(101);
      
      const result = enhancedCache.get('expiring-key');
      expect(result).toBeNull();
      
      vi.useRealTimers();
    });

    it('should implement LRU eviction when max size exceeded', () => {
      // Fill cache to max capacity
      for (let i = 0; i < 200; i++) {
        enhancedCache.set(`key-${i}`, { data: i }, 60000);
      }
      
      // Add one more item
      enhancedCache.set('new-key', { data: 'new' }, 60000);
      
      // First key should be evicted (LRU)
      const firstResult = enhancedCache.get('key-0');
      expect(firstResult).toBeNull();
      
      // Last key should still be there
      const lastResult = enhancedCache.get('key-199');
      expect(lastResult).not.toBeNull();
    });
  });

  describe('Request Deduplicator', () => {
    it('should prevent duplicate requests', async () => {
      const mockFetcher = vi.fn(() => Promise.resolve('result'));
      
      // Make 3 simultaneous requests with the same key
      const promises = [
        requestDeduplicator.request('same-key', mockFetcher),
        requestDeduplicator.request('same-key', mockFetcher),
        requestDeduplicator.request('same-key', mockFetcher),
      ];
      
      const results = await Promise.all(promises);
      
      // Should only call the fetcher once
      expect(mockFetcher).toHaveBeenCalledTimes(1);
      
      // All results should be the same
      expect(results).toEqual(['result', 'result', 'result']);
    });

    it('should allow different keys to execute separately', async () => {
      const mockFetcher = vi.fn(() => Promise.resolve('result'));
      
      // Make 3 requests with different keys
      await Promise.all([
        requestDeduplicator.request('key-1', mockFetcher),
        requestDeduplicator.request('key-2', mockFetcher),
        requestDeduplicator.request('key-3', mockFetcher),
      ]);
      
      // Should call the fetcher 3 times
      expect(mockFetcher).toHaveBeenCalledTimes(3);
    });
  });

  describe('cachedRequest', () => {
    it('should return cached value when available and not expired', async () => {
      const mockFetcher = vi.fn(() => Promise.resolve({ data: 'fetched' }));
      
      // First call should use fetcher
      const result1 = await cachedRequest('test-key', mockFetcher, 60000);
      expect(mockFetcher).toHaveBeenCalledTimes(1);
      expect(result1).toEqual({ data: 'fetched' });
      
      // Second call should use cache
      const result2 = await cachedRequest('test-key', mockFetcher, 60000);
      expect(mockFetcher).toHaveBeenCalledTimes(1); // Still 1
      expect(result2).toEqual({ data: 'fetched' });
    });

    it('should call fetcher when cache is expired', async () => {
      vi.useFakeTimers();
      const mockFetcher = vi.fn(() => Promise.resolve({ data: 'fetched' }));
      
      // First call
      await cachedRequest('test-key', mockFetcher, 100); // 100ms TTL
      expect(mockFetcher).toHaveBeenCalledTimes(1);
      
      // Advance time past expiration
      vi.advanceTimersByTime(101);
      
      // Second call should fetch again
      await cachedRequest('test-key', mockFetcher, 100);
      expect(mockFetcher).toHaveBeenCalledTimes(2);
      
      vi.useRealTimers();
    });
  });

  describe('API Functions', () => {
    it('getHomeFeed should use deduplication and caching', async () => {
      const mockResponse = {
        code: 0,
        message: 'success',
        data: { hero_items: [], sections: {}, section_order: [] }
      };
      
      (request as vi.MockedFunction<typeof request>).mockResolvedValue(mockResponse);
      
      // Make 2 simultaneous calls
      const [result1, result2] = await Promise.all([
        getHomeFeed(),
        getHomeFeed()
      ]);
      
      // Should only make one actual request due to deduplication
      expect(request).toHaveBeenCalledTimes(1);
      expect(result1).toEqual(mockResponse);
      expect(result2).toEqual(mockResponse);
    });
  });
});