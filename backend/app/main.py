import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import emit_security_warnings, get_settings
from .core.logging import setup_logging
from .db.session import init_db, get_query_stats, reset_query_stats
from .api.router import api_router
from .api.schemas.common import ApiResponse, business_error, ok, utc_now_iso
from .api.schemas.system import (
    DatabaseMetrics,
    HealthData,
    HealthCheck,
    MetricsData,
    MetricsResetData,
    RequestMetrics,
)

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
emit_security_warnings(settings)

HEALTH_SERVICE_NAME = "qsm-media-center"


def resolve_frontend_dist_dir(app_dir: Path) -> Path:
    env_path = os.getenv("FRONTEND_DIST_DIR")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            app_dir.parent.parent / "frontend" / "dist",  # local repo layout
            app_dir.parent / "frontend" / "dist",  # container layout: /app/frontend/dist
            app_dir.parent / "dist",  # fallback
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def build_request_stats_store() -> dict:
    return {
        "total_requests": 0,
        "total_time": 0.0,
        "slow_requests": deque(maxlen=100),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    init_db()
    
    from .services.tmdb import TmdbClient
    from .quark.core.quark_client import AsyncQuarkAPIClient
    from .quark.core.cache import get_cache
    
    app.state.tmdb_client = None
    if settings.tmdb_api_key:
        app.state.tmdb_client = TmdbClient(
            settings.tmdb_api_key,
            api_base=settings.tmdb_api_base,
            image_base=settings.tmdb_image_base,
            language=settings.default_language,
            proxy=settings.http_proxy,
        )
    else:
        logger.warning("TMDB_API_KEY not configured; TMDB-dependent endpoints are disabled")
    
    app.state.quark_client = AsyncQuarkAPIClient()
    
    cache = get_cache()
    cache.start_cleanup()
    
    # 初始化性能统计
    # 使用固定大小的队列防止内存泄漏
    app.state.request_stats = build_request_stats_store()
    
    logger.info("Application started: HTTP clients and cache initialized")
    
    yield
    
    if hasattr(app.state, 'tmdb_client') and app.state.tmdb_client:
        await app.state.tmdb_client.close()
        logger.info("TmdbClient closed")
    
    if hasattr(app.state, 'quark_client') and app.state.quark_client:
        await app.state.quark_client.close()
        logger.info("QuarkAPIClient closed")
    
    await cache.stop_cleanup()
    
    logger.info("Application shutdown complete")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# 添加 Gzip 压缩中间件 - 压缩响应数据减少传输时间
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,  # 只压缩大于 1KB 的响应
    compresslevel=6,    # 压缩级别 (1-9)
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Request ID 中间件
    - 自动生成唯一的 request_id
    - 注入到请求状态中供后续使用
    - 添加到响应头中便于追踪
    """
    async def dispatch(self, request: Request, call_next):
        # 从请求头获取或生成新的 request_id
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # 存储到请求状态中
        request.state.request_id = request_id
        
        # 调用下一个中间件或路由
        response = await call_next(request)
        
        # 添加到响应头
        response.headers["X-Request-ID"] = request_id
        
        return response


# 添加 Request ID 中间件
app.add_middleware(RequestIDMiddleware)

# 添加速率限制中间件
from .middleware.rate_limit import rate_limit_middleware
app.middleware("http")(rate_limit_middleware)




@app.middleware("http")
async def performance_monitoring(request: Request, call_next: Callable) -> Response:
    """
    性能监控中间件
    - 记录请求耗时
    - 记录慢请求
    - 添加响应头
    """
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    
    # 更新统计
    if hasattr(request.app.state, "request_stats"):
        request.app.state.request_stats["total_requests"] += 1
        request.app.state.request_stats["total_time"] += process_time
        
        # 记录慢请求 (>1秒)
        if process_time > 1.0:
            request.app.state.request_stats["slow_requests"].append({
                "path": request.url.path,
                "method": request.method,
                "time": round(process_time, 3),
                "timestamp": utc_now_iso(),
            })
    
    # 添加性能相关的响应头
    response.headers["X-Process-Time"] = str(process_time)
    
    # 使用中间件生成的 request_id
    if hasattr(request.state, "request_id"):
        response.headers["X-Request-ID"] = request.state.request_id
    
    # 静态资源添加缓存头
    if request.url.path.startswith("/static/") or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=86400"  # 24小时缓存
    
    return response


# 挂载静态文件
APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
FRONTEND_DIST_DIR = resolve_frontend_dist_dir(APP_DIR)
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")
else:
    logger.warning("Frontend assets directory not found: %s", FRONTEND_ASSETS_DIR)


def frontend_index_response() -> FileResponse:
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Frontend dist not found, expected index at: {FRONTEND_INDEX_FILE}",
        )
    return FileResponse(str(FRONTEND_INDEX_FILE))


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
        from .db.session import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = HealthCheck(status="ok", message="Database connection successful")
    except Exception as e:
        checks["database"] = HealthCheck(status="error", message=f"Database connection failed: {str(e)}")
        overall_status = "degraded"
        is_ready = False

    try:
        tmdb_client = getattr(request.app.state, "tmdb_client", None)
        if tmdb_client:
            checks["tmdb"] = HealthCheck(status="ok", message="TMDB client initialized")
        else:
            checks["tmdb"] = HealthCheck(status="warning", message="TMDB client not initialized")
            overall_status = "degraded"
    except Exception as e:
        checks["tmdb"] = HealthCheck(status="error", message=f"TMDB client error: {str(e)}")
        overall_status = "degraded"

    try:
        from .quark.core.cache import get_cache

        cache = get_cache()
        stats = await cache.get_stats()
        checks["cache"], cache_should_degrade = build_cache_health_check(stats)
        if cache_should_degrade:
            overall_status = "degraded"
    except Exception as e:
        checks["cache"] = HealthCheck(status="error", message=f"Cache error: {str(e)}")
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


@app.get("/api/v1/health", summary="健康检查", response_model=ApiResponse[HealthData])
async def health_check(request: Request) -> ApiResponse[HealthData]:
    """详细健康检查端点，供前端状态页和人工排障使用。"""
    health_data, _ = await collect_health_data(request)
    return ok(health_data)


@app.get("/api/v1/health/live", summary="存活检查", response_model=ApiResponse[HealthData])
async def liveness_check() -> ApiResponse[HealthData]:
    """轻量存活检查，仅确认进程仍可响应请求。"""
    return ok(build_liveness_data(), message="Service alive")


@app.get("/api/v1/health/ready", summary="就绪检查", response_model=ApiResponse[HealthData])
async def readiness_check(request: Request) -> ApiResponse[HealthData] | JSONResponse:
    """
    就绪检查：
    - 保留详细健康数据，便于排障
    - 仅当核心依赖不可用时返回 503，供 Docker/K8s 探针使用
    """
    health_data, is_ready = await collect_health_data(request)
    if is_ready:
        return ok(health_data, message="Service ready")

    response = business_error(
        data=health_data,
        message="Service not ready",
        code=503,
    )
    return JSONResponse(status_code=503, content=response.model_dump(mode="json"))


@app.get("/api/v1/metrics", summary="性能指标", response_model=ApiResponse[MetricsData])
async def get_metrics() -> ApiResponse[MetricsData]:
    """获取应用性能指标"""
    stats = getattr(app.state, "request_stats", {})
    total_requests = stats.get("total_requests", 0)
    total_time = stats.get("total_time", 0.0)
    
    # 获取数据库查询统计
    db_stats = get_query_stats()
    
    return ok(
        MetricsData(
            requests=RequestMetrics(
                total=total_requests,
                avg_time=round(total_time / max(total_requests, 1), 3),
                slow_requests_count=len(stats.get("slow_requests", [])),
            ),
            database=DatabaseMetrics(**db_stats),
            timestamp=utc_now_iso(),
        )
    )


@app.post("/api/v1/metrics/reset", summary="重置性能指标", response_model=ApiResponse[MetricsResetData])
async def reset_metrics() -> ApiResponse[MetricsResetData]:
    """重置性能统计"""
    if hasattr(app.state, "request_stats"):
        app.state.request_stats = build_request_stats_store()
    reset_query_stats()
    return ok(
        MetricsResetData(reset=True, timestamp=utc_now_iso()),
        message="Metrics reset successfully",
    )


# 注册路由 - 添加版本控制
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
@app.get("/collection", include_in_schema=False)
@app.get("/collections", include_in_schema=False)
@app.get("/search", include_in_schema=False)
@app.get("/settings", include_in_schema=False)
@app.get("/movie/{item_id}", include_in_schema=False)
@app.get("/tv/{item_id}", include_in_schema=False)
@app.get("/person/{person_id}", include_in_schema=False)
async def frontend_entry(item_id: int | None = None, person_id: int | None = None) -> FileResponse:
    _ = (item_id, person_id)
    return frontend_index_response()


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_fallback(full_path: str) -> FileResponse:
    if full_path.startswith(("api", "static", "assets")):
        raise HTTPException(status_code=404, detail="Not Found")
    if "." in Path(full_path).name:
        raise HTTPException(status_code=404, detail="Not Found")
    return frontend_index_response()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    _ = request
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": message, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    _ = request
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "Validation Error", "data": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"Global exception: {exc}", exc_info=True)
    if settings.debug:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "Internal Server Error", "data": {"detail": str(exc)}},
        )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "Internal Server Error", "data": None},
    )
