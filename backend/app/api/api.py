from fastapi import APIRouter

from .endpoints import home, settings, tmdb
from ..collection import routes as collection_routes
from ..transfer import routes as transfer_routes
from ..quark.api import routes as quark_routes

api_router = APIRouter()

api_router.include_router(tmdb.router, prefix="/tmdb", tags=["tmdb"])
api_router.include_router(home.router)
api_router.include_router(settings.api_router, prefix="/settings", tags=["settings"])
api_router.include_router(collection_routes.router)
api_router.include_router(transfer_routes.router)
api_router.include_router(quark_routes.router)
