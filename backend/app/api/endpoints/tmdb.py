from fastapi import APIRouter, HTTPException, Request
import httpx
import logging

from ...services.tmdb import TmdbClient

router = APIRouter()
logger = logging.getLogger(__name__)


def get_tmdb_client(request: Request) -> TmdbClient:
    """从应用状态获取共享的 TmdbClient 实例"""
    return request.app.state.tmdb_client


@router.get("/details", summary="获取TMDB详情")
async def get_tmdb_details(
    request: Request,
    media_type: str, 
    tmdb_id: int,
):
    """
    获取TMDB详情，用于获取海报等信息
    
    - **media_type**: 媒体类型 (movie 或 tv)
    - **tmdb_id**: TMDB ID
    """
    if tmdb_id <= 0:
        raise HTTPException(status_code=400, detail="TMDB ID 必须为正整数")
    
    tmdb_client = get_tmdb_client(request)
    try:
        logger.info(f"获取TMDB详情: media_type={media_type}, tmdb_id={tmdb_id}")
        data = await tmdb_client.details(media_type, tmdb_id)
        logger.info(f"TMDB详情获取成功: {data.get('title') or data.get('name')}")
        return {
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "title": data.get("title") or data.get("name"),
            "year": data.get("release_date", "").split("-")[0] if data.get("release_date") else data.get("first_air_date", "").split("-")[0] if data.get("first_air_date") else None
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"TMDB API HTTP错误: {e.response.status_code} - {e.response.text}")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="TMDB 资源不存在")
        raise HTTPException(status_code=502, detail=f"TMDB API错误: {e.response.status_code}")
    except httpx.ConnectError as e:
        logger.error(f"TMDB API连接错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"无法连接到TMDB API: {str(e)}")
    except httpx.TimeoutException as e:
        logger.error(f"TMDB API超时错误: {str(e)}")
        raise HTTPException(status_code=504, detail=f"TMDB API请求超时: {str(e)}")
    except Exception as e:
        logger.error(f"获取TMDB详情失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取TMDB详情失败: {str(e)}")
