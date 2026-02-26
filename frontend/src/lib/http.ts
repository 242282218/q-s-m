import type { ApiResponse } from "@/types/api";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  code: number;
  status: number;
  details?: unknown;

  constructor(message: string, code: number, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });

  let payload: ApiResponse<T> | null = null;
  try {
    payload = (await response.json()) as ApiResponse<T>;
  } catch {
    if (!response.ok) {
      throw new ApiError(`HTTP ${response.status}`, response.status, response.status);
    }
    throw new ApiError("响应不是合法 JSON", -1, response.status);
  }

  if (!response.ok) {
    throw new ApiError(payload?.message || `HTTP ${response.status}`, payload?.code ?? response.status, response.status, payload);
  }

  if (typeof payload.code !== "number" || typeof payload.message !== "string") {
    throw new ApiError("响应格式不符合约定", -1, response.status, payload);
  }

  return payload;
}

export function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

