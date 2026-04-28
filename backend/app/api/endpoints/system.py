from __future__ import annotations

from collections import deque

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.schemas.common import ApiResponse, business_error, get_request_id, ok_with_request, utc_now_iso
from app.api.schemas.system import (
    DatabaseMetrics,
    HealthCheck,
    HealthData,
    MetricsData,
    MetricsResetData,
    RequestMetrics,
)
from app.db.session import get_query_stats, reset_query_stats

router = APIRouter(tags=["system"])

HEALTH_SERVICE_NAME = "qsm-media-center"


def build_request_stats_store() -> dict:
    return {
        "total_requests": 0,
        "total_time": 0.0,
        "slow_requests": deque(maxlen=100),
    }


def build_cache_health_check(stats: dict | None) -> tuple[HealthCheck, bool]:
    """
    兼容单层和多级缓存统计结构，避免因为统计字段层级变化导致误报异常。

    Returns:
        (health_check, should_degrade)
    """
    if not isinstance(stats, dict) or not stats:
        return HealthCheck(status="warning", message="Cache stats not available"), False

    cache_stats = stats.get("l1") if isinstance(stats.get("l1"), dict) else stats
    valid = cache_stats.get("valid")
    total = cache_stats.get("total")

    if isinstance(valid, int) and isinstance(total, int):
        return HealthCheck(status="ok", message=f"Cache operational: {valid}/{total} entries"), False

    available_keys = ", ".join(sorted(str(key) for key in cache_stats.keys()))
    message = "Cache stats format unavailable"
    if available_keys:
        message = f"{message}: {available_keys}"
    return HealthCheck(status="warning", message=message), True


async def collect_health_data(request: Request) -> tuple[HealthData, bool]:
    checks: dict[str, HealthCheck] = {}
    overall_status = "ok"
    is_ready = True

    try:
        from sqlalchemy import text
        from app.db.session import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = HealthCheck(status="ok", message="Database connection successful")
    except Exception as exc:
        checks["database"] = HealthCheck(status="error", message=f"Database connection failed: {str(exc)}")
        overall_status = "degraded"
        is_ready = False

    try:
        tmdb_client = getattr(request.app.state, "tmdb_client", None)
        if tmdb_client:
            checks["tmdb"] = HealthCheck(status="ok", message="TMDB client initialized")
        else:
            checks["tmdb"] = HealthCheck(status="warning", message="TMDB client not initialized")
            overall_status = "degraded"
    except Exception as exc:
        checks["tmdb"] = HealthCheck(status="error", message=f"TMDB client error: {str(exc)}")
        overall_status = "degraded"

    try:
        from app.quark.core.cache import get_cache

        cache = get_cache()
        stats = await cache.get_stats()
        checks["cache"], cache_should_degrade = build_cache_health_check(stats)
        if cache_should_degrade:
            overall_status = "degraded"
    except Exception as exc:
        checks["cache"] = HealthCheck(status="error", message=f"Cache error: {str(exc)}")
        overall_status = "degraded"

    return (
        HealthData(
            status=overall_status,
            service=HEALTH_SERVICE_NAME,
            timestamp=utc_now_iso(),
            checks=checks,
        ),
        is_ready,
    )


def build_liveness_data() -> HealthData:
    return HealthData(
        status="ok",
        service=HEALTH_SERVICE_NAME,
        timestamp=utc_now_iso(),
        checks={"app": HealthCheck(status="ok", message="Process running")},
    )


@router.get("/health", summary="健康检查", response_model=ApiResponse[HealthData])
async def health_check(request: Request) -> ApiResponse[HealthData]:
    """详细健康检查端点，供前端状态页和人工排障使用。"""
    health_data, _ = await collect_health_data(request)
    return ok_with_request(health_data, request)


@router.get("/health/live", summary="存活检查", response_model=ApiResponse[HealthData])
async def liveness_check(request: Request) -> ApiResponse[HealthData]:
    """轻量存活检查，仅确认进程仍可响应请求。"""
    return ok_with_request(build_liveness_data(), request, message="Service alive")


@router.get("/health/ready", summary="就绪检查", response_model=ApiResponse[HealthData])
async def readiness_check(request: Request) -> ApiResponse[HealthData] | JSONResponse:
    """
    就绪检查：
    - 保留详细健康数据，便于排障
    - 仅当核心依赖不可用时返回 503，供 Docker/K8s 探针使用
    """
    health_data, is_ready = await collect_health_data(request)
    if is_ready:
        return ok_with_request(health_data, request, message="Service ready")

    response = business_error(
        data=health_data,
        message="Service not ready",
        code=503,
        request_id=get_request_id(request),
    )
    return JSONResponse(status_code=503, content=response.model_dump(mode="json"))


@router.get("/metrics", summary="性能指标", response_model=ApiResponse[MetricsData])
async def get_metrics(request: Request) -> ApiResponse[MetricsData]:
    """获取应用性能指标"""
    stats = getattr(request.app.state, "request_stats", {})
    total_requests = stats.get("total_requests", 0)
    total_time = stats.get("total_time", 0.0)
    db_stats = get_query_stats()

    return ok_with_request(
        MetricsData(
            requests=RequestMetrics(
                total=total_requests,
                avg_time=round(total_time / max(total_requests, 1), 3),
                slow_requests_count=len(stats.get("slow_requests", [])),
            ),
            database=DatabaseMetrics(**db_stats),
            timestamp=utc_now_iso(),
        ),
        request,
    )


@router.post("/metrics/reset", summary="重置性能指标", response_model=ApiResponse[MetricsResetData])
async def reset_metrics(request: Request) -> ApiResponse[MetricsResetData]:
    """重置性能统计"""
    if hasattr(request.app.state, "request_stats"):
        request.app.state.request_stats = build_request_stats_store()
    reset_query_stats()
    return ok_with_request(
        MetricsResetData(reset=True, timestamp=utc_now_iso()),
        request,
        message="Metrics reset successfully",
    )
