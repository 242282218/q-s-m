"""
转存服务
协调 QuarkTransferClient、TMDB 与 Renamer 完成转存和云端重命名任务。
"""
import logging
from typing import Any, AsyncGenerator, Optional, List, Dict, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..core.config import get_settings
from ..services.tmdb import TmdbClient
from ..db.models import Collection, TransferHistory
from ..collection.service import CollectionService
from ..quark.core.transfer_client import QuarkTransferClient
from ..quark.core.path_resolver import QuarkPathResolver
from ..utils.events import build_event_payload
from .emby import (
    cleanup_non_video_files,
    collect_video_files,
    get_category_base_dir,
    reorganize_to_emby_structure,
    resolve_tmdb_naming_info,
    transfer_share_to_target_fid,
    wait_for_transfer_task,
)
from .renamer import Renamer
from app.core.constants import PATH_REPLACEMENTS

logger = logging.getLogger(__name__)


class TransferService:
    """转存服务"""

    def __init__(self, db: Session, cookie: str = "", tmdb_client: Optional["TmdbClient"] = None):
        self.db = db
        self._cookie = cookie
        self.renamer = Renamer()
        self.collection_service = CollectionService(db)
        self._quark_client: Optional[QuarkTransferClient] = None
        self._path_resolver: Optional[QuarkPathResolver] = None
        self._tmdb_client = tmdb_client

    async def _get_client(self) -> QuarkTransferClient:
        if self._quark_client is None or self._quark_client.cookie != self._cookie:
            if self._quark_client:
                await self._quark_client.close()
            self._quark_client = QuarkTransferClient(self._cookie)
            self._path_resolver = QuarkPathResolver(self._quark_client)
            logger.debug("创建新的 QuarkTransferClient 实例")
        return self._quark_client

    async def _get_path_resolver(self) -> QuarkPathResolver:
        client = await self._get_client()
        if self._path_resolver is None or self._path_resolver.client is not client:
            self._path_resolver = QuarkPathResolver(client)
        return self._path_resolver

    async def _find_fid_by_path_no_create(self, client: QuarkTransferClient, path: str) -> Optional[str]:
        resolver = await self._get_path_resolver()
        if resolver.client is not client:
            resolver = QuarkPathResolver(client)
            self._path_resolver = resolver
        return await resolver.find_fid_by_path_no_create(path)

    async def get_quark(self) -> QuarkTransferClient:
        """获取夸克客户端（异步方法）"""
        return await self._get_client()

    async def close(self) -> None:
        """关闭夸克客户端连接"""
        if self._quark_client:
            await self._quark_client.close()
            self._quark_client = None
            self._path_resolver = None
            logger.debug("QuarkTransferClient 连接已关闭")

    @staticmethod
    def _normalize_storage_path(path: str) -> str:
        normalized = path or ""
        for src, dst in PATH_REPLACEMENTS.items():
            normalized = normalized.replace(src, dst)
        return normalized

    async def validate_link(self, share_url: str) -> Tuple[bool, str, List[Dict]]:
        """
        验证分享链接有效性并获取文件列表
        """
        logger.info(f"验证分享链接: {share_url[:50]}...")

        try:
            client = await self._get_client()
            is_valid, pwd_id, stoken = await client.validate_share_link(share_url)

            if not is_valid:
                logger.warning(f"分享链接无效: {share_url[:50]}...")
                return False, "链接无效或已失效", []

            detail_resp = await client.get_detail(pwd_id, stoken, "0")
            if detail_resp.get("code") != 0:
                error_msg = detail_resp.get("message", "获取文件列表失败")
                logger.error(f"获取文件列表失败: {error_msg}")
                return False, error_msg, []

            files = []
            for f in detail_resp.get("data", {}).get("list", []):
                files.append({
                    "fid": f.get("fid"),
                    "name": f.get("file_name"),
                    "size": f.get("size", 0),
                    "is_dir": f.get("dir", False),
                })

            logger.info(f"链接验证成功，共 {len(files)} 个文件")
            return True, "链接有效", files
        except Exception as e:
            logger.error(f"验证链接异常: {e}", exc_info=True)
            return False, f"验证失败: {str(e)}", []

    async def transfer_collection(
        self,
        collection_id: int,
        target_folder: Optional[str] = None,
        auto_rename: bool = False,
    ) -> Tuple[bool, str, List[Dict]]:
        """
        转存收藏中的资源并按 Emby v1.6 命名规范重命名。
        """
        logger.info(f"开始转存: collection_id={collection_id}, auto_rename={auto_rename}")

        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            logger.warning(f"转存失败 - 收藏不存在: id={collection_id}")
            return False, "收藏不存在", []

        settings = get_settings()
        client = await self._get_client()
        tmdb_client = self._tmdb_client
        if tmdb_client is None:
            tmdb_client = TmdbClient(
                settings.tmdb_api_key,
                api_base=settings.tmdb_api_base,
                image_base=settings.tmdb_image_base,
                language=settings.default_language,
                proxy=settings.http_proxy,
                timeout=8.0,
            )

        try:
            keep_extras = bool(settings.transfer_keep_extras)
            keep_subtitles = bool(settings.transfer_keep_subtitles)
            dry_run = bool(settings.transfer_dry_run)
            cleanup_enabled = bool(settings.transfer_cleanup_enabled)
            cleanup_delete_non_video = bool(settings.transfer_cleanup_delete_non_video)
            cleanup_delete_unselected_video = bool(settings.transfer_cleanup_delete_unselected_video)
            cleanup_delete_empty_dirs = bool(settings.transfer_cleanup_delete_empty_dirs)

            naming = await resolve_tmdb_naming_info(
                tmdb_client,
                self.renamer,
                media_type=collection.category or collection.media_type,
                tmdb_id=collection.tmdb_id,
                title=collection.title,
                year=collection.year,
            )

            if target_folder:
                media_root_path = target_folder
            else:
                media_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id, naming.media_type)
                media_root_path = f"{get_category_base_dir(naming.category)}/{media_root_name}"

            media_root_fid = await client.get_fid_by_path(media_root_path)
            if not media_root_fid:
                return False, f"创建目标目录失败: {media_root_path}", []

            success, message, transferred_items, task_id = await transfer_share_to_target_fid(
                client=client,
                share_url=collection.quark_share_url,
                target_fid=media_root_fid,
                flatten_single_root=True,
            )
            if not success:
                self.collection_service.update_status(collection_id, 2)
                return False, message, []

            task_done = await wait_for_transfer_task(client, task_id, max_retries=60, interval_seconds=1.0)
            if not task_done:
                logger.warning(f"等待转存任务超时: task_id={task_id}")

            reorganized_count = 0
            cleaned_count = 0
            planned_cleanup_count = 0
            if auto_rename:
                video_files = await collect_video_files(client, media_root_fid, self.renamer)
                if not video_files:
                    logger.warning("未识别到视频文件，跳过重组与清理: collection_id=%s", collection_id)
                else:
                    retained_fids = set()
                    async for event in reorganize_to_emby_structure(
                        client=client,
                        root_fid=media_root_fid,
                        root_path=media_root_path,
                        video_files=video_files,
                        renamer=self.renamer,
                        title=naming.title,
                        year=naming.year,
                        media_type=naming.media_type,
                        keep_extras=keep_extras,
                        dry_run=dry_run,
                    ):
                        if event.get("type") == "complete":
                            reorganized_count = int(event.get("success", 0))
                            retained_fids.update(event.get("retained_fids") or [])
                        else:
                            level = event.get("level")
                            msg = event.get("message", "")
                            if level == "error":
                                logger.warning(msg)
                            else:
                                logger.info(msg)

                    if cleanup_enabled:
                        async for event in cleanup_non_video_files(
                            client=client,
                            root_fid=media_root_fid,
                            renamer=self.renamer,
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
                            else:
                                level = event.get("level")
                                msg = event.get("message", "")
                                if level == "error":
                                    logger.warning(msg)
                                else:
                                    logger.info(msg)
                    else:
                        logger.info("清理阶段已关闭，跳过 cleanup")

            ls_resp = await client.ls_dir(media_root_fid)
            saved_files = ls_resp.get("data", {}).get("list", []) if ls_resp.get("code") == 0 else []

            for f in saved_files:
                history = TransferHistory(
                    collection_id=collection_id,
                    quark_fid=f.get("fid", ""),
                    local_path=media_root_path,
                    file_name=f.get("file_name", ""),
                    file_size=f.get("size"),
                )
                self.db.add(history)

            collection.title = naming.title
            collection.year = naming.year
            collection.media_type = "movie" if naming.media_type == "movie" else "tv"
            collection.category = naming.category
            collection.status = 1
            self.db.commit()

            transferred_files = [
                {
                    "fid": item.get("fid"),
                    "name": item.get("file_name") or item.get("name"),
                    "size": item.get("size"),
                    "path": media_root_path,
                }
                for item in (saved_files or transferred_items)
                if item.get("fid")
            ]

            status_msg = f"转存成功: {media_root_path}"
            if auto_rename:
                if dry_run:
                    status_msg += f"（DRY-RUN：重组计划 {reorganized_count}，清理计划 {planned_cleanup_count}）"
                else:
                    status_msg += f"（重组成功 {reorganized_count}，清理 {cleaned_count}）"
            if not task_done:
                status_msg += "（任务仍在后台执行）"

            logger.info(
                f"转存成功: id={collection_id}, tmdb_id={collection.tmdb_id}, "
                f"category={naming.category}, files={len(transferred_files)}"
            )
            return True, status_msg, transferred_files
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"转存失败 - 数据库错误: id={collection_id}, error={e}")
            return False, "转存失败: 数据库错误", []
        except Exception as e:
            self.db.rollback()
            logger.error(f"转存失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            return False, f"转存失败: {str(e)}", []
        finally:
            if self._tmdb_client is None:
                await tmdb_client.close()

    async def rename_collection(self, collection_id: int) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"开始独立重命名: collection_id={collection_id}")

        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            yield build_event_payload(
                event_type="error",
                message="收藏不存在",
                level="error",
            )
            return

        if collection.status != 1:
            yield build_event_payload(
                event_type="error",
                message="该收藏尚未转存，无法重命名",
                level="error",
            )
            return

        settings = get_settings()
        client = await self._get_client()
        tmdb_client = self._tmdb_client
        if tmdb_client is None:
            tmdb_client = TmdbClient(
                settings.tmdb_api_key,
                api_base=settings.tmdb_api_base,
                image_base=settings.tmdb_image_base,
                language=settings.default_language,
                proxy=settings.http_proxy,
                timeout=8.0,
            )

        try:
            keep_extras = bool(settings.transfer_keep_extras)
            keep_subtitles = bool(settings.transfer_keep_subtitles)
            dry_run = bool(settings.transfer_dry_run)
            cleanup_enabled = bool(settings.transfer_cleanup_enabled)
            cleanup_delete_non_video = bool(settings.transfer_cleanup_delete_non_video)
            cleanup_delete_unselected_video = bool(settings.transfer_cleanup_delete_unselected_video)
            cleanup_delete_empty_dirs = bool(settings.transfer_cleanup_delete_empty_dirs)

            naming = await resolve_tmdb_naming_info(
                tmdb_client,
                self.renamer,
                media_type=collection.category or collection.media_type,
                tmdb_id=collection.tmdb_id,
                title=collection.title,
                year=collection.year,
            )

            latest_record = (
                self.db.query(TransferHistory)
                .filter(TransferHistory.collection_id == collection_id)
                .order_by(TransferHistory.transferred_at.desc())
                .first()
            )

            if latest_record and latest_record.local_path:
                media_root_path = self._normalize_storage_path(latest_record.local_path)
            else:
                media_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id, naming.media_type)
                media_root_path = f"{get_category_base_dir(naming.category)}/{media_root_name}"

            expected_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id, naming.media_type)
            expected_root_path = f"{get_category_base_dir(naming.category)}/{expected_root_name}"

            if media_root_path != expected_root_path:
                current_root_fid = await self._find_fid_by_path_no_create(client, media_root_path)
                expected_root_fid = await self._find_fid_by_path_no_create(client, expected_root_path)
                if expected_root_fid:
                    media_root_path = expected_root_path
                elif current_root_fid:
                    renamed_root = await client.rename(current_root_fid, expected_root_name)
                    if renamed_root:
                        old_path = media_root_path
                        media_root_path = expected_root_path
                        (
                            self.db.query(TransferHistory)
                            .filter(TransferHistory.collection_id == collection_id)
                            .update({"local_path": media_root_path}, synchronize_session=False)
                        )
                        self.db.commit()
                        yield build_event_payload(
                            event_type="log",
                            message=f"根目录改名: {old_path} -> {media_root_path}",
                            level="info",
                        )

            media_root_fid = await self._find_fid_by_path_no_create(client, media_root_path)
            if not media_root_fid:
                yield build_event_payload(
                    event_type="error",
                    message=f"未找到已转存目录: {media_root_path}",
                    level="error",
                )
                return

            collection.title = naming.title
            collection.year = naming.year
            collection.media_type = "movie" if naming.media_type == "movie" else "tv"
            collection.category = naming.category
            self.db.commit()

            yield build_event_payload(
                event_type="log",
                message=f"定位目录: {media_root_path}",
                level="info",
            )

            video_files = await collect_video_files(client, media_root_fid, self.renamer)
            if not video_files:
                yield build_event_payload(
                    event_type="log",
                    message="未识别到视频文件，跳过重组与清理",
                    level="warning",
                )
                return

            retained_fids = set()
            async for event in reorganize_to_emby_structure(
                client=client,
                root_fid=media_root_fid,
                root_path=media_root_path,
                video_files=video_files,
                renamer=self.renamer,
                title=naming.title,
                year=naming.year,
                media_type=naming.media_type,
                keep_extras=keep_extras,
                dry_run=dry_run,
            ):
                if event.get("type") == "complete":
                    retained_fids.update(event.get("retained_fids") or [])
                yield event

            if cleanup_enabled:
                async for event in cleanup_non_video_files(
                    client=client,
                    root_fid=media_root_fid,
                    renamer=self.renamer,
                    protected_video_fids=retained_fids,
                    keep_subtitles=keep_subtitles,
                    dry_run=dry_run,
                    delete_non_video=cleanup_delete_non_video,
                    delete_unselected_videos=cleanup_delete_unselected_video,
                    delete_empty_dirs=cleanup_delete_empty_dirs,
                ):
                    yield event
            else:
                yield build_event_payload(
                    event_type="log",
                    message="清理阶段已关闭，跳过 cleanup",
                    level="info",
                )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"重命名失败 - 数据库错误: id={collection_id}, error={e}")
            yield build_event_payload(
                event_type="error",
                message="重命名失败: 数据库错误",
                level="error",
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"重命名失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            yield build_event_payload(
                event_type="error",
                message=f"重命名失败: {str(e)}",
                level="error",
            )
        finally:
            if self._tmdb_client is None:
                await tmdb_client.close()

    def _get_target_folder(self, collection: Collection) -> str:
        """
        向后兼容：根据收藏信息确定目标目录。
        """
        category = collection.category or collection.media_type
        base_dir = get_category_base_dir(category)
        title = self.renamer.sanitize_for_emby(collection.title, ascii_only=False)
        if not title:
            title = self.renamer.sanitize_for_emby(collection.title, ascii_only=True)
        folder_name = f"{title} ({collection.year})" if collection.year else title
        if collection.tmdb_id:
            folder_name = f"{folder_name} [tmdbid={collection.tmdb_id}]"
        return f"{base_dir}/{folder_name}"
