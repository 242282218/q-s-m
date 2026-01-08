from fastapi import APIRouter, Query
from typing import Optional

from app.quark.services.search_service import SearchService

router = APIRouter(prefix="/quark", tags=["quark"])


@router.get("/search/tmdb/{tmdb_id}", summary="通过TMDB ID搜索夸克资源")
async def search_by_tmdb_id(
    tmdb_id: int,
    media_type: str = Query("movie", description="媒体类型，可选值：movie, tv"),
    max_results: int = Query(20, description="最大结果数量", ge=1, le=100)
):
    """
    通过TMDB ID搜索夸克资源
    
    Args:
        tmdb_id: TMDB ID
        media_type: 媒体类型（movie或tv）
        max_results: 最大结果数量
        
    Returns:
        搜索结果
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"API called: tmdb_id={tmdb_id}, media_type={media_type}, max_results={max_results}")
    service = SearchService()
    result = await service.search_by_tmdb_id(tmdb_id, max_results, media_type)
    logger.info(f"API returned: total={result.total}, resources={len(result.resources)}")
    return result


@router.get("/search/title", summary="通过标题搜索夸克资源")
async def search_by_title(
    title: str = Query(..., description="搜索标题"),
    year: Optional[int] = Query(None, description="年份"),
    max_results: int = Query(20, description="最大结果数量", ge=1, le=100)
):
    """
    通过标题搜索夸克资源
    
    Args:
        title: 搜索标题
        year: 年份（可选）
        max_results: 最大结果数量
        
    Returns:
        搜索结果
    """
    service = SearchService()
    return await service.search_by_title(title, year, max_results)