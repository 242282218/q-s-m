/**
 * API 请求缓存管理器
 * 
 * 优化记录:
 * - 2026-02-26: 添加请求缓存、内存管理、自动过期清理
 */

(function() {
  'use strict';

  // 缓存配置
  const CACHE_CONFIG = {
    maxSize: 100,           // 最大缓存条目数
    defaultTTL: 5 * 60 * 1000,  // 默认缓存5分钟
    cleanupInterval: 60 * 1000,  // 清理间隔1分钟
  };

  /**
   * 缓存条目
   */
  class CacheEntry {
    constructor(data, ttl) {
      this.data = data;
      this.timestamp = Date.now();
      this.ttl = ttl || CACHE_CONFIG.defaultTTL;
      this.accessCount = 1;
      this.lastAccessed = this.timestamp;
    }

    isExpired() {
      return Date.now() - this.timestamp > this.ttl;
    }

    touch() {
      this.accessCount++;
      this.lastAccessed = Date.now();
    }
  }

  /**
   * API 缓存管理器
   */
  class APICache {
    constructor() {
      this.cache = new Map();
      this.stats = {
        hits: 0,
        misses: 0,
        evictions: 0,
        totalRequests: 0
      };
      
      // 启动定期清理
      this._startCleanup();
    }

    /**
     * 生成缓存键
     */
    _generateKey(url, options = {}) {
      const method = options.method || 'GET';
      const body = options.body || '';
      return `${method}:${url}:${body}`;
    }

    /**
     * 获取缓存
     */
    get(url, options = {}) {
      const key = this._generateKey(url, options);
      const entry = this.cache.get(key);

      if (!entry) {
        this.stats.misses++;
        return null;
      }

      if (entry.isExpired()) {
        this.cache.delete(key);
        this.stats.misses++;
        return null;
      }

      entry.touch();
      this.stats.hits++;
      return entry.data;
    }

    /**
     * 设置缓存
     */
    set(url, data, options = {}, ttl = null) {
      // 只缓存 GET 请求
      if (options.method && options.method !== 'GET') {
        return;
      }

      const key = this._generateKey(url, options);
      
      // 如果缓存已满，清理最旧的条目
      if (this.cache.size >= CACHE_CONFIG.maxSize) {
        this._evictLRU();
      }

      this.cache.set(key, new CacheEntry(data, ttl));
    }

    /**
     * 删除缓存
     */
    delete(url, options = {}) {
      const key = this._generateKey(url, options);
      return this.cache.delete(key);
    }

    /**
     * 清空缓存
     */
    clear() {
      this.cache.clear();
      this.stats.hits = 0;
      this.stats.misses = 0;
      this.stats.evictions = 0;
      this.stats.totalRequests = 0;
    }

    /**
     * 获取统计信息
     */
    getStats() {
      const hitRate = this.stats.totalRequests > 0 
        ? (this.stats.hits / this.stats.totalRequests * 100).toFixed(1)
        : 0;
      
      return {
        size: this.cache.size,
        maxSize: CACHE_CONFIG.maxSize,
        hits: this.stats.hits,
        misses: this.stats.misses,
        evictions: this.stats.evictions,
        hitRate: hitRate + '%',
        totalRequests: this.stats.totalRequests
      };
    }

    /**
     * LRU 淘汰策略
     */
    _evictLRU() {
      let oldestKey = null;
      let oldestTime = Infinity;

      for (const [key, entry] of this.cache) {
        if (entry.lastAccessed < oldestTime) {
          oldestTime = entry.lastAccessed;
          oldestKey = key;
        }
      }

      if (oldestKey) {
        this.cache.delete(oldestKey);
        this.stats.evictions++;
      }
    }

    /**
     * 清理过期缓存
     */
    _cleanup() {
      const now = Date.now();
      let cleaned = 0;

      for (const [key, entry] of this.cache) {
        if (entry.isExpired()) {
          this.cache.delete(key);
          cleaned++;
        }
      }

      if (cleaned > 0) {
        console.log(`[APICache] Cleaned ${cleaned} expired entries`);
      }
    }

    /**
     * 启动定期清理
     */
    _startCleanup() {
      setInterval(() => this._cleanup(), CACHE_CONFIG.cleanupInterval);
    }
  }

  // 创建全局缓存实例
  const apiCache = new APICache();

  /**
   * 带缓存的 fetch 函数
   * 
   * @param {string} url - 请求地址
   * @param {Object} options - fetch 选项
   * @param {Object} cacheOptions - 缓存选项 { ttl, skipCache }
   * @returns {Promise<Response>}
   */
  async function cachedFetch(url, options = {}, cacheOptions = {}) {
    const { ttl, skipCache = false } = cacheOptions;

    // 检查缓存
    if (!skipCache && (!options.method || options.method === 'GET')) {
      const cached = apiCache.get(url, options);
      if (cached) {
        console.log(`[cachedFetch] Cache hit: ${url}`);
        return new Response(JSON.stringify(cached), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
    }

    // 发起请求
    const response = await fetch(url, options);
    
    // 缓存成功的 GET 请求
    if (response.ok && !skipCache && (!options.method || options.method === 'GET')) {
      try {
        const clonedResponse = response.clone();
        const data = await clonedResponse.json();
        apiCache.set(url, data, options, ttl);
      } catch (e) {
        // 非 JSON 响应，不缓存
      }
    }

    return response;
  }

  // 暴露到全局
  window.APICache = {
    get: (url, options) => apiCache.get(url, options),
    set: (url, data, options, ttl) => apiCache.set(url, data, options, ttl),
    delete: (url, options) => apiCache.delete(url, options),
    clear: () => apiCache.clear(),
    getStats: () => apiCache.getStats(),
    fetch: cachedFetch
  };

  console.log('[APICache] Initialized');
})();
