import { consumeSse } from "@/lib/sse";
import { ApiError, API_BASE, request, toQuery } from "@/lib/http";
import type {
  ApiResponse,
  CollectionAddData,
  CollectionAddRequest,
  CollectionCheckLinksData,
  CollectionCheckLinksRequest,
  CollectionListData,
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
  SettingsUpdate,
  SettingsUpdateData,
  SseEnvelope,
  TmdbDetailsData,
  TransferExecData,
  TransferExecRequest,
  ValidateLinkData,
  ValidateLinkRequest,
} from "@/types/api";

const cache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5分钟

async function cachedRequest<T>(key: string, fetcher: () => Promise<ApiResponse<T>>): Promise<ApiResponse<T>> {
  const cached = cache.get(key);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data as ApiResponse<T>;
  }
  
  const result = await fetcher();
  cache.set(key, { data: result, timestamp: Date.now() });
  return result;
}

/**
 * 获取服务健康状态
 * @returns 服务健康信息
 */
export function getHealth() {
  return request<HealthData>("/health");
}

/**
 * 获取系统指标数据
 * @returns 请求和数据库性能指标
 */
export function getMetrics() {
  return request<MetricsData>("/metrics");
}

/**
 * 获取首页推荐数据
 * @returns 包含轮播图和内容分区的首页数据
 */
export function getHomeFeed() {
  return cachedRequest<HomeData>("/home", () => request<HomeData>("/home"));
}

/**
 * 获取收藏列表
 * @param page - 页码（从1开始）
 * @param pageSize - 每页数量
 * @returns 分页的收藏列表
 */
export function getCollections(page: number, pageSize: number) {
  return request<CollectionListData>(
    `/collection/list${toQuery({ page, limit: pageSize, sort_by: "saved_at", order: "desc" })}`,
  );
}

/**
 * 删除指定收藏
 * @param id - 收藏ID
 * @returns 删除结果
 */
export function deleteCollection(id: number) {
  return request<{ deleted: boolean }>(`/collection/${id}`, { method: "DELETE" });
}

/**
 * 执行转存操作
 * @param payload - 转存请求参数
 * @returns 转存执行结果
 */
export function transferCollection(payload: TransferExecRequest) {
  return request<TransferExecData>("/transfer/exec", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * 验证单个收藏的网盘状态
 * @param id - 收藏ID
 * @returns 验证结果
 */
export function verifySingleCollection(id: number) {
  return request<CollectionVerifySingleData>(`/collection/verify/${id}`, {
    method: "POST",
  });
}

/**
 * 验证分享链接有效性
 * @param payload - 链接验证请求
 * @returns 链接有效性及文件列表
 */
export function validateLink(payload: ValidateLinkRequest) {
  return request<ValidateLinkData>("/transfer/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * 更新系统设置
 * @param payload - 设置更新参数
 * @returns 更新结果及是否需要重启
 */
export function updateSettings(payload: SettingsUpdate) {
  return request<SettingsUpdateData>("/settings/update", {
    method: "POST",
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
    `/quark/search/tmdb/${tmdbId}${toQuery({ media_type: mediaType, max_results: maxResults })}`,
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
    `/quark/search/title${toQuery({ title, year: year ?? null, max_results: maxResults })}`,
  );
}

/**
 * 批量检查链接的收藏状态
 * @param payload - 链接列表
 * @returns 每个链接的收藏状态
 */
export function checkLinks(payload: CollectionCheckLinksRequest) {
  return request<CollectionCheckLinksData>("/collection/check-links", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * 添加新收藏
 * @param payload - 收藏信息
 * @returns 创建结果
 */
export function addCollection(payload: CollectionAddRequest) {
  return request<CollectionAddData>("/collection/add", {
    method: "POST",
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
  return request<QuarkTransferData>("/quark/transfer", {
    method: "POST",
    body: JSON.stringify({
      to_dir_fid: "0",
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
    `/tmdb/details${toQuery({ media_type: mediaType, tmdb_id: tmdbId })}`,
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
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "网络请求失败";
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
  signal?: AbortSignal,
) {
  return startSse("/transfer/rename", payload, onEnvelope, signal);
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
  signal?: AbortSignal,
) {
  return startSse("/collection/verify", payload, onEnvelope, signal);
}
