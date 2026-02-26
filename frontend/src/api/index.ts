import { consumeSse } from "@/lib/sse";
import { request, toQuery } from "@/lib/http";
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

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function getHealth() {
  return request<HealthData>("/health");
}

export function getMetrics() {
  return request<MetricsData>("/metrics");
}

export function getHomeFeed() {
  return request<HomeData>("/home");
}

export function getCollections(page: number, pageSize: number) {
  return request<CollectionListData>(
    `/collection/list${toQuery({ page, limit: pageSize, sort_by: "saved_at", order: "desc" })}`,
  );
}

export function deleteCollection(id: number) {
  return request<{ deleted: boolean }>(`/collection/${id}`, { method: "DELETE" });
}

export function transferCollection(payload: TransferExecRequest) {
  return request<TransferExecData>("/transfer/exec", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function verifySingleCollection(id: number) {
  return request<CollectionVerifySingleData>(`/collection/verify/${id}`, {
    method: "POST",
  });
}

export function validateLink(payload: ValidateLinkRequest) {
  return request<ValidateLinkData>("/transfer/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSettings(payload: SettingsUpdate) {
  return request<SettingsUpdateData>("/settings/update", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function searchByTmdb(tmdbId: number, mediaType: string, maxResults = 100) {
  return request<SearchData>(
    `/quark/search/tmdb/${tmdbId}${toQuery({ media_type: mediaType, max_results: maxResults })}`,
  );
}

export function searchByTitle(title: string, year?: number, maxResults = 100) {
  return request<SearchData>(
    `/quark/search/title${toQuery({ title, year: year ?? null, max_results: maxResults })}`,
  );
}

export function checkLinks(payload: CollectionCheckLinksRequest) {
  return request<CollectionCheckLinksData>("/collection/check-links", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function addCollection(payload: CollectionAddRequest) {
  return request<CollectionAddData>("/collection/add", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

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

export function getTmdbDetails(mediaType: string, tmdbId: number) {
  return request<TmdbDetailsData>(
    `/tmdb/details${toQuery({ media_type: mediaType, tmdb_id: tmdbId })}`,
  );
}

export function getDetailPageData(mediaType: string, itemId: number) {
  return request<DetailPageData>(`/tmdb/detail/${mediaType}/${itemId}`);
}

export function getPersonPageData(personId: number) {
  return request<PersonData>(`/tmdb/person/${personId}`);
}

export function searchTmdbPosters(query: string) {
  return request<TmdbSearchData>(`/tmdb/search${toQuery({ q: query })}`);
}

async function startSse<T>(
  path: string,
  body: T,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  await consumeSse(response, onEnvelope);
}

export function startRenameSse(
  payload: RenameRequest,
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal,
) {
  return startSse("/transfer/rename", payload, onEnvelope, signal);
}

export function startVerifySse(
  payload: { collection_ids?: number[] | null },
  onEnvelope: (envelope: SseEnvelope) => void,
  signal?: AbortSignal,
) {
  return startSse("/collection/verify", payload, onEnvelope, signal);
}

export type ApiEnvelope<T> = ApiResponse<T>;
