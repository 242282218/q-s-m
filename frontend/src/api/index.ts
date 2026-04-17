import { consumeSse } from '@/shared/lib/sse';
import { withApiKeyHeader } from '@/shared/lib/api-key';
import { ApiError, API_BASE, request, toQuery } from '@/shared/lib/http';
import { globalCache } from '@/composables/useApiCache';
import type {
  CollectionAddData,
  CollectionAddRequest,
  CollectionBatchAddData,
  CollectionBatchAddRequest,
  CollectionBatchDeleteData,
  CollectionBatchDeleteRequest,
  CollectionCheckLinksData,
  CollectionCheckLinksRequest,
  CollectionListData,
  CollectionListCursorData,
  CollectionVerifySingleData,
  DetailPageData,
  HealthData,
  HomeData,
  MetricsData,
  PersonData,
  TmdbSearchData,
  QuarkTransferData,
  RenameRequest,
  SearchData,
  SettingsCurrentData,
  SettingsUpdate,
  SettingsUpdateData,
  SseEnvelope,
  TmdbDetailsData,
  TransferBatchData,
  TransferBatchRequest,
  TransferExecData,
  TransferExecRequest,
} from '@/types/api';

const HOME_FEED_CACHE_TTL = 5 * 60 * 1000;

export const enhancedCache = globalCache;

export function getCacheStats() {
  return globalCache.getStats();
}

/**
 * 获取服务健康状态
 * @returns 服务健康信息
 */
export function getHealth() {
  return request<HealthData>('/health');
}

/**
 * 获取系统指标数据
 * @returns 请求和数据库性能指标
 */
export function getMetrics() {
  return request<MetricsData>('/metrics');
}

/**
 * 获取当前生效的系统设置（敏感字段仅返回掩码）
 * @returns 当前设置快照
 */
export function getSettings() {
  return request<SettingsCurrentData>('/settings');
}

export function getSettingsWithApiKey(apiKey: string) {
  return request<SettingsCurrentData>('/settings', {
    headers: { 'X-API-Key': apiKey },
  });
}

/**
 * 获取首页推荐数据
 * @returns 包含轮播图和内容分区的首页数据
 */
export function getHomeFeed() {
  return request<HomeData>('/home', {}, { cacheTtl: HOME_FEED_CACHE_TTL });
}

/**
 * 获取收藏列表（传统页码分页）
 * @param page - 页码（从1开始）
 * @param pageSize - 每页数量（最大100）
 * @returns 分页的收藏列表
 */
export function getCollections(page: number, pageSize: number) {
  // 限制 pageSize 最大为 100
  const limit = Math.min(pageSize, 100);
  return request<CollectionListData>(
    `/collections${toQuery({ page, limit, sort_by: 'saved_at', order: 'desc' })}`
  );
}

/**
 * 获取收藏列表（游标分页）
 * @param cursor - 游标（用于分页定位）
 * @param limit - 每页数量（最大100）
 * @returns 游标分页的收藏列表
 */
export function getCollectionsCursor(cursor?: string | null, limit: number = 20) {
  // 限制 limit 最大为 100
  const pageSize = Math.min(limit, 100);
  const params: Record<string, string | number> = {
    limit: pageSize,
    sort_by: 'saved_at',
    order: 'desc',
  };
  if (cursor) {
    params.cursor = cursor;
  }
  return request<CollectionListCursorData>(`/collections/cursor${toQuery(params)}`);
}

/**
 * 删除指定收藏
 * @param id - 收藏ID
 * @returns 删除结果
 */
export function deleteCollection(id: number) {
  return request<{ deleted: boolean }>(`/collections/${id}`, { method: 'DELETE' });
}

/**
 * 执行转存操作
 * @param payload - 转存请求参数
 * @returns 转存执行结果
 */
export function transferCollection(payload: TransferExecRequest) {
  return request<TransferExecData>(`/transfers/${payload.collection_id}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * 验证单个收藏的网盘状态
 * @param id - 收藏ID
 * @returns 验证结果
 */
export function verifySingleCollection(id: number) {
  return request<CollectionVerifySingleData>(`/collections/verify/${id}`, {
    method: 'POST',
  });
}

/**
 * 更新系统设置
 * @param payload - 设置更新参数
 * @returns 更新结果及是否需要重启
 */
export function updateSettings(payload: SettingsUpdate) {
  return request<SettingsUpdateData>('/settings/update', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateSettingsWithApiKey(payload: SettingsUpdate, apiKey: string) {
  return request<SettingsUpdateData>('/settings/update', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(payload),
  });
}

/**
 * 通过TMDB ID搜索资源
 * @param tmdbId - TMDB影片ID
 * @param mediaType - 媒体类型（movie/tv）
 * @param maxResults - 最大返回结果数，默认100
 * @returns 搜索结果
 */
export function searchByTmdb(tmdbId: number, mediaType: string, maxResults = 100) {
  return request<SearchData>(
    `/quark/searches/tmdb/${tmdbId}${toQuery({ media_type: mediaType, max_results: maxResults })}`
  );
}

/**
 * 通过标题搜索资源
 * @param title - 影片标题
 * @param year - 发行年份（可选）
 * @param maxResults - 最大返回结果数，默认100
 * @returns 搜索结果
 */
export function searchByTitle(title: string, year?: number, maxResults = 100) {
  return request<SearchData>(
    `/quark/searches/by-title${toQuery({ title, year: year ?? null, max_results: maxResults })}`
  );
}

/**
 * 批量检查链接的收藏状态
 * @param payload - 链接列表
 * @returns 每个链接的收藏状态
 */
export function checkLinks(payload: CollectionCheckLinksRequest) {
  return request<CollectionCheckLinksData>('/collections/by-links/check', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * 添加新收藏
 * @param payload - 收藏信息
 * @returns 创建结果
 */
export function addCollection(payload: CollectionAddRequest) {
  return request<CollectionAddData>('/collections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * 保存资源到网盘
 * @param payload - 资源信息
 * @returns 保存结果
 */
export function saveResource(payload: {
  link: string;
  media_type: string;
  title: string;
  year?: number | null;
  tmdb_id?: number | null;
  poster_path?: string | null;
  backdrop_path?: string | null;
  resource_name?: string | null;
  to_dir_name?: string | null;
}) {
  return request<QuarkTransferData>('/quark/transfer', {
    method: 'POST',
    body: JSON.stringify({
      to_dir_fid: '0',
      ...payload,
    }),
  });
}

/**
 * 获取TMDB影片详情
 * @param mediaType - 媒体类型（movie/tv）
 * @param tmdbId - TMDB影片ID
 * @returns 影片海报和背景图信息
 */
export function getTmdbDetails(mediaType: string, tmdbId: number) {
  return request<TmdbDetailsData>(
    `/tmdb/details${toQuery({ media_type: mediaType, tmdb_id: tmdbId })}`
  );
}

/**
 * 获取影片详情页完整数据
 * @param mediaType - 媒体类型（movie/tv）
 * @param itemId - 影片ID
 * @returns 详情页数据，包含影片信息和推荐
 */
export function getDetailPageData(mediaType: string, itemId: number) {
  return request<DetailPageData>(`/tmdb/detail/${mediaType}/${itemId}`);
}

/**
 * 获取演员详情页数据
 * @param personId - 演员ID
 * @returns 演员信息和作品列表
 */
export function getPersonPageData(personId: number) {
  return request<PersonData>(`/tmdb/person/${personId}`);
}

/**
 * 搜索TMDB海报
 * @param query - 搜索关键词
 * @returns 海报搜索结果
 */
export function searchTmdbPosters(query: string) {
  return request<TmdbSearchData>(`/tmdb/search${toQuery({ q: query })}`);
}

/**
 * 启动SSE流式请求（内部函数）
 * @param path - API路径
 * @param body - 请求体
 * @param onEnvelope - 消息回调函数
 * @param signal - 用于取消请求的AbortSignal
 */
async function startSse<T>(
  path: string,
  body: T,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal
): Promise<void> {
  let response: Response;
  try {
    const headers = withApiKeyHeader({ 'Content-Type': 'application/json' });
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error instanceof DOMException ? error : new DOMException(error.message, 'AbortError');
    }
    const message = error instanceof Error ? error.message : '网络请求失败';
    throw new ApiError(message, -1, 0);
  }

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    let errorCode = response.status;
    let errorDetails: unknown;

    try {
      const errorData = await response.json();
      errorMessage = errorData?.message || errorMessage;
      errorCode = errorData?.code ?? response.status;
      errorDetails = errorData;
    } catch {
      // 响应体不是 JSON，使用默认错误信息
    }

    throw new ApiError(errorMessage, errorCode, response.status, errorDetails);
  }

  await consumeSse(response, onEnvelope);
}

/**
 * 启动重命名SSE任务
 * @param payload - 重命名请求参数
 * @param onEnvelope - 消息回调函数
 * @param signal - 用于取消请求的AbortSignal
 */
export function startRenameSse(
  payload: RenameRequest,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal
) {
  const path = `/transfers/${payload.collection_id}/rename`;
  return startSse(path, payload, onEnvelope, signal);
}

/**
 * 启动验证网盘状态SSE任务
 * @param payload - 验证请求参数（可选指定收藏ID列表）
 * @param onEnvelope - 消息回调函数
 * @param signal - 用于取消请求的AbortSignal
 */
export function startVerifySse(
  payload: { collection_ids?: number[] | null },
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal
) {
  return startSse('/collections/verify', payload, onEnvelope, signal);
}

/**
 * 批量添加收藏
 * @param payload - 批量添加请求
 * @returns 批量添加结果
 */
export function batchAddCollections(payload: CollectionBatchAddRequest) {
  return request<CollectionBatchAddData>('/collections/batch', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * 批量删除收藏
 * @param payload - 批量删除请求
 * @returns 批量删除结果
 */
export function batchDeleteCollections(payload: CollectionBatchDeleteRequest) {
  return request<CollectionBatchDeleteData>('/collections/batch', {
    method: 'DELETE',
    body: JSON.stringify(payload),
  });
}

/**
 * 启动批量添加收藏SSE任务
 * @param payload - 批量添加请求
 * @param onEnvelope - 消息回调函数
 * @param signal - 用于取消请求的AbortSignal
 */
export function startBatchAddSse(
  payload: CollectionBatchAddRequest,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal
) {
  return startSse('/collections/batch/sse', payload, onEnvelope, signal);
}

/**
 * 批量转存
 * @param payload - 批量转存请求
 * @returns 批量转存结果
 */
export function batchTransfer(payload: TransferBatchRequest) {
  return request<TransferBatchData>('/transfers/batch', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * 启动批量转存SSE任务
 * @param payload - 批量转存请求
 * @param onEnvelope - 消息回调函数
 * @param signal - 用于取消请求的AbortSignal
 */
export function startBatchTransferSse(
  payload: TransferBatchRequest,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal
) {
  return startSse('/transfers/batch/sse', payload, onEnvelope, signal);
}
