"""
收藏网盘状态验证服务。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db.models import Collection, TransferHistory
from ..quark.core.path_resolver import QuarkPathResolver
from ..quark.core.transfer_client import QuarkTransferClient
from ..transfer.emby import get_category_base_dir
from ..transfer.renamer import Renamer
from ..utils.events import build_event_payload
from app.core.constants import PATH_REPLACEMENTS

logger = logging.getLogger(__name__)


class CollectionVerifyService:
    """收藏网盘比对验证服务。"""

    def __init__(self, db: Session, client: QuarkTransferClient):
        self.db = db
        self.client = client
        self.renamer = Renamer()
        self.path_resolver = QuarkPathResolver(client)

    @staticmethod
    def _normalize_storage_path(path: str) -> str:
        normalized = path or ""
        for src, dst in PATH_REPLACEMENTS.items():
            normalized = normalized.replace(src, dst)
        return QuarkPathResolver.normalize_path(normalized)

    def _build_expected_path(self, collection: Collection) -> str:
        category = collection.category or collection.media_type or "movie"
        media_root_name = self.renamer.build_media_root_name(
            collection.title or "",
            collection.year,
            collection.tmdb_id,
            category,
        )
        base_dir = get_category_base_dir(category)
        return QuarkPathResolver.normalize_path(f"{base_dir}/{media_root_name}")

    def _get_latest_local_path(self, collection_id: int) -> Optional[str]:
        latest_record = (
            self.db.query(TransferHistory)
            .filter(TransferHistory.collection_id == collection_id)
            .order_by(desc(TransferHistory.transferred_at), desc(TransferHistory.id))
            .first()
        )
        if not latest_record or not latest_record.local_path:
            return None
        return self._normalize_storage_path(latest_record.local_path)

    async def _path_exists_and_not_empty(self, path: str) -> bool:
        fid = await self.path_resolver.find_fid_by_path_no_create(path)
        if not fid:
            return False
        children = await self.path_resolver.list_dir(fid, use_cache=False)
        if children is None:
            return False
        return len(children) > 0

    async def _verify_collection(self, collection: Collection) -> Dict[str, Any]:
        previous_status = int(collection.status or 0)
        latest_local_path = self._get_latest_local_path(collection.id)
        checked_path = latest_local_path or self._build_expected_path(collection)
        path_source = "history" if latest_local_path else "fallback"

        exists = await self._path_exists_and_not_empty(checked_path)
        current_status = previous_status

        # 仅对“已转存/网盘已删除”语义进行验证纠偏。
        if previous_status in (1, 3):
            current_status = 1 if exists else 3

        if current_status != previous_status:
            try:
                collection.status = current_status
                self.db.commit()
            except SQLAlchemyError:
                self.db.rollback()
                raise

        return {
            "collection_id": collection.id,
            "title": collection.title,
            "previous_status": previous_status,
            "current_status": current_status,
            "exists": exists,
            "checked_path": checked_path,
            "path_source": path_source,
        }

    async def verify_single(self, collection_id: int) -> Dict[str, Any]:
        collection = self.db.query(Collection).filter(Collection.id == collection_id).first()
        if not collection:
            raise ValueError("收藏不存在")
        return await self._verify_collection(collection)

    async def verify_all(
        self,
        collection_ids: Optional[List[int]] = None,
        *,
        interval_seconds: float = 0.2,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if collection_ids:
            collections = (
                self.db.query(Collection)
                .filter(Collection.id.in_(collection_ids), Collection.status.in_((1, 3)))
                .all()
            )
        else:
            collections = (
                self.db.query(Collection)
                .filter(Collection.status.in_((1, 3)))
                .all()
            )

        total = len(collections)
        exists_count = 0
        deleted_count = 0
        failed_count = 0

        if total == 0:
            yield build_event_payload(
                event_type="complete",
                current=0,
                total=0,
                message="没有需要验证的收藏",
                exists=0,
                deleted=0,
                failed=0,
            )
            return

        for index, collection in enumerate(collections, start=1):
            try:
                result = await self._verify_collection(collection)
                if result["exists"]:
                    exists_count += 1
                    level = "info"
                    text = f"存在: {result['title']}"
                else:
                    deleted_count += 1
                    level = "warning"
                    text = f"已删除: {result['title']}"

                yield build_event_payload(
                    event_type="log",
                    current=index,
                    total=total,
                    message=text,
                    level=level,
                    **result,
                )
            except Exception as exc:
                failed_count += 1
                logger.error("验证收藏失败: id=%s, error=%s", collection.id, exc, exc_info=True)
                yield build_event_payload(
                    event_type="log",
                    current=index,
                    total=total,
                    message=f"验证失败: {collection.title}",
                    level="error",
                    collection_id=collection.id,
                    title=collection.title,
                    previous_status=int(collection.status or 0),
                    current_status=int(collection.status or 0),
                    exists=False,
                    checked_path="",
                    path_source="unknown",
                )

            yield build_event_payload(
                event_type="progress",
                current=index,
                total=total,
                message=f"已验证 {index}/{total}",
            )

            if interval_seconds > 0 and index < total:
                await asyncio.sleep(interval_seconds)

        yield build_event_payload(
            event_type="complete",
            current=total,
            total=total,
            message=f"验证完成：存在 {exists_count}，已删除 {deleted_count}，失败 {failed_count}",
            exists=exists_count,
            deleted=deleted_count,
            failed=failed_count,
        )
