"""
转存服务（重构版）
协调转存、重命名、清理服务完成转存任务

架构改进:
- 2026-03-09: 拆分为 TransferService（协调）、RenameService、CleanupService
- 添加分布式锁支持
- 统一异常处理
"""
import logging
import asyncio
from typing import Any, AsyncGenerator, Optional, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..core.config import get_settings
from ..core.exceptions import TransferException, QuarkException
from ..core.error_codes import ErrorCode, ErrorContext
from ..core.distributed_lock import get_distributed_lock
from ..services.tmdb import TmdbClient
from ..db.models import Collection, TransferHistory
from ..collection.service import CollectionService
from ..quark.core.transfer_client import QuarkTransferClient
from ..quark.core.path_resolver import QuarkPathResolver
from ..quark.services.rename_service import RenameService
from ..quark.services.cleanup_service import CleanupService
from ..utils.events import build_event_payload
from .emby import (
    get_category_base_dir,
    resolve_tmdb_naming_info,
    transfer_share_to_target_fid,
    wait_for_transfer_task,
)
from .renamer import Renamer
from app.core.constants import PATH_REPLACEMENTS

logger = logging.getLogger(__name__)


def raise_transfer_failure(
    message: str,
    *,
    collection_id: int | None = None,
    target_folder: str | None = None,
    share_url: str | None = None,
    reason: str | None = None,
    data: dict | list | None = None,
) -> None:
    if "收藏不存在" in message:
        raise TransferException(
            message,
            code=ErrorCode.COLLECTION_NOT_FOUND,
            context=ErrorContext(field="collection_id", value=collection_id, reason=reason or message),
            data=data,
        )

    if "未配置 QUARK_TRANSFER_COOKIE" in message:
        raise TransferException(
            message,
            code=ErrorCode.CONFIG_ERROR,
            context=ErrorContext(field="QUARK_TRANSFER_COOKIE", reason="missing runtime configuration"),
            data=data,
        )

    if "未配置 TMDB_API_KEY" in message:
        raise TransferException(
            message,
            code=ErrorCode.CONFIG_ERROR,
            context=ErrorContext(field="TMDB_API_KEY", reason="missing runtime configuration"),
            data=data,
        )

    if "转存超时" in message or "验证超时" in message:
        raise TransferException(
            message,
            code=ErrorCode.TRANSFER_TIMEOUT,
            context=ErrorContext(field="collection_id", value=collection_id, reason=reason or message),
            data=data,
        )

    if "创建目标目录失败" in message:
        failed_target = message.partition(":")[2].strip() or target_folder
        raise TransferException(
            message,
            code=ErrorCode.TRANSFER_DIR_NOT_FOUND,
            context=ErrorContext(field="target_folder", value=failed_target, reason=reason or message),
            data=data,
        )

    if "分享链接" in message and ("无效" in message or "失效" in message):
        raise TransferException(
            message,
            code=ErrorCode.TRANSFER_LINK_EXPIRED,
            context=ErrorContext(field="share_url", value=share_url, reason=reason or message),
            data=data,
        )

    if "没有可转存的文件" in message or "没有文件" in message:
        raise TransferException(
            message,
            code=ErrorCode.TRANSFER_NO_FILES,
            context=ErrorContext(
                field="collection_id" if collection_id is not None else "share_url",
                value=collection_id if collection_id is not None else share_url,
                reason=reason or message,
            ),
            data=data,
        )

    raise TransferException(
        message,
        code=ErrorCode.TRANSFER_FAILED,
        context=ErrorContext(
            field="collection_id" if collection_id is not None else "share_url",
            value=collection_id if collection_id is not None else share_url,
            reason=reason or message,
        ),
        data=data,
    )


class TransferService:
    """转存服务（协调器）"""

    DEFAULT_TIMEOUT = 30
    TRANSFER_TIMEOUT = 120
    MAX_WORKERS = 5

    def __init__(
        self,
        db: Session,
        cookie: str = "",
        tmdb_client: Optional["TmdbClient"] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ):
        self.db = db
        self._cookie = cookie
        self.renamer = Renamer()
        self.collection_service = CollectionService(db)
        self._quark_client: Optional[QuarkTransferClient] = None
        self._path_resolver: Optional[QuarkPathResolver] = None
        self._tmdb_client = tmdb_client
        self._background_tasks = background_tasks
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)

        # 新增服务
        self.rename_service = RenameService(self.renamer)
        self.cleanup_service = CleanupService(self.renamer)
        self.distributed_lock = get_distributed_lock()

    async def _get_client(self) -> QuarkTransferClient:
        """获取 Quark 客户端（带连接复用）"""
        if not self._cookie:
            raise TransferException("未配置 QUARK_TRANSFER_COOKIE", code=ErrorCode.CONFIG_ERROR)
        if self._quark_client is None or self._quark_client.cookie != self._cookie:
            if self._quark_client:
                await self._quark_client.close()
            self._quark_client = QuarkTransferClient(self._cookie)
            self._path_resolver = QuarkPathResolver(self._quark_client)
            logger.debug("创建新的 QuarkTransferClient 实例")
        return self._quark_client

    async def _get_path_resolver(self) -> QuarkPathResolver:
        """获取路径解析器"""
        client = await self._get_client()
        if self._path_resolver is None or self._path_resolver.client is not client:
            self._path_resolver = QuarkPathResolver(client)
        return self._path_resolver

    async def _find_fid_by_path_no_create(
        self,
        client: QuarkTransferClient,
        path: str
    ) -> Optional[str]:
        """查找路径对应的 FID（不创建）"""
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
        self._executor.shutdown(wait=False)

    @staticmethod
    def _normalize_storage_path(path: str) -> str:
        """标准化存储路径"""
        normalized = path or ""
        for src, dst in PATH_REPLACEMENTS.items():
            normalized = normalized.replace(src, dst)
        return normalized

    @staticmethod
    def _attach_share_passcode(share_url: str, share_pwd: Optional[str]) -> str:
        """
        统一补齐分享链接中的提取码参数。

        Why:
            收藏记录会单独存储 share_pwd；若链接未携带 pwd 参数，转存链路会把私密分享误判为失效。
        """
        normalized_url = (share_url or "").strip()
        if not normalized_url:
            return ""

        passcode = (share_pwd or "").strip()
        if not passcode:
            return normalized_url

        try:
            split_result = urlsplit(normalized_url)
        except ValueError:
            return normalized_url

        query_items = parse_qsl(split_result.query, keep_blank_values=True)
        for index, (key, value) in enumerate(query_items):
            if key.lower() != "pwd":
                continue
            if value.strip():
                return normalized_url
            query_items[index] = (key, passcode)
            break
        else:
            query_items.append(("pwd", passcode))

        rebuilt_query = urlencode(query_items, doseq=True)
        return urlunsplit(
            (
                split_result.scheme,
                split_result.netloc,
                split_result.path,
                rebuilt_query,
                split_result.fragment,
            )
        )

    async def validate_link(
        self,
        share_url: str,
        timeout: Optional[int] = None
    ) -> Tuple[bool, str, List[Dict]]:
        """
        验证分享链接有效性并获取文件列表

        Args:
            share_url: 分享链接
            timeout: 超时时间（秒），默认 30 秒
        """
        effective_timeout = timeout or self.DEFAULT_TIMEOUT
        logger.info(f"验证分享链接: {share_url[:50]}...")

        try:
            client = await self._get_client()

            # 使用 asyncio.wait_for 添加超时控制
            is_valid, pwd_id, stoken = await asyncio.wait_for(
                client.validate_share_link(share_url),
                timeout=effective_timeout
            )

            if not is_valid:
                logger.warning(f"分享链接无效: {share_url[:50]}...")
                raise_transfer_failure(
                    "分享链接无效或已失效",
                    share_url=share_url,
                    reason="链接无效或已过期",
                    data=[],
                )

            detail_resp = await asyncio.wait_for(
                client.get_detail(pwd_id, stoken, "0"),
                timeout=effective_timeout
            )

            if detail_resp.get("code") != 0:
                error_msg = detail_resp.get("message", "获取文件列表失败")
                logger.error(f"获取文件列表失败: {error_msg}")
                raise_transfer_failure(error_msg, share_url=share_url, data=[])

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

        except asyncio.TimeoutError:
            logger.error(f"验证链接超时（{effective_timeout}秒）: {share_url[:50]}...")
            raise_transfer_failure(
                f"验证超时（{effective_timeout}秒），请稍后重试",
                share_url=share_url,
                data=[],
            )
        except TransferException:
            raise
        except Exception as e:
            logger.error(f"验证链接异常: {e}", exc_info=True)
            raise_transfer_failure(f"验证失败: {str(e)}", share_url=share_url, data=[])

    async def transfer_collection(
        self,
        collection_id: int,
        target_folder: Optional[str] = None,
        auto_rename: bool = False,
        use_background_task: bool = False
    ) -> Tuple[bool, str, List[Dict]]:
        """
        转存收藏中的资源并按 Emby v1.6 命名规范重命名。

        Args:
            collection_id: 收藏 ID
            target_folder: 目标文件夹
            auto_rename: 是否自动重命名
            use_background_task: 是否使用后台任务处理耗时操作
        """
        logger.info(f"开始转存: collection_id={collection_id}, auto_rename={auto_rename}")

        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            logger.warning(f"转存失败 - 收藏不存在: id={collection_id}")
            raise_transfer_failure("收藏不存在", collection_id=collection_id, data=[])

        # 如果使用后台任务，提交到 BackgroundTasks
        if use_background_task and self._background_tasks:
            self._background_tasks.add_task(
                self._transfer_collection_task,
                collection_id,
                target_folder,
                auto_rename
            )
            return True, "转存任务已提交到后台处理", []

        # 否则同步执行
        return await self._transfer_collection_impl(collection_id, target_folder, auto_rename)

    async def _transfer_collection_task(
        self,
        collection_id: int,
        target_folder: Optional[str],
        auto_rename: bool
    ) -> None:
        """后台任务：转存收藏"""
        try:
            # 创建新的数据库会话
            from ..db.session import SessionLocal
            db = SessionLocal()
            try:
                # 创建新的服务实例
                service = TransferService(
                    db=db,
                    cookie=self._cookie,
                    tmdb_client=self._tmdb_client
                )
                success, message, files = await service._transfer_collection_impl(
                    collection_id, target_folder, auto_rename
                )
                logger.info(f"后台转存任务完成: collection_id={collection_id}, success={success}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"后台转存任务失败: collection_id={collection_id}, error={e}", exc_info=True)

    async def _transfer_collection_impl(
        self,
        collection_id: int,
        target_folder: Optional[str],
        auto_rename: bool
    ) -> Tuple[bool, str, List[Dict]]:
        """转存实现（带分布式锁）"""
        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            raise_transfer_failure("收藏不存在", collection_id=collection_id, data=[])

        settings = get_settings()
        if self._tmdb_client is None and not settings.tmdb_api_key:
            raise_transfer_failure("未配置 TMDB_API_KEY，无法执行转存", collection_id=collection_id, data=[])
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
            # 使用分布式锁防止并发转存
            async with self.distributed_lock.acquire(f"transfer:collection:{collection_id}", timeout=300):
                # 使用 asyncio.wait_for 添加超时控制
                naming = await asyncio.wait_for(
                    resolve_tmdb_naming_info(
                        tmdb_client,
                        self.renamer,
                        media_type=collection.category or collection.media_type,
                        tmdb_id=collection.tmdb_id,
                        title=collection.title,
                        year=collection.year,
                    ),
                    timeout=self.DEFAULT_TIMEOUT
                )

                if target_folder:
                    media_root_path = target_folder
                else:
                    media_root_name = self.renamer.build_media_root_name(
                        naming.title, naming.year, naming.tmdb_id, naming.media_type
                    )
                    media_root_path = f"{get_category_base_dir(naming.category)}/{media_root_name}"

                # 获取目标目录 FID
                media_root_fid = await asyncio.wait_for(
                    client.get_fid_by_path(media_root_path),
                    timeout=self.DEFAULT_TIMEOUT
                )
                if not media_root_fid:
                    raise_transfer_failure(
                        f"创建目标目录失败: {media_root_path}",
                        collection_id=collection_id,
                        target_folder=media_root_path,
                        data=[],
                    )

                # 执行转存
                share_url = self._attach_share_passcode(
                    collection.quark_share_url,
                    collection.quark_share_pwd,
                )
                success, message, transferred_items, task_id = await asyncio.wait_for(
                    transfer_share_to_target_fid(
                        client=client,
                        share_url=share_url,
                        target_fid=media_root_fid,
                        flatten_single_root=True,
                    ),
                    timeout=self.TRANSFER_TIMEOUT
                )

                if not success:
                    self.collection_service.update_status(collection_id, 2)
                    raise_transfer_failure(
                        message,
                        collection_id=collection_id,
                        share_url=share_url,
                        target_folder=media_root_path,
                        data=[],
                    )

                # 等待转存任务完成（带超时）
                task_done = await asyncio.wait_for(
                    wait_for_transfer_task(client, task_id, max_retries=60, interval_seconds=1.0),
                    timeout=self.TRANSFER_TIMEOUT
                )
                if not task_done:
                    logger.warning(f"等待转存任务超时: task_id={task_id}")

                # 自动重命名（如果启用）
                reorganized_count = 0
                cleaned_count = 0
                planned_cleanup_count = 0

                if auto_rename:
                    reorganized_count, cleaned_count, planned_cleanup_count = await self._auto_rename(
                        client, media_root_fid, media_root_path, naming, collection_id
                    )

                # 获取转存后的文件列表
                ls_resp = await client.ls_dir(media_root_fid)
                saved_files = ls_resp.get("data", {}).get("list", []) if ls_resp.get("code") == 0 else []

                # 批量保存转存历史
                await self._save_transfer_history(collection_id, media_root_path, saved_files)

                # 更新收藏信息
                collection.title = naming.title
                collection.year = naming.year
                collection.media_type = "movie" if naming.media_type == "movie" else "tv"
                collection.category = naming.category
                collection.status = 1
                self.db.commit()

                # 构建返回结果
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

                # 构建状态消息
                status_msg = f"转存成功: {media_root_path}"
                if auto_rename:
                    if settings.transfer_dry_run:
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

        except asyncio.TimeoutError:
            self.db.rollback()
            logger.error(f"转存超时: collection_id={collection_id}")
            raise_transfer_failure("转存超时，请稍后重试", collection_id=collection_id, data=[])
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"转存失败 - 数据库错误: id={collection_id}, error={e}")
            raise TransferException(
                "转存失败: 数据库错误",
                code=ErrorCode.DATABASE_ERROR,
                context=ErrorContext(field="collection_id", value=collection_id, reason="database error"),
                data=[],
            )
        except TransferException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"转存失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            raise_transfer_failure(f"转存失败: {str(e)}", collection_id=collection_id, data=[])
        finally:
            if self._tmdb_client is None and tmdb_client:
                await tmdb_client.close()

    async def _auto_rename(
        self,
        client: QuarkTransferClient,
        media_root_fid: str,
        media_root_path: str,
        naming: Any,
        collection_id: int
    ) -> Tuple[int, int, int]:
        """
        自动重命名文件（使用 RenameService 和 CleanupService）

        Returns:
            (重组数量, 清理数量, 计划清理数量)
        """
        settings = get_settings()
        reorganized_count = 0
        cleaned_count = 0
        planned_cleanup_count = 0
        retained_fids = set()

        # 使用 RenameService 重组文件
        async for event in self.rename_service.rename_media_files(
            client=client,
            root_fid=media_root_fid,
            root_path=media_root_path,
            title=naming.title,
            year=naming.year,
            media_type=naming.media_type,
            keep_extras=bool(settings.transfer_keep_extras),
            dry_run=bool(settings.transfer_dry_run),
        ):
            if event.get("type") == "complete":
                reorganized_count = int(event.get("success", 0))
                retained_fids.update(event.get("retained_fids") or [])

        # 使用 CleanupService 清理文件
        if settings.transfer_cleanup_enabled:
            async for event in self.cleanup_service.cleanup_files(
                client=client,
                root_fid=media_root_fid,
                protected_video_fids=retained_fids,
                keep_subtitles=bool(settings.transfer_keep_subtitles),
                dry_run=bool(settings.transfer_dry_run),
                delete_non_video=bool(settings.transfer_cleanup_delete_non_video),
                delete_unselected_videos=bool(settings.transfer_cleanup_delete_unselected_video),
                delete_empty_dirs=bool(settings.transfer_cleanup_delete_empty_dirs),
            ):
                if event.get("type") == "complete":
                    cleaned_count = int(event.get("deleted", 0))
                    planned_cleanup_count = int(event.get("planned", 0))

        return reorganized_count, cleaned_count, planned_cleanup_count

    async def _save_transfer_history(
        self,
        collection_id: int,
        media_root_path: str,
        saved_files: List[Dict]
    ) -> None:
        """批量保存转存历史"""
        if not saved_files:
            return

        # 批量创建历史记录
        history_records = []
        for f in saved_files:
            history = TransferHistory(
                collection_id=collection_id,
                quark_fid=f.get("fid", ""),
                local_path=media_root_path,
                file_name=f.get("file_name", ""),
                file_size=f.get("size"),
            )
            history_records.append(history)

        # 使用批量插入
        try:
            self.db.bulk_save_objects(history_records)
            self.db.commit()
            logger.info(f"批量保存转存历史: {len(history_records)} 条记录")
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"保存转存历史失败: {e}")
            raise

    async def rename_collection(self, collection_id: int) -> AsyncGenerator[Dict[str, Any], None]:
        """
        独立重命名收藏（使用 RenameService 和 CleanupService）

        Args:
            collection_id: 收藏 ID
        """
        logger.info(f"开始独立重命名: collection_id={collection_id}")

        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            yield build_event_payload(event_type="error", message="收藏不存在", level="error")
            return

        if collection.status != 1:
            yield build_event_payload(event_type="error", message="该收藏尚未转存，无法重命名", level="error")
            return

        settings = get_settings()
        client = await self._get_client()
        tmdb_client = self._tmdb_client

        if tmdb_client is None and not settings.tmdb_api_key:
            yield build_event_payload(
                event_type="error",
                message="未配置 TMDB_API_KEY，无法执行重命名",
                level="error",
            )
            return

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
            # 使用分布式锁防止并发重命名
            async with self.distributed_lock.acquire(f"rename:collection:{collection_id}", timeout=300):
                naming = await asyncio.wait_for(
                    resolve_tmdb_naming_info(
                        tmdb_client, self.renamer,
                        media_type=collection.category or collection.media_type,
                        tmdb_id=collection.tmdb_id,
                        title=collection.title,
                        year=collection.year,
                    ),
                    timeout=self.DEFAULT_TIMEOUT
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
                    media_root_name = self.renamer.build_media_root_name(
                        naming.title, naming.year, naming.tmdb_id, naming.media_type
                    )
                    media_root_path = f"{get_category_base_dir(naming.category)}/{media_root_name}"

                expected_root_name = self.renamer.build_media_root_name(
                    naming.title, naming.year, naming.tmdb_id, naming.media_type
                )
                expected_root_path = f"{get_category_base_dir(naming.category)}/{expected_root_name}"

                if media_root_path != expected_root_path:
                    current_root_fid = await self._find_fid_by_path_no_create(client, media_root_path)
                    expected_root_fid = await self._find_fid_by_path_no_create(client, expected_root_path)

                    if expected_root_fid:
                        media_root_path = expected_root_path
                    elif current_root_fid:
                        renamed_root = await client.rename(current_root_fid, expected_root_name)
                        if renamed_root:
                            media_root_path = expected_root_path
                            self.db.query(TransferHistory).filter(
                                TransferHistory.collection_id == collection_id
                            ).update({"local_path": media_root_path}, synchronize_session=False)
                            self.db.commit()
                            yield build_event_payload(
                                event_type="log",
                                message=f"根目录改名: {expected_root_path}",
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

                yield build_event_payload(event_type="log", message=f"定位目录: {media_root_path}", level="info")

                # 使用 RenameService
                retained_fids = set()
                async for event in self.rename_service.rename_media_files(
                    client=client,
                    root_fid=media_root_fid,
                    root_path=media_root_path,
                    title=naming.title,
                    year=naming.year,
                    media_type=naming.media_type,
                    keep_extras=bool(settings.transfer_keep_extras),
                    dry_run=bool(settings.transfer_dry_run),
                ):
                    if event.get("type") == "complete":
                        retained_fids.update(event.get("retained_fids") or [])
                    yield event

                # 使用 CleanupService
                if settings.transfer_cleanup_enabled:
                    async for event in self.cleanup_service.cleanup_files(
                        client=client,
                        root_fid=media_root_fid,
                        protected_video_fids=retained_fids,
                        keep_subtitles=bool(settings.transfer_keep_subtitles),
                        dry_run=bool(settings.transfer_dry_run),
                        delete_non_video=bool(settings.transfer_cleanup_delete_non_video),
                        delete_unselected_videos=bool(settings.transfer_cleanup_delete_unselected_video),
                        delete_empty_dirs=bool(settings.transfer_cleanup_delete_empty_dirs),
                    ):
                        yield event
                else:
                    yield build_event_payload(event_type="log", message="清理阶段已关闭，跳过 cleanup", level="info")

        except asyncio.TimeoutError:
            self.db.rollback()
            logger.error(f"重命名超时: collection_id={collection_id}")
            yield build_event_payload(event_type="error", message="重命名超时，请稍后重试", level="error")
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"重命名失败 - 数据库错误: id={collection_id}, error={e}")
            yield build_event_payload(event_type="error", message="重命名失败: 数据库错误", level="error")
        except Exception as e:
            self.db.rollback()
            logger.error(f"重命名失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            yield build_event_payload(event_type="error", message=f"重命名失败: {str(e)}", level="error")
        finally:
            if self._tmdb_client is None and tmdb_client:
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


class TransferTaskManager:
    """
    转存任务管理器

    用于管理后台转存任务的状态和进度
    """

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task_id: str, collection_id: int) -> None:
        """创建任务记录"""
        async with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "collection_id": collection_id,
                "status": "pending",  # pending, running, completed, failed
                "progress": 0,
                "message": "",
                "created_at": asyncio.get_event_loop().time(),
                "updated_at": asyncio.get_event_loop().time(),
            }

    async def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None
    ) -> None:
        """更新任务状态"""
        async with self._lock:
            if task_id in self._tasks:
                if status:
                    self._tasks[task_id]["status"] = status
                if progress is not None:
                    self._tasks[task_id]["progress"] = progress
                if message:
                    self._tasks[task_id]["message"] = message
                self._tasks[task_id]["updated_at"] = asyncio.get_event_loop().time()

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """列出任务"""
        async with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t["status"] == status]
            # 按更新时间排序
            tasks.sort(key=lambda x: x["updated_at"], reverse=True)
            return tasks[:limit]

    async def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> int:
        """清理旧任务"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            to_remove = [
                task_id for task_id, task in self._tasks.items()
                if now - task["updated_at"] > max_age_seconds
            ]
            for task_id in to_remove:
                del self._tasks[task_id]
            return len(to_remove)


# 全局任务管理器实例
task_manager = TransferTaskManager()
