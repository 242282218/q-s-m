import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings
from .core.logging import setup_logging
from .db.session import init_db
from .api.api import api_router
from .api.endpoints.home import router as home_router
from .api.endpoints.settings import router as settings_router

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title=settings.app_name, lifespan=lifespan)

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/api/health", summary="健康检查")
async def health_check() -> dict:
    """健康检查端点，用于容器健康监控"""
    return {
        "status": "ok",
        "service": "qsm-media-center",
        "timestamp": datetime.utcnow().isoformat()
    }

app.include_router(api_router, prefix="/api")
app.include_router(home_router)
app.include_router(settings_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    if settings.debug:
        return JSONResponse(
            status_code=500,
            content={"message": "Internal Server Error", "detail": str(exc)},
        )
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": "服务器内部错误，请稍后重试"},
    )
