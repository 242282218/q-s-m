from typing import Optional

from fastapi import APIRouter, Query

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


# ==================== 转存路由 ====================
import re
from typing import Optional
from pydantic import BaseModel
from app.core.config import get_settings
from app.transfer.quark_client import QuarkTransferClient
from app.services.tmdb import TmdbClient


def contains_chinese(text: str) -> bool:
    """检查是否包含中文字符"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9fa5]', text))


async def get_chinese_title(client: TmdbClient, title: str, year: Optional[int], media_type: str) -> Optional[str]:
    """
    通过TMDB查询中文标题
    """
    try:
        if media_type == "movie":
            results = await client.search_movies(query=title, year=year)
        else:
            results = await client.search_tv(query=title, year=year)
        
        # 查找匹配项
        for item in results:
            # 简单的年份匹配验证（如果提供了年份）
            item_date = item.get("release_date") or item.get("first_air_date")
            item_year = int(item_date.split("-")[0]) if item_date else None
            
            if year and item_year and abs(item_year - year) > 1:
                continue
                
            # 返回中文标题 (TMDB默认返回请求语言的标题，我们在client中设置了zh-CN)
            # 但有些条目只有英文名，所以再次检查
            cn_title = item.get("title") or item.get("name")
            if cn_title and contains_chinese(cn_title):
                return cn_title
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"TMDB search failed: {e}")
    
    return None


class TransferRequest(BaseModel):
    """转存请求"""
    link: str
    to_dir_fid: str = "0"
    to_dir_name: Optional[str] = None
    media_type: str = "movie"  # movie 或 tv
    title: Optional[str] = None
    year: Optional[int] = None


@router.post("/transfer", summary="保存资源到网盘")
async def transfer_resource(request: TransferRequest):
    """
    保存分享资源到网盘
    
    Args:
        link: 夸克分享链接
        to_dir_fid: 目标目录ID（默认根目录）
        to_dir_name: 资源名称（用于创建子目录）
        media_type: 媒体类型（movie/tv，用于分类）
        
    Returns:
        转存结果
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 根据 media_type 构建目标路径: /收藏TV/Movies 或 /收藏TV/TV Shows
    category_dirs = {
        'movie': 'Movies',
        'tv': 'TV Shows',
        'anime': 'Anime',
        'documentary': 'Documentary',
    }
    category_dir = category_dirs.get(request.media_type, 'Movies')
    
    # 构建完整目录名: /收藏TV/Movies/资源名
    if request.to_dir_name:
        full_dir_name = f"/收藏TV/{category_dir}/{request.to_dir_name}"
    else:
        full_dir_name = f"/收藏TV/{category_dir}"
    
    logger.info(f"Transfer request: link={request.link}, target_dir={full_dir_name}")
    
    settings = get_settings()
    client = QuarkTransferClient(settings.quark_cookie)
    
    try:
        success, message, files = await client.transfer_share(
            share_url=request.link,
            target_dir=full_dir_name
        )
        
        saved_files = [f["fid"] for f in files]
        
        # 自动重命名
        renamed_count = 0
        if success and request.title:
            from app.transfer.renamer import Renamer
            renamer = Renamer()
            
            # 优化标题：始终尝试获取中文名（标准化命名）
            final_title = request.title
            try:
                tmdb_client = TmdbClient(
                    settings.tmdb_api_key, 
                    api_base=settings.tmdb_api_base,
                    proxy=settings.http_proxy,  # 传入显式配置的代理
                    timeout=5.0  # 设置短超时，避免卡顿
                )
                cn_title = await get_chinese_title(
                    tmdb_client, 
                    request.title, 
                    request.year, 
                    request.media_type
                )
                await tmdb_client.close()
                
                if cn_title:
                    final_title = cn_title
                    logger.info(f"Using Chinese title: {cn_title} (was {request.title})")
            except Exception as e:
                logger.warning(f"Failed to get chinese title: {e}")
            
            logger.info(f"Rename logic: original_title='{request.title}', year={request.year}, contains_chinese={contains_chinese(request.title)}, final_title='{final_title}'")
            
            for f in files:
                # 只处理视频文件
                if not renamer.is_video_file(f["name"]):
                    continue
                
                # 生成新文件名
                rename_result = renamer.generate_path(
                    original_filename=f["name"],
                    title=final_title,
                    year=request.year,
                    media_type=request.media_type,
                    category=request.media_type
                )
                
                if rename_result.new_name != f["name"]:
                    try:
                        await client.rename(f["fid"], rename_result.new_name)
                        renamed_count += 1
                        logger.info(f"Renamed: {f['name']} -> {rename_result.new_name}")
                    except Exception as e:
                        logger.error(f"Rename failed for {f['name']}: {str(e)}")
                else:
                    logger.info(f"Skipping rename for {f['name']}: new name {rename_result.new_name} matches original")
        
        message = f"{message} (已重命名 {renamed_count} 个文件)" if renamed_count > 0 else message
        
        result = {
            "success": success,
            "message": message,
            "saved_files": saved_files,
            "task_id": ""
        }
    except Exception as e:
        logger.error(f"Transfer error: {str(e)}")
        result = {
            "success": False,
            "message": f"转存异常: {str(e)}",
            "saved_files": []
        }
    
    logger.info(f"Transfer result: success={result.get('success')}, message={result.get('message')}")
    return result