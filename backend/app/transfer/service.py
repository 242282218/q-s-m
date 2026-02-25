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
from ..utils.events import build_event_payload
from .emby import (
    ensure_season_directories,
    get_category_base_dir,
    rename_saved_tree_to_emby,
    resolve_tmdb_naming_info,
    transfer_share_to_target_fid,
    wait_for_transfer_task,
)
from .renamer import Renamer

logger = logging.getLogger(__name__)

PATH_REPLACEMENTS = {
    "/鏀惰棌TV/Movies": "/影视收藏/电影",
    "/鏀惰棌TV/TV Shows": "/影视收藏/电视剧",
    "/鏀惰棌TV/Anime": "/影视收藏/动漫",
    "/收藏TV/Movies": "/影视收藏/电影",
    "/收藏TV/TV Shows": "/影视收藏/电视剧",
    "/收藏TV/Anime": "/影视收藏/动漫",
}


class TransferService:
    """转存服务"""

    def __init__(self, db: Session, cookie: str = ""):
        self.db = db
        self._cookie = cookie
        self.renamer = Renamer()
        self.collection_service = CollectionService(db)
        self._quark_client: Optional[QuarkTransferClient] = None

    async def _get_client(self) -> QuarkTransferClient:
        if self._quark_client is None or self._quark_client.cookie != self._cookie:
            if self._quark_client:
                await self._quark_client.close()
            self._quark_client = QuarkTransferClient(self._cookie)
            logger.debug("创建新的 QuarkTransferClient 实例")
        return self._quark_client

    async def _find_fid_by_path_no_create(self, client: QuarkTransferClient, path: str) -> Optional[str]:
        normalized = (path or "").strip()
        if not normalized or normalized == "/":
            return "0"
        parts = [p for p in normalized.split("/") if p]
        current_fid = "0"
        for part in parts:
            ls_resp = await client.ls_dir(current_fid)
            if ls_resp.get("code") != 0:
                return None
            next_fid = None
            for item in ls_resp.get("data", {}).get("list", []) or []:
                name = item.get("file_name") or item.get("name")
                if name == part and ((item.get("dir") is True) or (item.get("dir") == 1)):
                    next_fid = item.get("fid")
                    break
            if not next_fid:
                return None
            current_fid = next_fid
        return current_fid

    async def get_quark(self) -> QuarkTransferClient:
        """获取夸克客户端（异步方法）"""
        return await self._get_client()

    async def close(self) -> None:
        """关闭夸克客户端连接"""
        if self._quark_client:
            await self._quark_client.close()
            self._quark_client = None
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
        tmdb_client = TmdbClient(
            settings.tmdb_api_key,
            api_base=settings.tmdb_api_base,
            image_base=settings.tmdb_image_base,
            language=settings.default_language,
            proxy=settings.http_proxy,
            timeout=8.0,
        )

        try:
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
                media_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id)
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

            renamed_count = 0
            if auto_rename:
                async for event in rename_saved_tree_to_emby(
                    client=client,
                    root_fid=media_root_fid,
                    renamer=self.renamer,
                    title=naming.title,
                    year=naming.year,
                    media_type=naming.media_type,
                ):
                    if event.get("type") == "complete":
                        renamed_count = int(event.get("success", 0))

            if naming.media_type == "tv":
                await ensure_season_directories(client, media_root_path, naming.season_count, self.renamer)

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
            if auto_rename and renamed_count > 0:
                status_msg += f"（已重命名 {renamed_count} 个文件/目录）"
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
        tmdb_client = TmdbClient(
            settings.tmdb_api_key,
            api_base=settings.tmdb_api_base,
            image_base=settings.tmdb_image_base,
            language=settings.default_language,
            proxy=settings.http_proxy,
            timeout=8.0,
        )

        try:
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
                media_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id)
                media_root_path = f"{get_category_base_dir(naming.category)}/{media_root_name}"

            expected_root_name = self.renamer.build_media_root_name(naming.title, naming.year, naming.tmdb_id)
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

            if naming.media_type == "tv":
                await ensure_season_directories(client, media_root_path, naming.season_count, self.renamer)

            async for event in rename_saved_tree_to_emby(
                client=client,
                root_fid=media_root_fid,
                renamer=self.renamer,
                title=naming.title,
                year=naming.year,
                media_type=naming.media_type,
            ):
                yield event
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
