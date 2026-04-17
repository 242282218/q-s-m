import type { ApiResponse } from '@/types/api';
import { globalCache, globalDeduplicator, createCacheKey } from '@/composables/useApiCache';
import { emitAuthRequired } from '@/shared/lib/auth-prompt';
import { withApiKeyHeader } from '@/shared/lib/api-key';

export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 500;

// 默认缓存配置
const DEFAULT_CACHE_TTL = 5 * 60 * 1000; // 5 分钟
const CACHEABLE_METHODS = ['GET', 'HEAD'];
const HTTP_CACHE_KEY_PREFIX = /^(GET|HEAD):/;

// 请求拦截器类型
export interface RequestInterceptor {
  onRequest: (config: RequestInit) => RequestInit | Promise<RequestInit>;
}

// 拦截器管理器
class InterceptorManager {
  private requestInterceptors: RequestInterceptor[] = [];

  /**
   * 添加请求拦截器
   * @param interceptor 拦截器对象
   */
  addRequestInterceptor(interceptor: RequestInterceptor): void {
    this.requestInterceptors.push(interceptor);
  }

  /**
   * 移除请求拦截器
   * @param interceptor 拦截器对象
   */
  removeRequestInterceptor(interceptor: RequestInterceptor): void {
    const index = this.requestInterceptors.indexOf(interceptor);
    if (index > -1) {
      this.requestInterceptors.splice(index, 1);
    }
  }

  /**
   * 执行所有请求拦截器
   * @param config 请求配置
   * @returns 处理后的请求配置
   */
  async executeRequestInterceptors(config: RequestInit): Promise<RequestInit> {
    let processedConfig = config;
    for (const interceptor of this.requestInterceptors) {
      processedConfig = await interceptor.onRequest(processedConfig);
    }
    return processedConfig;
  }

  /**
   * 获取拦截器数量（用于测试）
   */
  getInterceptorCount(): number {
    return this.requestInterceptors.length;
  }
}

// 导出单例
export const interceptorManager = new InterceptorManager();

export class ApiError extends Error {
  code: number;
  status: number;
  details?: unknown;

  constructor(message: string, code: number, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function shouldRetry(status: number): boolean {
  return status === 429 || status >= 500;
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeAbortError(error: Error): DOMException | Error {
  return error instanceof DOMException ? error : new DOMException(error.message, 'AbortError');
}

async function parseJsonResponse<T>(response: Response): Promise<ApiResponse<T>> {
  const contentType = response.headers.get('content-type');
  const isJson = contentType?.includes('application/json') ?? false;

  try {
    return (await response.json()) as ApiResponse<T>;
  } catch (parseError) {
    const errorMessage = isJson
      ? `JSON 解析失败: ${parseError instanceof Error ? parseError.message : '未知错误'}`
      : `期望 JSON 响应，但收到 ${contentType || '未知类型'}`;

    if (!response.ok) {
      throw new ApiError(
        `HTTP ${response.status} - ${errorMessage}`,
        response.status,
        response.status
      );
    }

    throw new ApiError(errorMessage, -1, response.status, {
      contentType,
      url: response.url,
    });
  }
}

function validateResponseFormat<T>(payload: ApiResponse<T>, status: number): void {
  if (typeof payload.code !== 'number' || typeof payload.message !== 'string') {
    throw new ApiError('响应格式不符合约定', -1, status, payload);
  }
}

/**
 * 判断请求是否可缓存
 */
function isCacheableRequest(init: RequestInit): boolean {
  const method = (init.method || 'GET').toUpperCase();
  return CACHEABLE_METHODS.includes(method);
}

/**
 * 生成请求缓存键
 */
function generateRequestCacheKey(path: string, init: RequestInit): string {
  const method = init.method || 'GET';
  const body = init.body ? String(init.body) : '';
  return createCacheKey(`${method}:${path}`, { body });
}

function isHttpCacheKey(key: string): boolean {
  return HTTP_CACHE_KEY_PREFIX.test(key);
}

export interface RequestOptions {
  /** 是否启用缓存（仅对 GET/HEAD 请求有效） */
  cache?: boolean;
  /** 缓存时间（毫秒） */
  cacheTtl?: number;
  /** 强制刷新缓存 */
  forceRefresh?: boolean;
  /** 请求超时时间（毫秒） */
  timeout?: number;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {}
): Promise<ApiResponse<T>> {
  const {
    cache = true,
    cacheTtl = DEFAULT_CACHE_TTL,
    forceRefresh = false,
    timeout = 30000,
  } = options;

  // 检查是否可以使用缓存
  const canUseCache = cache && isCacheableRequest(init);
  const cacheKey = canUseCache ? generateRequestCacheKey(path, init) : null;

  // 尝试从缓存获取
  if (canUseCache && !forceRefresh && cacheKey) {
    const cached = globalCache.get(cacheKey);
    if (cached !== null) {
      return cached as ApiResponse<T>;
    }
  }

  // 使用去重器执行请求
  const requestKey = cacheKey || `${init.method || 'GET'}:${path}:${Date.now()}`;

  return globalDeduplicator.getOrCreate(requestKey, async (dedupeSignal) => {
    // 执行请求拦截器
    const processedInit = await interceptorManager.executeRequestInterceptors(init);
    return executeRequest<T>(
      path,
      processedInit,
      cacheKey,
      cacheTtl,
      canUseCache,
      timeout,
      dedupeSignal
    );
  });
}

/**
 * 执行实际请求（带重试逻辑）
 */
async function executeRequest<T>(
  path: string,
  processedInit: RequestInit,
  cacheKey: string | null,
  cacheTtl: number,
  canUseCache: boolean,
  timeout: number,
  dedupeSignal?: AbortSignal
): Promise<ApiResponse<T>> {
  let error: Error | null = null;
  const externalSignal = processedInit.signal;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    let abortedByCaller = false;
    const linkedSignals = [externalSignal, dedupeSignal].filter(
      (signal): signal is AbortSignal => signal !== undefined
    );
    const abortHandler = () => {
      abortedByCaller = true;
      controller.abort();
    };

    for (const signal of linkedSignals) {
      if (signal.aborted) {
        abortHandler();
        break;
      }
      signal.addEventListener('abort', abortHandler, { once: true });
    }

    try {
      const headers = withApiKeyHeader(processedInit.headers);
      if (processedInit.body !== undefined && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }

      const response = await fetch(`${API_BASE}${path}`, {
        ...processedInit,
        headers,
        signal: controller.signal,
      });

      const payload = await parseJsonResponse<T>(response);

      if (!response.ok) {
        const apiError = new ApiError(
          payload?.message || `HTTP ${response.status}`,
          payload?.code ?? response.status,
          response.status,
          payload
        );

        if (shouldRetry(response.status) && attempt < MAX_RETRIES) {
          await delay(RETRY_DELAY_MS * (attempt + 1));
          continue;
        }
        throw apiError;
      }

      validateResponseFormat(payload, response.status);

      // 缓存成功的响应
      if (canUseCache && cacheKey) {
        globalCache.set(cacheKey, payload, cacheTtl);
      }

      return payload;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        emitAuthRequired(err.message);
      }

      if (err instanceof Error && err.name === 'AbortError') {
        if (abortedByCaller) {
          throw normalizeAbortError(err);
        }
        error = new ApiError(`请求超时`, -1, 0);
      } else {
        error = err as Error;
      }

      if (err instanceof ApiError && shouldRetry(err.status) && attempt < MAX_RETRIES) {
        await delay(RETRY_DELAY_MS * (attempt + 1));
        continue;
      }

      throw error;
    } finally {
      clearTimeout(timeoutId);
      for (const signal of linkedSignals) {
        signal.removeEventListener('abort', abortHandler);
      }
    }
  }

  throw error || new ApiError('请求失败', -1, 0);
}

/**
 * 带缓存的 GET 请求
 */
export async function get<T>(
  path: string,
  options: Omit<RequestOptions, 'cache'> = {}
): Promise<ApiResponse<T>> {
  return request<T>(path, { method: 'GET' }, { cache: true, ...options });
}

/**
 * POST 请求（不缓存）
 */
export async function post<T>(
  path: string,
  body: unknown,
  options: Omit<RequestOptions, 'cache'> = {}
): Promise<ApiResponse<T>> {
  return request<T>(
    path,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    { cache: false, ...options }
  );
}

/**
 * PUT 请求（不缓存）
 */
export async function put<T>(
  path: string,
  body: unknown,
  options: Omit<RequestOptions, 'cache'> = {}
): Promise<ApiResponse<T>> {
  return request<T>(
    path,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
    { cache: false, ...options }
  );
}

/**
 * DELETE 请求（不缓存）
 */
export async function del<T>(
  path: string,
  options: Omit<RequestOptions, 'cache'> = {}
): Promise<ApiResponse<T>> {
  return request<T>(path, { method: 'DELETE' }, { cache: false, ...options });
}

/**
 * PATCH 请求（不缓存）
 */
export async function patch<T>(
  path: string,
  body: unknown,
  options: Omit<RequestOptions, 'cache'> = {}
): Promise<ApiResponse<T>> {
  return request<T>(
    path,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
    { cache: false, ...options }
  );
}

export function toQuery(
  params: Record<string, string | number | boolean | null | undefined>
): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }
    query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : '';
}

/**
 * 清除 HTTP 请求缓存
 * @param pattern 可选的 URL 匹配模式
 */
export function clearHttpCache(pattern?: string): void {
  if (!pattern) {
    globalCache.clearMatching((key) => isHttpCacheKey(key));
    return;
  }

  globalCache.clearMatching((key) => isHttpCacheKey(key) && key.includes(pattern));
}

/**
 * 取消所有进行中的 HTTP 请求
 */
export function cancelAllHttpRequests(): void {
  globalDeduplicator.cancelAll();
}
