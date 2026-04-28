import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .api.endpoints.system import build_request_stats_store
from .api.router import api_router
from .api.schemas.common import ErrorDetail, business_error, get_request_id, utc_now_iso
from .core.config import emit_security_warnings, get_settings
from .core.exceptions import QSMException
from .core.logging import setup_logging
from .db.session import init_db

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
emit_security_warnings(settings)


def resolve_frontend_dist_dir(app_dir: Path) -> Path:
    env_path = os.getenv("FRONTEND_DIST_DIR")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            app_dir.parent.parent / "frontend" / "dist",
            app_dir.parent / "frontend" / "dist",
            app_dir.parent / "dist",
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

    from .quark.core.cache import get_cache
    from .quark.core.quark_client import AsyncQuarkAPIClient
    from .services.tmdb import TmdbClient

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
    app.state.request_stats = build_request_stats_store()

    logger.info("Application started: HTTP clients and cache initialized")

    yield

    if hasattr(app.state, "tmdb_client") and app.state.tmdb_client:
        await app.state.tmdb_client.close()
        logger.info("TmdbClient closed")

    if hasattr(app.state, "quark_client") and app.state.quark_client:
        await app.state.quark_client.close()
        logger.info("QuarkAPIClient closed")

    await cache.stop_cleanup()
    logger.info("Application shutdown complete")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Request ID 中间件
    - 自动生成唯一的 request_id
    - 注入到请求状态中供后续使用
    - 添加到响应头中便于追踪
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def build_error_detail_from_qsm_exception(exc: QSMException) -> ErrorDetail:
    field = None
    value = None
    reason = exc.message
    merged_context: dict | None = None

    if exc.context is not None:
        field = exc.context.field
        value = exc.context.value
        reason = exc.context.reason or exc.message
        if exc.context.extra:
            merged_context = dict(exc.context.extra)

    if exc.details:
        if merged_context is None:
            merged_context = {}
        merged_context.update(exc.details)

    return ErrorDetail(
        field=field,
        value=value,
        reason=reason,
        context=merged_context,
    )


def frontend_index_response() -> FileResponse:
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Frontend dist not found, expected index at: {FRONTEND_INDEX_FILE}",
        )
    return FileResponse(str(FRONTEND_INDEX_FILE))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        response = business_error(
            data=None,
            message=message,
            code=exc.status_code,
            error=ErrorDetail(reason=message),
            request_id=get_request_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    @app.exception_handler(QSMException)
    async def qsm_exception_handler(request: Request, exc: QSMException):
        response = business_error(
            data=exc.data,
            message=exc.message,
            code=int(exc.code),
            error=build_error_detail_from_qsm_exception(exc),
            request_id=get_request_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = exc.errors()
        first_error = details[0] if details else {}
        loc = first_error.get("loc") if isinstance(first_error, dict) else None
        field = loc[-1] if isinstance(loc, (list, tuple)) and loc else None
        response = business_error(
            data=details,
            message="Validation Error",
            code=422,
            error=ErrorDetail(
                field=str(field) if field is not None else None,
                value=first_error.get("input") if isinstance(first_error, dict) else None,
                reason=first_error.get("msg") if isinstance(first_error, dict) else "request validation failed",
                context={"errors": details},
            ),
            request_id=get_request_id(request),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global exception: {exc}", exc_info=True)
        error = ErrorDetail(
            reason="unhandled exception",
            context={"detail": str(exc)} if settings.debug else None,
        )
        response = business_error(
            data={"detail": str(exc)} if settings.debug else None,
            message="Internal Server Error",
            code=500,
            error=error,
            request_id=get_request_id(request),
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))

    globals().update(
        {
            "http_exception_handler": http_exception_handler,
            "qsm_exception_handler": qsm_exception_handler,
            "validation_exception_handler": validation_exception_handler,
            "global_exception_handler": global_exception_handler,
        }
    )


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,
        compresslevel=6,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    from .middleware.rate_limit import rate_limit_middleware

    app.middleware("http")(rate_limit_middleware)

    @app.middleware("http")
    async def performance_monitoring(request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        if hasattr(request.app.state, "request_stats"):
            request.app.state.request_stats["total_requests"] += 1
            request.app.state.request_stats["total_time"] += process_time
            if process_time > 1.0:
                request.app.state.request_stats["slow_requests"].append(
                    {
                        "path": request.url.path,
                        "method": request.method,
                        "time": round(process_time, 3),
                        "timestamp": utc_now_iso(),
                    }
                )

        response.headers["X-Process-Time"] = str(process_time)
        if hasattr(request.state, "request_id"):
            response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/static/") or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    globals()["performance_monitoring"] = performance_monitoring


def register_frontend_routes(app: FastAPI) -> None:
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

    globals().update(
        {
            "frontend_entry": frontend_entry,
            "frontend_fallback": frontend_fallback,
        }
    )


def mount_static_assets(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if FRONTEND_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")
    else:
        logger.warning("Frontend assets directory not found: %s", FRONTEND_ASSETS_DIR)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )
    register_middleware(app)
    register_exception_handlers(app)
    mount_static_assets(app)
    app.include_router(api_router, prefix="/api/v1")
    register_frontend_routes(app)
    return app


APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
FRONTEND_DIST_DIR = resolve_frontend_dist_dir(APP_DIR)
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"

app = create_app()
