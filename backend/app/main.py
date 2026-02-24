import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware

from .core.config import get_settings
from .core.logging import setup_logging
from .db.session import init_db
from .api.api import api_router
from .api.endpoints.home import router as home_router
from .api.endpoints.settings import router as settings_router

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    init_db()
    yield

app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Mount static files
# backend/app/main.py -> backend/app/static
APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include API routers
app.include_router(api_router, prefix="/api")

# Include Home/Page router
app.include_router(home_router)
app.include_router(settings_router)

# Health Check
@app.get("/api/health", summary="健康检查")
async def health_check() -> dict:
    """健康检查端点，用于容器健康监控"""
    return {
        "status": "ok",
        "service": "qsm-media-center",
        "timestamp": datetime.utcnow().isoformat()
    }

# WebDAV Service
try:
    from wsgidav.wsgidav_app import WsgiDAVApp
    from .webdav.provider import QuarkDAVProvider
    
    user_mapping = {}
    if settings.quark_webdav_username and settings.quark_webdav_password:
        user_mapping = {
            settings.quark_webdav_username: {
                "password": settings.quark_webdav_password
            }
        }
    else:
        # Default to anonymous access if no credentials configured
        user_mapping = {"*": True}

    webdav_config = {
        "provider_mapping": {"/": QuarkDAVProvider(settings.quark_cookie)},
        "simple_dc": {"user_mapping": user_mapping},
        "verbose": 1,
        "logging": {
            "enable": True,
            "enable_loggers": [],
        },
    }
    webdav_app = WsgiDAVApp(webdav_config)
    app.mount("/webdav", WSGIMiddleware(webdav_app))
except ImportError:
    logger.warning("wsgidav not installed, WebDAV service disabled")
except Exception as e:
    logger.error(f"WebDAV service failed to initialize: {e}")

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )
