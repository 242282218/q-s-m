from fastapi import APIRouter

from app.quark.api.routes import search

router = APIRouter()

# 包含搜索路由
router.include_router(search.router)