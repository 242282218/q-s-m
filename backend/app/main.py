import logging
import os
import time
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
from .middleware.rate_limit import rate_limit_middleware
from .core.config import get_settings
from .core.logging import setup_logging
from .db.session import init_db, get_query_stats, reset_query_stats
from .api.api import api_router
from .api.schemas.common import ApiResponse, ok, utc_now_iso
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    init_db()
    
    from .services.tmdb import TmdbClient
    from .quark.core.quark_client import AsyncQuarkAPIClient
    from .quark.core.cache import get_cache
    
    app.state.tmdb_client = TmdbClient(
        settings.tmdb_api_key,
        api_base=settings.tmdb_api_base,
        image_base=settings.tmdb_image_base,
        language=settings.default_language,
        proxy=settings.http_proxy,
    )
    
    app.state.quark_client = AsyncQuarkAPIClient()
    
    cache = get_cache()
    cache.start_cleanup()
    
    # 初始化性能统计
    # 使用固定大小的队列防止内存泄漏
    app.state.request_stats = {
        "total_requests": 0,
        "total_time": 0.0,
        "slow_requests": deque(maxlen=100)
    }
    
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
            # 只保留最近100条慢请求
            if len(request.app.state.request_stats["slow_requests"]) > 100:
                request.app.state.request_stats["slow_requests"].pop(0)
    
    # 添加性能相关的响应头
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = str(id(request))
    
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


@app.get("/api/v1/health", summary="健康检查", response_model=ApiResponse[HealthData])
async def health_check(request: Request) -> ApiResponse[HealthData]:
    """健康检查端点，用于容器健康监控"""
    checks = {}
    overall_status = "ok"
    
    # 检查数据库连接
    try:
        from .db.session import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        checks["database"] = HealthCheck(status="ok", message="Database connection successful")
    except Exception as e:
        checks["database"] = HealthCheck(status="error", message=f"Database connection failed: {str(e)}")
        overall_status = "degraded"
    
    # 检查 TMDB 客户端
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
    
    # 检查缓存
    try:
        from .quark.core.cache import get_cache
        cache = get_cache()
        stats = await cache.get_stats()
        if stats:
            checks["cache"] = HealthCheck(status="ok", message=f"Cache operational: {stats['valid']}/{stats['total']} entries")
        else:
            checks["cache"] = HealthCheck(status="warning", message="Cache stats not available")
    except Exception as e:
        checks["cache"] = HealthCheck(status="error", message=f"Cache error: {str(e)}")
        overall_status = "degraded"
    
    return ok(
        HealthData(
            status=overall_status,
            service="qsm-media-center",
            timestamp=utc_now_iso(),
            checks=checks,
        )
    )


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
        app.state.request_stats = {
            "total_requests": 0,
            "total_time": 0.0,
            "slow_requests": []
        }
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
