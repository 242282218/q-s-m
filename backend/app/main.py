"""
Compatibility entrypoint.

Why:
    `uvicorn app.main:app` and the existing test suite still import from this module.
    The actual application assembly now lives in `app.app_factory` so `main.py`
    can stay small while preserving the public entrypoint.
"""

from .api.endpoints.system import (
    build_liveness_data,
    build_request_stats_store,
    collect_health_data,
    get_metrics,
    health_check,
    liveness_check,
    readiness_check,
    reset_metrics,
)
from .app_factory import (
    RequestIDMiddleware,
    app,
    build_error_detail_from_qsm_exception,
    create_app,
    frontend_entry,
    frontend_fallback,
    frontend_index_response,
    global_exception_handler,
    http_exception_handler,
    lifespan,
    mount_static_assets,
    performance_monitoring,
    dynamic_cors_middleware,
    qsm_exception_handler,
    register_exception_handlers,
    register_frontend_routes,
    register_middleware,
    resolve_frontend_dist_dir,
    validation_exception_handler,
)

__all__ = [
    "RequestIDMiddleware",
    "app",
    "build_error_detail_from_qsm_exception",
    "build_liveness_data",
    "build_request_stats_store",
    "collect_health_data",
    "create_app",
    "frontend_entry",
    "frontend_fallback",
    "frontend_index_response",
    "get_metrics",
    "global_exception_handler",
    "health_check",
    "http_exception_handler",
    "lifespan",
    "liveness_check",
    "mount_static_assets",
    "performance_monitoring",
    "dynamic_cors_middleware",
    "qsm_exception_handler",
    "readiness_check",
    "register_exception_handlers",
    "register_frontend_routes",
    "register_middleware",
    "reset_metrics",
    "resolve_frontend_dist_dir",
    "validation_exception_handler",
]
