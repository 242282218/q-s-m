export type ISODateTime = string;

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** 游标分页（适用于大数据量列表） */
export interface CursorPagination {
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
  prev_cursor: string | null;
  total: number | null;
}

export interface HealthCheck {
  status: string;
  message: string;
}

export interface HealthData {
  status: string;
  service: string;
  timestamp: ISODateTime;
  checks: Record<string, HealthCheck>;
}

export interface RequestMetrics {
  total: number;
  avg_time: number;
  slow_requests_count: number;
}

export interface SlowQuery {
  duration: number;
  statement: string;
}

export interface DatabaseMetrics {
  total_queries: number;
  total_time: number;
  avg_time: number;
  slow_queries_count: number;
  recent_slow_queries: SlowQuery[];
}

export interface MetricsData {
  requests: RequestMetrics;
  database: DatabaseMetrics;
  timestamp: ISODateTime;
}

export interface TmdbDetailsData {
  poster_path: string | null;
  backdrop_path: string | null;
  title: string | null;
  year: number | null;
}

export interface DetailCastMember {
  id: number;
  name: string;
  character: string;
  profile_url: string | null;
}

export interface DetailVideo {
  key: string;
  name: string;
  type: string;
  official: boolean;
}

export interface DetailItem {
  id: number;
  media_type: string;
  title: string;
  year: number | null;
  genres: string[];
  runtime: number | null;
  vote: number | null;
  tagline: string;
  overview: string;
  poster_url: string | null;
  backdrop_url: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  cast: DetailCastMember[];
  videos: DetailVideo[];
}

export interface PosterCard {
  id: number;
  media_type: string;
  title: string;
  subtitle: string;
  overview: string;
  genres: number[];
  tone: string;
  poster_url: string | null;
  backdrop_url: string | null;
}

export interface DetailPageData {
  item: DetailItem;
  recommendations: PosterCard[];
}

export interface PersonCredit {
  id: number;
  media_type: string;
  title: string;
  year: string;
  role: string;
}

export interface PersonData {
  id: number;
  name: string;
  known_for: string;
  biography: string;
  birthday: string;
  place_of_birth: string;
  profile_url: string | null;
  top_credits: PosterCard[];
  all_credits: PersonCredit[];
}

export interface TmdbSearchData {
  query: string;
  posters: PosterCard[];
}

export interface SettingsUpdate {
  LOG_LEVEL?: string;
  API_KEY?: string;
  TMDB_API_KEY?: string;
  HTTP_PROXY?: string;
  QUARK_TRANSFER_COOKIE?: string;
  TRANSFER_KEEP_EXTRAS?: boolean;
  TRANSFER_KEEP_SUBTITLES?: boolean;
  TRANSFER_DRY_RUN?: boolean;
  TRANSFER_CLEANUP_ENABLED?: boolean;
  TRANSFER_CLEANUP_DELETE_NON_VIDEO?: boolean;
  TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO?: boolean;
  TRANSFER_CLEANUP_DELETE_EMPTY_DIRS?: boolean;
}

export interface SettingsUpdateData {
  updated_keys: string[];
  restart_required: boolean;
}

export interface SettingsCurrentData {
  LOG_LEVEL: string;
  HTTP_PROXY: string | null;
  TRANSFER_KEEP_EXTRAS: boolean;
  TRANSFER_KEEP_SUBTITLES: boolean;
  TRANSFER_DRY_RUN: boolean;
  TRANSFER_CLEANUP_ENABLED: boolean;
  TRANSFER_CLEANUP_DELETE_NON_VIDEO: boolean;
  TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: boolean;
  TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: boolean;
  API_KEY_CONFIGURED: boolean;
  API_KEY_MASKED: string | null;
  TMDB_API_KEY_CONFIGURED: boolean;
  TMDB_API_KEY_MASKED: string | null;
  QUARK_TRANSFER_COOKIE_CONFIGURED: boolean;
  QUARK_TRANSFER_COOKIE_MASKED: string | null;
}

export interface CollectionAddRequest {
  tmdb_id: number;
  media_type: string;
  title: string;
  year: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  share_url: string;
  share_pwd: string | null;
  file_structure: unknown;
  category: string | null;
}

export interface CollectionAddData {
  created: boolean;
  id: number | null;
}

export interface CollectionItem {
  id: number;
  tmdb_id: number;
  media_type: string;
  title: string;
  year: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  quark_share_url: string;
  category: string | null;
  status: number;
  saved_at: ISODateTime;
}

export interface CollectionListData {
  items: CollectionItem[];
  pagination: Pagination;
}

export interface CollectionListCursorData {
  items: CollectionItem[];
  pagination: CursorPagination;
}

export interface CollectionCheckLinksRequest {
  links: string[];
}

export interface CollectionLinkStatus {
  link: string;
  collected: boolean;
  id: number | null;
  status: number | null;
}

export interface CollectionCheckLinksData {
  results: CollectionLinkStatus[];
}

export interface CollectionVerifyResult {
  collection_id: number;
  title: string;
  previous_status: number;
  current_status: number;
  exists: boolean;
  checked_path: string;
  path_source: string;
}

export interface CollectionVerifySingleData {
  result: CollectionVerifyResult;
}

// ==================== Batch Operation Types ====================

export interface CollectionBatchAddRequest {
  items: CollectionAddRequest[];
}

export interface CollectionBatchAddResult {
  index: number;
  success: boolean;
  id: number | null;
  message: string;
}

export interface CollectionBatchAddData {
  total: number;
  success_count: number;
  failed_count: number;
  results: CollectionBatchAddResult[];
}

export interface CollectionBatchDeleteRequest {
  ids: number[];
}

export interface CollectionBatchDeleteResult {
  id: number;
  success: boolean;
  message: string;
}

export interface CollectionBatchDeleteData {
  total: number;
  success_count: number;
  failed_count: number;
  results: CollectionBatchDeleteResult[];
}

export interface TransferBatchItem {
  collection_id: number;
  target_folder: string | null;
  auto_rename: boolean;
}

export interface TransferBatchRequest {
  items: TransferBatchItem[];
}

export interface TransferBatchResult {
  collection_id: number;
  success: boolean;
  message: string;
  files: TransferredFile[];
}

export interface TransferBatchData {
  total: number;
  success_count: number;
  failed_count: number;
  results: TransferBatchResult[];
}

export interface TransferExecRequest {
  collection_id: number;
  target_folder: string | null;
  auto_rename: boolean;
}

export interface TransferredFile {
  fid: string | null;
  name: string | null;
  size: number | null;
  path: string | null;
}

export interface TransferExecData {
  success: boolean;
  files: TransferredFile[];
}

export interface RenameRequest {
  collection_id: number;
}

export interface MediaDto {
  tmdb_id: number;
  title: string;
  original_title: string;
  year: number | null;
  rating: number | null;
  overview: string;
  poster_path: string;
  backdrop_path: string;
  media_type: string;
}

export interface ResourceDto {
  name: string;
  link: string;
  overall_score: number;
  quality_level: string;
  resolution: string;
  codec: string;
  is_best: boolean;
  normalized_name: string | null;
  conf: number | null;
  qual: number | null;
  alpha: number | null;
  tags: string[] | null;
  size_gb: number | null;
  c_text: number | null;
  c_intent: number | null;
  c_plaus: number | null;
  p: number | null;
  r: number | null;
}

export interface SearchData {
  media: MediaDto | null;
  resources: ResourceDto[];
  total: number;
  query_time: number | null;
}

export interface HomePosterItem {
  id: number;
  media_type: string;
  title: string;
  subtitle: string;
  overview: string;
  genres: number[];
  tone: string;
  poster_url: string | null;
  backdrop_url: string | null;
}

export interface HomeHeroItem {
  id: number;
  media_type: string;
  title: string;
  year: number | null;
  genres: string[];
  runtime: number | null;
  vote: number | null;
  tagline: string;
  overview: string;
  poster_url: string | null;
  backdrop_url: string | null;
}

export interface HomeSectionMeta {
  key: string;
  title: string;
  tag: string | null;
}

export interface HomeData {
  hero_items: HomeHeroItem[];
  sections: Record<string, HomePosterItem[]>;
  section_order: HomeSectionMeta[];
  generated_at: ISODateTime;
}

export interface QuarkTransferData {
  saved_files: string[];
  task_id: string;
  collection_id: number | null;
  collection_created: boolean;
}

/**
 * SSE 事件数据负载（来自 build_event_payload）
 */
export interface SseEventData {
  type: string;
  current: number;
  total: number;
  percentage: number;
  message: string;
  level: string;
  [key: string]: unknown;
}

/**
 * SSE 信封（后端 SseEvent 模型）
 * 注意：这不是 ApiResponse 格式，而是独立的 SSE 事件结构
 */
export interface SseEnvelope {
  type: 'log' | 'progress' | 'complete' | 'error';
  data: SseEventData;
  timestamp: string;
  request_id: string | null;
  message: string | null;
  level: 'info' | 'warning' | 'error' | 'debug';
  code?: number | null;
}
