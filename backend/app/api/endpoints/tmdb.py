from fastapi import APIRouter, HTTPException, Depends
import httpx
import logging

from ...services.tmdb import TmdbClient
from ...core.config import get_settings, Settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency to get TmdbClient
def get_tmdb_client(settings: Settings = Depends(get_settings)) -> TmdbClient:
    return TmdbClient(
        settings.tmdb_api_key,
        api_base=settings.tmdb_api_base,
        image_base=settings.tmdb_image_base,
        language=settings.default_language,
    )

@router.get("/details", summary="获取TMDB详情")
async def get_tmdb_details(
    media_type: str, 
    tmdb_id: int,
    tmdb_client: TmdbClient = Depends(get_tmdb_client)
):
    """
    获取TMDB详情，用于获取海报等信息
    
    - **media_type**: 媒体类型 (movie 或 tv)
    - **tmdb_id**: TMDB ID
    """
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
    finally:
        await tmdb_client.close()
