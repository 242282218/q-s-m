import type { ApiResponse } from "@/types/api";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

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

async function parseJsonResponse<T>(response: Response): Promise<ApiResponse<T>> {
  const contentType = response.headers.get("content-type");
  const isJson = contentType?.includes("application/json") ?? false;

  try {
    return (await response.json()) as ApiResponse<T>;
  } catch (parseError) {
    const errorMessage = isJson
      ? `JSON 解析失败: ${parseError instanceof Error ? parseError.message : "未知错误"}`
      : `期望 JSON 响应，但收到 ${contentType || "未知类型"}`;

    if (!response.ok) {
      throw new ApiError(
        `HTTP ${response.status} - ${errorMessage}`,
        response.status,
        response.status,
      );
    }

    throw new ApiError(errorMessage, -1, response.status, {
      contentType,
      url: response.url,
    });
  }
}

function validateResponseFormat<T>(payload: ApiResponse<T>, status: number): void {
  if (typeof payload.code !== "number" || typeof payload.message !== "string") {
    throw new ApiError("响应格式不符合约定", -1, status, payload);
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 30000,
): Promise<ApiResponse<T>> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });

    const payload = await parseJsonResponse<T>(response);

    if (!response.ok) {
      throw new ApiError(
        payload?.message || `HTTP ${response.status}`,
        payload?.code ?? response.status,
        response.status,
        payload,
      );
    }

    validateResponseFormat(payload, response.status);

    return payload;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError(`请求超时（${timeoutMs}ms）`, -1, 0);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
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

