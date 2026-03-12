"""
收藏网盘状态验证服务。

支持智能验证：
- 验证所有收藏，不限制状态
- 全盘扫描 + 智能匹配
- 自动发现网盘中已存在但状态未同步的收藏
- 自动创建 TransferHistory 记录
- 自动修正 category 和路径
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

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

# 质量标签正则（需要从标题中去除的）
QUALITY_TAGS_PATTERN = re.compile(
    r'\s*('
    r'4K|2160P|1080P|720P|480P|'
    r'HDR|HDR10|DOLBY|ATMOS|'
    r'REMUX|WEB-DL|BLURAY|HDTV|'
    r'H\.264|H\.265|HEVC|AVC|'
    r'DTS|AC3|AAC|FLAC|'
    r'\d+BIT|'
    r'DUAL[-_]?AUDIO|'
    r'MULTI[-_]?AUDIO|'
    r'\[.*?\]'  # 方括号标签
    r')\s*',
    re.IGNORECASE
)

# 分类目录映射
CATEGORY_DIRS = {
    "movie": "/影视收藏/电影",
    "tv": "/影视收藏/电视剧",
    "anime": "/影视收藏/动漫",
    "documentary": "/影视收藏/纪录片",
}


class CollectionVerifyService:
    """收藏网盘比对验证服务。"""

    def __init__(self, db: Session, client: QuarkTransferClient):
        self.db = db
        self.client = client
        self.renamer = Renamer()
        self.path_resolver = QuarkPathResolver(client)
        self._scan_cache: Dict[str, List[Dict]] = {}

    @staticmethod
    def _normalize_storage_path(path: str) -> str:
        normalized = path or ""
        for src, dst in PATH_REPLACEMENTS.items():
            normalized = normalized.replace(src, dst)
        return QuarkPathResolver.normalize_path(normalized)

    @staticmethod
    def _normalize_title(title: str) -> str:
        """
        标准化标题，去除质量标签。
        
        Examples:
            "古见同学有交流障碍症4K" -> "古见同学有交流障碍症"
            "进击的巨人 [4K HDR]" -> "进击的巨人"
        """
        if not title:
            return ""
        # 去除质量标签
        normalized = QUALITY_TAGS_PATTERN.sub(' ', title)
        # 去除多余空格
        normalized = ' '.join(normalized.split())
        return normalized.strip()

    @staticmethod
    def _extract_tmdb_id_from_name(name: str) -> Optional[int]:
        """从目录名中提取 TMDB ID。"""
        match = re.search(r'\[tmdbid=(\d+)\]', name, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_year_from_name(name: str) -> Optional[int]:
        """从目录名中提取年份。"""
        match = re.search(r'\((\d{4})\)', name)
        if match:
            return int(match.group(1))
        return None

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

    async def _scan_category_dirs(self) -> Dict[str, List[Dict]]:
        """
        扫描所有分类目录，缓存结果。
        
        Returns:
            {category_dir: [{name, fid, year, tmdb_id}, ...]}
        """
        if self._scan_cache:
            return self._scan_cache

        for category, dir_path in CATEGORY_DIRS.items():
            fid = await self.path_resolver.find_fid_by_path_no_create(dir_path)
            if not fid:
                logger.warning("分类目录不存在: %s", dir_path)
                continue

            children = await self.path_resolver.list_dir(fid, use_cache=False)
            if not children:
                continue

            items = []
            for child in children:
                if not child.get("dir"):
                    continue
                name = child.get("file_name") or child.get("name", "")
                items.append({
                    "name": name,
                    "fid": child.get("fid"),
                    "year": self._extract_year_from_name(name),
                    "tmdb_id": self._extract_tmdb_id_from_name(name),
                    "normalized_name": self._normalize_title(name),
                })

            self._scan_cache[dir_path] = items
            logger.info("扫描目录 %s: 发现 %d 个子目录", dir_path, len(items))

        return self._scan_cache

    async def _smart_find_in_quark(
        self,
        collection: Collection,
    ) -> Optional[Tuple[str, str, str]]:
        """
        智能匹配：在网盘中查找收藏对应的目录。
        
        匹配策略（按优先级）：
        1. TMDB ID 匹配
        2. 标题精确匹配（忽略质量标签）
        3. 标题包含匹配
        
        Returns:
            (found_path, found_fid, found_category) 或 None
        """
        cache = await self._scan_category_dirs()

        collection_tmdb_id = collection.tmdb_id
        collection_title = self._normalize_title(collection.title or "")
        collection_year = collection.year

        candidates: List[Tuple[str, str, str, int]] = []

        for category, dir_path in CATEGORY_DIRS.items():
            items = cache.get(dir_path, [])
            for item in items:
                score = 0

                # 策略1: TMDB ID 匹配（最高优先级）
                if collection_tmdb_id and item.get("tmdb_id") == collection_tmdb_id:
                    score = 100
                    logger.debug(
                        "TMDB ID 匹配: %s (tmdbid=%s)",
                        item["name"],
                        collection_tmdb_id,
                    )

                # 策略2: 标题精确匹配
                elif item.get("normalized_name") == collection_title:
                    score = 80
                    # 年份匹配加分
                    if collection_year and item.get("year") == collection_year:
                        score += 10
                    logger.debug(
                        "标题精确匹配: %s (score=%d)",
                        item["name"],
                        score,
                    )

                # 策略3: 标题包含匹配
                elif collection_title and item.get("normalized_name"):
                    item_name = item["normalized_name"]
                    if collection_title in item_name or item_name in collection_title:
                        score = 60
                        # 年份匹配加分
                        if collection_year and item.get("year") == collection_year:
                            score += 10
                        logger.debug(
                            "标题包含匹配: %s (score=%d)",
                            item["name"],
                            score,
                        )

                if score > 0:
                    found_path = f"{dir_path}/{item['name']}"
                    candidates.append((found_path, item["fid"], category, score))

        if not candidates:
            return None

        # 按分数排序，返回最高分
        candidates.sort(key=lambda x: x[3], reverse=True)
        best = candidates[0]
        return best[0], best[1], best[2]

    async def _path_exists_and_not_empty(self, path: str) -> Tuple[bool, Optional[str], Optional[list]]:
        """
        检查路径是否存在且非空。
        
        Returns:
            (exists, fid, children): 是否存在、目录FID、子文件列表
        """
        fid = await self.path_resolver.find_fid_by_path_no_create(path)
        if not fid:
            return False, None, None
        children = await self.path_resolver.list_dir(fid, use_cache=False)
        if children is None:
            return False, fid, None
        return len(children) > 0, fid, children

    def _ensure_transfer_history(
        self,
        collection: Collection,
        local_path: str,
        fid: Optional[str] = None,
        children: Optional[list] = None,
    ) -> None:
        """
        确保收藏有 TransferHistory 记录。
        如果不存在，则创建一条记录。
        """
        existing = (
            self.db.query(TransferHistory)
            .filter(TransferHistory.collection_id == collection.id)
            .first()
        )
        if existing:
            return

        now = datetime.now(timezone.utc)

        if children:
            for child in children:
                if child.get("dir"):
                    continue
                history = TransferHistory(
                    collection_id=collection.id,
                    quark_fid=child.get("fid", ""),
                    local_path=local_path,
                    file_name=child.get("file_name") or child.get("name", ""),
                    file_size=child.get("size"),
                    transferred_at=now,
                )
                self.db.add(history)
        else:
            history = TransferHistory(
                collection_id=collection.id,
                quark_fid=fid or "",
                local_path=local_path,
                file_name="",
                file_size=None,
                transferred_at=now,
            )
            self.db.add(history)

        logger.info(
            "为收藏创建 TransferHistory 记录: collection_id=%s, path=%s",
            collection.id,
            local_path,
        )

    def _update_collection_category(
        self,
        collection: Collection,
        new_category: str,
        new_path: str,
    ) -> None:
        """更新收藏的分类和路径信息。"""
        old_category = collection.category
        if old_category != new_category:
            collection.category = new_category
            logger.info(
                "更新收藏分类: collection_id=%s, %s -> %s",
                collection.id,
                old_category,
                new_category,
            )

    async def _verify_collection(self, collection: Collection) -> Dict[str, Any]:
        previous_status = int(collection.status or 0)
        latest_local_path = self._get_latest_local_path(collection.id)

        # 第一步：尝试历史路径
        checked_path = latest_local_path
        path_source = "history" if latest_local_path else "pending_smart"

        exists = False
        fid = None
        children = None
        found_category = None

        if checked_path:
            exists, fid, children = await self._path_exists_and_not_empty(checked_path)

        # 第二步：如果历史路径不存在，尝试预期路径
        if not exists:
            expected_path = self._build_expected_path(collection)
            exists, fid, children = await self._path_exists_and_not_empty(expected_path)
            if exists:
                checked_path = expected_path
                path_source = "expected"

        # 第三步：如果预期路径也不存在，进行智能匹配
        if not exists:
            smart_result = await self._smart_find_in_quark(collection)
            if smart_result:
                checked_path, fid, found_category = smart_result
                path_source = "smart_match"
                # 获取子文件列表
                if fid:
                    children = await self.path_resolver.list_dir(fid, use_cache=False)
                    exists = children is not None and len(children) > 0

        current_status = previous_status
        auto_created_history = False
        category_updated = False

        if exists:
            if previous_status == 0:
                current_status = 1
                auto_created_history = True
                logger.info(
                    "发现网盘已存在资源，自动更新状态: collection_id=%s, title=%s, path=%s",
                    collection.id,
                    collection.title,
                    checked_path,
                )
            elif previous_status == 3:
                current_status = 1

            # 更新分类（如果智能匹配发现了不同分类）
            if found_category and found_category != collection.category:
                self._update_collection_category(collection, found_category, checked_path)
                category_updated = True

            # 创建历史记录
            try:
                self._ensure_transfer_history(collection, checked_path, fid, children)
            except SQLAlchemyError as e:
                self.db.rollback()
                logger.warning("创建 TransferHistory 失败: %s", e)
        else:
            if previous_status == 1:
                current_status = 3

        # 更新状态
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
            "checked_path": checked_path or "",
            "path_source": path_source,
            "auto_created_history": auto_created_history,
            "category_updated": category_updated,
            "found_category": found_category,
        }

    async def verify_single(self, collection_id: int) -> Dict[str, Any]:
        # 清空缓存，确保获取最新数据
        self._scan_cache = {}
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
        # 清空缓存
        self._scan_cache = {}

        # 预先扫描所有目录（提高效率）
        yield build_event_payload(
            event_type="log",
            current=0,
            total=0,
            message="正在扫描网盘目录...",
            level="info",
        )
        await self._scan_category_dirs()

        if collection_ids:
            collections = (
                self.db.query(Collection)
                .filter(Collection.id.in_(collection_ids))
                .all()
            )
        else:
            collections = self.db.query(Collection).all()

        total = len(collections)
        exists_count = 0
        deleted_count = 0
        not_transferred_count = 0
        auto_fixed_count = 0
        failed_count = 0

        if total == 0:
            yield build_event_payload(
                event_type="complete",
                current=0,
                total=0,
                message="没有需要验证的收藏",
                exists=0,
                deleted=0,
                not_transferred=0,
                auto_fixed=0,
                failed=0,
            )
            return

        yield build_event_payload(
            event_type="log",
            current=0,
            total=total,
            message=f"开始智能验证 {total} 条收藏...",
            level="info",
        )

        for index, collection in enumerate(collections, start=1):
            try:
                result = await self._verify_collection(collection)

                if result["exists"]:
                    exists_count += 1
                    if result.get("auto_created_history"):
                        auto_fixed_count += 1
                        level = "success"
                        extra = f" ({result.get('found_category', '')})" if result.get("category_updated") else ""
                        text = f"✓ 自动发现: {result['title']}{extra}"
                    else:
                        level = "info"
                        text = f"✓ 存在: {result['title']}"
                else:
                    if result["current_status"] == 0:
                        not_transferred_count += 1
                        level = "info"
                        text = f"○ 未转存: {result['title']}"
                    else:
                        deleted_count += 1
                        level = "warning"
                        text = f"✗ 已删除: {result['title']}"

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

        summary_parts = []
        if exists_count > 0:
            summary_parts.append(f"存在 {exists_count}")
        if auto_fixed_count > 0:
            summary_parts.append(f"自动修复 {auto_fixed_count}")
        if not_transferred_count > 0:
            summary_parts.append(f"未转存 {not_transferred_count}")
        if deleted_count > 0:
            summary_parts.append(f"已删除 {deleted_count}")
        if failed_count > 0:
            summary_parts.append(f"失败 {failed_count}")

        yield build_event_payload(
            event_type="complete",
            current=total,
            total=total,
            message=f"验证完成：{', '.join(summary_parts)}",
            exists=exists_count,
            deleted=deleted_count,
            not_transferred=not_transferred_count,
            auto_fixed=auto_fixed_count,
            failed=failed_count,
        )
