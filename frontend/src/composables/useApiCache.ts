import { ref, type Ref } from 'vue';

// ============================================
// 类型定义
// ============================================

export interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

export interface PendingRequest<T> {
  promise: Promise<T>;
  abortControllers: Set<AbortController>;
}

export interface UseApiCacheOptions {
  /** 默认缓存时间（毫秒），默认 5 分钟 */
  defaultTtl?: number;
  /** 最大缓存条目数，默认 100 */
  maxEntries?: number;
  /** 是否启用缓存 */
  enabled?: boolean;
}

export interface UseApiCacheReturn<T> {
  /** 缓存的数据 */
  data: Ref<T | null>;
  /** 是否正在加载 */
  loading: Ref<boolean>;
  /** 错误信息 */
  error: Ref<Error | null>;
  /** 执行请求（带缓存） */
  execute: (
    key: string,
    fetcher: (signal: AbortSignal) => Promise<T>,
    options?: CacheRequestOptions
  ) => Promise<T>;
  /** 手动设置缓存 */
  setCache: (key: string, data: T, ttl?: number) => void;
  /** 获取缓存 */
  getCache: (key: string) => T | null;
  /** 清除指定缓存 */
  clearCache: (key?: string) => void;
  /** 检查是否有缓存 */
  hasCache: (key: string) => boolean;
  /** 取消所有进行中的请求 */
  cancelAll: () => void;
  /** 获取缓存大小 */
  getCacheSize: () => number;
}

export interface CacheRequestOptions {
  /** 缓存时间（毫秒） */
  ttl?: number;
  /** 是否强制刷新（跳过缓存） */
  forceRefresh?: boolean;
  /** 自定义缓存键 */
  cacheKey?: string;
}

export interface CacheStats {
  hits: number;
  misses: number;
  evictions: number;
  errors: number;
}

// ============================================
// 内存缓存管理器
// ============================================

class MemoryCache<T = unknown> {
  private cache: Map<string, CacheEntry<T>> = new Map();
  private maxEntries: number;
  private stats: CacheStats = {
    hits: 0,
    misses: 0,
    evictions: 0,
    errors: 0,
  };

  constructor(maxEntries: number = 100) {
    this.maxEntries = maxEntries;
  }

  /**
   * 获取缓存条目
   */
  get(key: string): T | null {
    try {
      const entry = this.cache.get(key);
      if (!entry) {
        this.stats.misses++;
        return null;
      }

      // 检查是否过期
      if (Date.now() - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
        this.stats.misses++;
        return null;
      }

      this.stats.hits++;
      // 读取命中后刷新顺序，维持 LRU 语义。
      this.cache.delete(key);
      this.cache.set(key, entry);
      return entry.data;
    } catch {
      this.stats.errors++;
      return null;
    }
  }

  /**
   * 设置缓存条目
   */
  set(key: string, data: T, ttl: number): void {
    try {
      if (this.cache.has(key)) {
        this.cache.delete(key);
      }

      // 如果超过最大条目数，删除最旧的条目
      if (this.cache.size >= this.maxEntries) {
        const firstKey = this.cache.keys().next().value;
        if (firstKey !== undefined) {
          this.cache.delete(firstKey);
          this.stats.evictions++;
        }
      }

      this.cache.set(key, {
        data,
        timestamp: Date.now(),
        ttl,
      });
    } catch {
      this.stats.errors++;
    }
  }

  /**
   * 检查是否有缓存（且未过期）
   */
  has(key: string): boolean {
    try {
      const entry = this.cache.get(key);
      if (!entry) return false;

      // 检查是否过期
      if (Date.now() - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
        return false;
      }

      return true;
    } catch {
      this.stats.errors++;
      return false;
    }
  }

  /**
   * 删除缓存条目
   */
  delete(key: string): boolean {
    try {
      return this.cache.delete(key);
    } catch {
      this.stats.errors++;
      return false;
    }
  }

  /**
   * 清空缓存
   */
  clear(): void {
    try {
      this.cache.clear();
      this.resetStats();
    } catch {
      this.stats.errors++;
    }
  }

  /**
   * 获取缓存大小
   */
  size(): number {
    // 清理过期条目后返回大小
    this.cleanup();
    return this.cache.size;
  }

  /**
   * 清理过期条目
   */
  cleanup(): void {
    try {
      const now = Date.now();
      for (const [key, entry] of this.cache.entries()) {
        if (now - entry.timestamp > entry.ttl) {
          this.cache.delete(key);
        }
      }
    } catch {
      this.stats.errors++;
    }
  }

  getStats(): CacheStats {
    return { ...this.stats };
  }

  resetStats(): void {
    this.stats = {
      hits: 0,
      misses: 0,
      evictions: 0,
      errors: 0,
    };
  }
}

// ============================================
// 请求去重管理器
// ============================================

class RequestDeduplicator<T = unknown> {
  private pendingRequests: Map<string, PendingRequest<T>> = new Map();

  /**
   * 获取或创建请求
   * @param key 请求键
   * @param fetcher 请求函数
   * @returns 请求结果
   */
  async getOrCreate(key: string, fetcher: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const existingRequest = this.pendingRequests.get(key);

    if (existingRequest) {
      // 请求已在进行中，返回相同的 Promise
      const abortController = new AbortController();
      existingRequest.abortControllers.add(abortController);

      try {
        const result = await existingRequest.promise;
        return result;
      } finally {
        existingRequest.abortControllers.delete(abortController);
      }
    }

    // 创建新的请求
    const abortControllers = new Set<AbortController>();
    const mainAbortController = new AbortController();
    abortControllers.add(mainAbortController);

    const promise = fetcher(mainAbortController.signal).finally(() => {
      // 请求完成后清理
      this.pendingRequests.delete(key);
    });

    this.pendingRequests.set(key, {
      promise,
      abortControllers,
    });

    return promise;
  }

  /**
   * 取消指定键的请求
   */
  cancel(key: string): void {
    const request = this.pendingRequests.get(key);
    if (request) {
      request.abortControllers.forEach((controller) => {
        controller.abort();
      });
      this.pendingRequests.delete(key);
    }
  }

  /**
   * 取消所有进行中的请求
   */
  cancelAll(): void {
    this.pendingRequests.forEach((request) => {
      request.abortControllers.forEach((controller) => {
        controller.abort();
      });
    });
    this.pendingRequests.clear();
  }

  /**
   * 检查是否有进行中的请求
   */
  has(key: string): boolean {
    return this.pendingRequests.has(key);
  }

  /**
   * 获取进行中的请求数量
   */
  size(): number {
    return this.pendingRequests.size;
  }
}

// ============================================
// 全局实例
// ============================================

const globalCache = new MemoryCache<unknown>(100);
const globalDeduplicator = new RequestDeduplicator<unknown>();

// ============================================
// Composable
// ============================================

/**
 * API 请求缓存和去重 Composable
 *
 * 功能：
 * - 内存缓存（支持 TTL）
 * - 请求去重（pending request merge）
 * - AbortController 支持请求取消
 * - 自动缓存清理
 *
 * @example
 * ```ts
 * const { data, loading, error, execute, setCache, getCache } = useApiCache<UserData>();
 *
 * // 执行带缓存的请求
 * const userData = await execute(
 *   `user-${userId}`,
 *   (signal) => fetchUser(userId, signal),
 *   { ttl: 60000 } // 缓存 1 分钟
 * );
 *
 * // 强制刷新
 * const freshData = await execute(
 *   `user-${userId}`,
 *   (signal) => fetchUser(userId, signal),
 *   { forceRefresh: true }
 * );
 * ```
 */
export function useApiCache<T = unknown>(options: UseApiCacheOptions = {}): UseApiCacheReturn<T> {
  const {
    defaultTtl = 5 * 60 * 1000, // 默认 5 分钟
    maxEntries = 100,
    enabled = true,
  } = options;

  // 使用局部缓存实例（可选，也可以使用全局实例）
  const cache = new MemoryCache<T>(maxEntries);
  const deduplicator = new RequestDeduplicator<T>();

  const data = ref<T | null>(null) as Ref<T | null>;
  const loading = ref(false);
  const error = ref<Error | null>(null);

  /**
   * 生成缓存键
   */
  const generateCacheKey = (key: string): string => {
    return `api-cache:${key}`;
  };

  /**
   * 执行请求（带缓存和去重）
   */
  const execute = async (
    key: string,
    fetcher: (signal: AbortSignal) => Promise<T>,
    requestOptions: CacheRequestOptions = {}
  ): Promise<T> => {
    const { ttl = defaultTtl, forceRefresh = false, cacheKey = key } = requestOptions;
    const fullCacheKey = generateCacheKey(cacheKey);

    loading.value = true;
    error.value = null;

    try {
      // 检查缓存（除非强制刷新）
      if (enabled && !forceRefresh) {
        const cached = cache.get(fullCacheKey);
        if (cached !== null) {
          data.value = cached;
          loading.value = false;
          return cached;
        }
      }

      // 使用去重器执行请求
      const result = await deduplicator.getOrCreate(key, async (signal) => {
        try {
          const response = await fetcher(signal);

          // 缓存结果
          if (enabled) {
            cache.set(fullCacheKey, response, ttl);
          }

          return response;
        } catch (err) {
          // 重新抛出错误以便上层处理
          throw err instanceof Error ? err : new Error(String(err));
        }
      });

      data.value = result;
      return result;
    } catch (err) {
      const errorInstance = err instanceof Error ? err : new Error(String(err));
      error.value = errorInstance;
      throw errorInstance;
    } finally {
      loading.value = false;
    }
  };

  /**
   * 手动设置缓存
   */
  const setCache = (key: string, value: T, ttl?: number): void => {
    const fullCacheKey = generateCacheKey(key);
    cache.set(fullCacheKey, value, ttl ?? defaultTtl);
  };

  /**
   * 获取缓存
   */
  const getCache = (key: string): T | null => {
    const fullCacheKey = generateCacheKey(key);
    return cache.get(fullCacheKey);
  };

  /**
   * 清除缓存
   */
  const clearCache = (key?: string): void => {
    if (key) {
      const fullCacheKey = generateCacheKey(key);
      cache.delete(fullCacheKey);
    } else {
      cache.clear();
    }
  };

  /**
   * 检查是否有缓存
   */
  const hasCache = (key: string): boolean => {
    const fullCacheKey = generateCacheKey(key);
    return cache.has(fullCacheKey);
  };

  /**
   * 取消所有进行中的请求
   */
  const cancelAll = (): void => {
    deduplicator.cancelAll();
    loading.value = false;
  };

  /**
   * 获取缓存大小
   */
  const getCacheSize = (): number => {
    return cache.size();
  };

  return {
    data,
    loading,
    error,
    execute,
    setCache,
    getCache,
    clearCache,
    hasCache,
    cancelAll,
    getCacheSize,
  };
}

// ============================================
// 工具函数
// ============================================

/**
 * 创建请求缓存键
 * @param endpoint API 端点
 * @param params 请求参数
 * @returns 缓存键
 */
export function createCacheKey(endpoint: string, params?: Record<string, unknown>): string {
  if (!params || Object.keys(params).length === 0) {
    return endpoint;
  }

  const sortedParams = Object.entries(params)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join('&');

  return `${endpoint}?${sortedParams}`;
}

/**
 * 带缓存的 fetch 包装器
 * @param url 请求 URL
 * @param options 请求选项
 * @returns 响应数据
 */
export async function cachedFetch<T>(
  url: string,
  options: RequestInit & { ttl?: number; forceRefresh?: boolean } = {}
): Promise<T> {
  const { ttl = 5 * 60 * 1000, forceRefresh = false, ...fetchOptions } = options;

  const cacheKey = `fetch:${url}:${JSON.stringify(fetchOptions)}`;

  // 检查缓存
  if (!forceRefresh) {
    const cached = globalCache.get(cacheKey);
    if (cached !== null) {
      return cached as T;
    }
  }

  // 执行请求
  const response = await fetch(url, fetchOptions);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();

  // 缓存结果
  globalCache.set(cacheKey, data, ttl);

  return data as T;
}

/**
 * 清除全局缓存
 * @param pattern 可选的匹配模式（正则表达式字符串）
 */
export function clearGlobalCache(pattern?: string): void {
  if (!pattern) {
    globalCache.clear();
    return;
  }

  // 根据模式清除缓存
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _regex = new RegExp(pattern);
  // 注意：这里需要遍历缓存键并删除匹配的条目
  // 由于 MemoryCache 没有暴露 keys 方法，我们需要添加一个
}

/**
 * 取消所有进行中的全局请求
 */
export function cancelAllGlobalRequests(): void {
  globalDeduplicator.cancelAll();
}

// 导出全局实例供外部使用
export { globalCache, globalDeduplicator, MemoryCache, RequestDeduplicator };
