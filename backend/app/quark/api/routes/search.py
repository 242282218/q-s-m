import logging
import re
from typing import Optional

from fastapi import APIRouter, Query, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.quark.core.transfer_client import QuarkTransferClient
from app.quark.services.search_service import SearchService
from app.services.tmdb import TmdbClient
from app.transfer.emby import (
    cleanup_non_video_files,
    collect_video_files,
    get_category_base_dir,
    reorganize_to_emby_structure,
    resolve_tmdb_naming_info,
    transfer_share_to_target_fid,
    wait_for_transfer_task,
)
from app.transfer.renamer import Renamer
from app.collection.service import CollectionService

router = APIRouter(prefix="/quark", tags=["quark"])
logger = logging.getLogger(__name__)


@router.get("/search/tmdb/{tmdb_id}", summary="通过TMDB ID搜索夸克资源")
async def search_by_tmdb_id(
    request: Request,
    tmdb_id: int,
    media_type: str = Query("movie", description="媒体类型，可选值：movie, tv"),
    max_results: int = Query(20, description="最大结果数量", ge=1, le=100)
):
    """
    通过TMDB ID搜索夸克资源
    """
    logger.info(f"API called: tmdb_id={tmdb_id}, media_type={media_type}, max_results={max_results}")

    quark_client = getattr(request.app.state, "quark_client", None)
    service = SearchService(quark_client=quark_client)

    result = await service.search_by_tmdb_id(tmdb_id, max_results, media_type)
    logger.info(f"API returned: total={result.total}, resources={len(result.resources)}")
    return result


@router.get("/search/title", summary="通过标题搜索夸克资源")
async def search_by_title(
    request: Request,
    title: str = Query(..., description="搜索标题"),
    year: Optional[int] = Query(None, description="年份"),
    max_results: int = Query(20, description="最大结果数量", ge=1, le=100)
):
    """
    通过标题搜索夸克资源
    """
    quark_client = getattr(request.app.state, "quark_client", None)
    service = SearchService(quark_client=quark_client)
    return await service.search_by_title(title, year, max_results)


def contains_chinese(text: str) -> bool:
    """检查是否包含中文字符"""
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fa5]", text))


def normalize_title_candidate(text: Optional[str]) -> Optional[str]:
    """标准化标题候选，去掉序号前缀和非法字符。"""
    if not text:
        return None
    renamer = Renamer()
    candidate = renamer.sanitize_filename(text)
    candidate = re.sub(r"^\d+\.\s*", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate or None


class TransferRequest(BaseModel):
    """转存请求"""
    link: str
    to_dir_fid: str = "0"
    to_dir_name: Optional[str] = None
    media_type: str = "movie"
    title: Optional[str] = None
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    resource_name: Optional[str] = None


def build_emby_folder_name(title: str, year: Optional[int], media_type: str) -> str:
    """向后兼容的目录名生成接口。"""
    del media_type
    renamer = Renamer()
    safe_title = renamer.sanitize_for_emby(title, ascii_only=False)
    if not safe_title:
        safe_title = renamer.sanitize_for_emby(title, ascii_only=True) or renamer.sanitize_filename(title)
    if year:
        return f"{safe_title} ({year})"
    return safe_title


def resolve_final_title(req: TransferRequest, tmdb_title: Optional[str]) -> Optional[str]:
    """
    选择最终标题，优先使用中文名称。
    优先级：TMDB 标题 > 请求标题 > 资源名 > 前端目录名。
    """
    candidates = [tmdb_title, req.title, req.resource_name, req.to_dir_name]
    for candidate in candidates:
        normalized = normalize_title_candidate(candidate)
        if normalized and contains_chinese(normalized):
            return normalized
    for candidate in candidates:
        normalized = normalize_title_candidate(candidate)
        if normalized:
            return normalized
    return None


@router.post("/transfer", summary="保存资源到网盘")
async def transfer_resource(
    request: Request,
    req: TransferRequest,
    db: Session = Depends(get_db),
):
    """
    保存分享资源到网盘并执行 Emby v1.6 规范重命名。
    """
    settings = get_settings()
    cookie = settings.quark_transfer_cookie or settings.quark_cookie
    renamer = Renamer()
    client = QuarkTransferClient(cookie)
    keep_extras = bool(settings.transfer_keep_extras)
    keep_subtitles = bool(settings.transfer_keep_subtitles)
    dry_run = bool(settings.transfer_dry_run)
    cleanup_enabled = bool(settings.transfer_cleanup_enabled)
    cleanup_delete_non_video = bool(settings.transfer_cleanup_delete_non_video)
    cleanup_delete_unselected_video = bool(settings.transfer_cleanup_delete_unselected_video)
    cleanup_delete_empty_dirs = bool(settings.transfer_cleanup_delete_empty_dirs)

    collection_id = None
    collection_created = False
    close_tmdb_client = False

    tmdb_client = getattr(request.app.state, "tmdb_client", None)
    if tmdb_client is None:
        tmdb_client = TmdbClient(
            settings.tmdb_api_key,
            api_base=settings.tmdb_api_base,
            image_base=settings.tmdb_image_base,
            language=settings.default_language,
            proxy=settings.http_proxy,
            timeout=8.0,
        )
        close_tmdb_client = True

    try:
        query_title = (
            normalize_title_candidate(req.title)
            or normalize_title_candidate(req.resource_name)
            or normalize_title_candidate(req.to_dir_name)
        )
        naming = await resolve_tmdb_naming_info(
            tmdb_client,
            renamer,
            media_type=req.media_type,
            tmdb_id=req.tmdb_id,
            title=query_title,
            year=req.year,
        )

        media_root_name = renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id, naming.media_type)
        base_dir = get_category_base_dir(naming.category)
        media_root_path = f"{base_dir}/{media_root_name}"

        media_root_fid = await client.get_fid_by_path(media_root_path)
        if not media_root_fid:
            return {
                "success": False,
                "message": f"创建目标目录失败: {media_root_path}",
                "saved_files": [],
                "task_id": "",
                "collection_id": None,
                "collection_created": False,
            }

        success, message, transferred_items, task_id = await transfer_share_to_target_fid(
            client=client,
            share_url=req.link,
            target_fid=media_root_fid,
            flatten_single_root=True,
        )
        if not success:
            return {
                "success": False,
                "message": message,
                "saved_files": [],
                "task_id": task_id,
                "collection_id": None,
                "collection_created": False,
            }

        task_done = await wait_for_transfer_task(client, task_id, max_retries=60, interval_seconds=1.0)
        if not task_done:
            logger.warning(f"转存任务等待超时: task_id={task_id}")

        reorganized_count = 0
        cleaned_count = 0
        planned_cleanup_count = 0

        video_files = await collect_video_files(client, media_root_fid, renamer)
        if not video_files:
            logger.warning("未识别到视频文件，跳过重组与清理")
        else:
            retained_fids = set()
            async for event in reorganize_to_emby_structure(
                client=client,
                root_fid=media_root_fid,
                root_path=media_root_path,
                video_files=video_files,
                renamer=renamer,
                title=naming.title,
                year=naming.year,
                media_type=naming.media_type,
                keep_extras=keep_extras,
                dry_run=dry_run,
            ):
                if event.get("type") == "complete":
                    reorganized_count = int(event.get("success", 0))
                    retained_fids.update(event.get("retained_fids") or [])
                elif event.get("level") == "error":
                    logger.warning(event.get("message", ""))
                else:
                    logger.info(event.get("message", ""))

            if cleanup_enabled:
                async for event in cleanup_non_video_files(
                    client=client,
                    root_fid=media_root_fid,
                    renamer=renamer,
                    protected_video_fids=retained_fids,
                    keep_subtitles=keep_subtitles,
                    dry_run=dry_run,
                    delete_non_video=cleanup_delete_non_video,
                    delete_unselected_videos=cleanup_delete_unselected_video,
                    delete_empty_dirs=cleanup_delete_empty_dirs,
                ):
                    if event.get("type") == "complete":
                        cleaned_count = int(event.get("deleted", 0))
                        planned_cleanup_count = int(event.get("planned", 0))
                    elif event.get("level") == "error":
                        logger.warning(event.get("message", ""))
                    else:
                        logger.info(event.get("message", ""))
            else:
                logger.info("清理阶段已关闭，跳过 cleanup")

        if naming.tmdb_id:
            collection_service = CollectionService(db)
            collection_media_type = "movie" if naming.media_type == "movie" else "tv"
            col_success, col_id, _ = collection_service.add(
                tmdb_id=naming.tmdb_id,
                media_type=collection_media_type,
                title=naming.title,
                share_url=req.link,
                year=naming.year,
                poster_path=req.poster_path,
                backdrop_path=req.backdrop_path,
                category=naming.category,
            )
            if col_success:
                collection_id = col_id
                collection_created = True
            elif col_id:
                collection_id = col_id

        status_msg = f"转存成功: {media_root_path}"
        if dry_run:
            status_msg += f"（DRY-RUN：重组计划 {reorganized_count}，清理计划 {planned_cleanup_count}）"
        else:
            status_msg += f"（重组成功 {reorganized_count}，清理 {cleaned_count}）"
        if not task_done:
            status_msg += "（任务仍在后台执行）"

        return {
            "success": True,
            "message": status_msg,
            "saved_files": [item.get("fid") for item in transferred_items if item.get("fid")],
            "task_id": task_id,
            "collection_id": collection_id,
            "collection_created": collection_created,
        }
    except Exception as e:
        logger.error(f"Transfer error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"转存异常: {str(e)}",
            "saved_files": [],
            "task_id": "",
            "collection_id": None,
            "collection_created": False,
        }
    finally:
        if close_tmdb_client:
            await tmdb_client.close()
        await client.close()
