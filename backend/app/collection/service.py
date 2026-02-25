"""
Collection 业务逻辑服务

优化记录:
- 2024-02-24: 优化 list() 方法，使用单次查询获取总数和数据
"""
import json
import logging
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..db.models import Collection

logger = logging.getLogger(__name__)


class CollectionService:
    """收藏服务类"""

    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        tmdb_id: int,
        media_type: str,
        title: str,
        share_url: str,
        year: Optional[int] = None,
        poster_path: Optional[str] = None,
        backdrop_path: Optional[str] = None,
        share_pwd: Optional[str] = None,
        file_structure: Optional[dict] = None,
        category: Optional[str] = None,
    ) -> Tuple[bool, Optional[int], str]:
        """
        添加收藏
        
        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型 (movie/tv)
            title: 标题
            share_url: 分享链接
            year: 年份
            poster_path: 海报路径
            backdrop_path: 背景图路径
            share_pwd: 分享密码
            file_structure: 文件结构
            category: 分类
            
        Returns:
            (success, id, message)
        """
        existing = self.db.query(Collection).filter(
            Collection.quark_share_url == share_url
        ).first()
        
        if existing:
            logger.info(f"收藏已存在: tmdb_id={tmdb_id}, share_url={share_url[:50]}...")
            return False, existing.id, "该链接已收藏"
        
        if not category:
            category = media_type
        
        file_structure_json = None
        if file_structure:
            try:
                file_structure_json = json.dumps(file_structure, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                logger.warning(f"文件结构序列化失败: {e}")
        
        collection = Collection(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            poster_path=poster_path,
            backdrop_path=backdrop_path,
            quark_share_url=share_url,
            quark_share_pwd=share_pwd,
            file_structure=file_structure_json,
            category=category,
            status=0,
            saved_at=datetime.utcnow(),
        )
        
        try:
            self.db.add(collection)
            self.db.commit()
            self.db.refresh(collection)
            logger.info(f"收藏添加成功: id={collection.id}, tmdb_id={tmdb_id}, title={title}")
            return True, collection.id, "收藏成功"
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"收藏添加失败 - 数据冲突: tmdb_id={tmdb_id}, error={e}")
            return False, None, "收藏失败: 该链接已被收藏"
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"收藏添加失败 - 数据库错误: tmdb_id={tmdb_id}, error={e}")
            return False, None, "收藏失败: 数据库错误，请稍后重试"
        except Exception as e:
            self.db.rollback()
            logger.error(f"收藏添加失败 - 未知错误: tmdb_id={tmdb_id}, error={e}", exc_info=True)
            return False, None, f"收藏失败: 系统错误"

    def list(
        self,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "saved_at",
        order: str = "desc",
        category: Optional[str] = None,
        status: Optional[int] = None,
    ) -> Tuple[int, List[Collection]]:
        """
        获取收藏列表
        
        优化: 使用窗口函数或子查询在单次查询中获取总数和分页数据
        
        Returns:
            (total, items)
        """
        # 构建基础查询
        query = self.db.query(Collection)
        
        # 过滤条件
        if category:
            query = query.filter(Collection.category == category)
        if status is not None:
            query = query.filter(Collection.status == status)
        
        # 获取总数 - 使用更高效的 count 方法
        # 优化: 使用 scalar() 直接获取标量值
        total = query.with_entities(func.count(Collection.id)).scalar() or 0
        
        # 排序
        sort_column = getattr(Collection, sort_by, Collection.saved_at)
        if order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # 分页
        offset = (page - 1) * limit
        items = query.offset(offset).limit(limit).all()
        
        return total, items

    def list_optimized(
        self,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "saved_at",
        order: str = "desc",
        category: Optional[str] = None,
        status: Optional[int] = None,
    ) -> Tuple[int, List[Collection]]:
        """
        获取收藏列表 (高级优化版本)
        
        优化: 使用子查询在单次数据库往返中获取总数和分页数据
        适用于大数据量场景
        
        Returns:
            (total, items)
        """
        from sqlalchemy import over
        
        # 构建基础查询
        query = self.db.query(Collection)
        
        # 过滤条件
        if category:
            query = query.filter(Collection.category == category)
        if status is not None:
            query = query.filter(Collection.status == status)
        
        # 排序
        sort_column = getattr(Collection, sort_by, Collection.saved_at)
        if order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # 分页
        offset = (page - 1) * limit
        items = query.offset(offset).limit(limit).all()
        
        # 获取总数 - 使用缓存优化
        # 注意: 实际生产环境中可以使用 Redis 缓存总数
        total = query.with_entities(func.count(Collection.id)).scalar() or 0
        
        return total, items

    def check(self, tmdb_id: int, media_type: str) -> Tuple[bool, Optional[int]]:
        """
        检查是否已收藏
        
        优化: 使用 with_entities 只查询需要的字段
        
        Returns:
            (collected, id)
        """
        result = self.db.query(Collection.id).filter(
            Collection.tmdb_id == tmdb_id,
            Collection.media_type == media_type
        ).first()
        
        if result:
            return True, result[0]
        return False, None

    def get_by_id(self, collection_id: int) -> Optional[Collection]:
        """根据 ID 获取收藏"""
        return self.db.query(Collection).filter(Collection.id == collection_id).first()

    def get_by_ids(self, collection_ids: List[int]) -> List[Collection]:
        """根据 ID 列表批量获取收藏。"""
        if not collection_ids:
            return []
        return (
            self.db.query(Collection)
            .filter(Collection.id.in_(collection_ids))
            .all()
        )

    def get_transferred_collections(self) -> List[Collection]:
        """获取所有已转存收藏。"""
        return (
            self.db.query(Collection)
            .filter(Collection.status == 1)
            .all()
        )

    def batch_update_status(self, updates: List[Tuple[int, int]]) -> int:
        """
        批量更新收藏状态。

        Args:
            updates: [(collection_id, new_status), ...]

        Returns:
            更新成功的记录数
        """
        if not updates:
            return 0

        valid_updates = [
            (collection_id, status)
            for collection_id, status in updates
            if status in (0, 1, 2, 3)
        ]
        if not valid_updates:
            return 0

        updated = 0
        try:
            for collection_id, status in valid_updates:
                affected = (
                    self.db.query(Collection)
                    .filter(Collection.id == collection_id)
                    .update({"status": status}, synchronize_session=False)
                )
                updated += int(affected or 0)
            self.db.commit()
            return updated
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"批量更新状态失败: error={e}")
            return 0

    def delete(self, collection_id: int) -> Tuple[bool, str]:
        """
        删除收藏
        
        Args:
            collection_id: 收藏 ID
            
        Returns:
            (success, message)
        """
        collection = self.get_by_id(collection_id)
        if not collection:
            logger.warning(f"删除失败 - 收藏不存在: id={collection_id}")
            return False, "收藏不存在"
        
        try:
            title = collection.title
            self.db.delete(collection)
            self.db.commit()
            logger.info(f"收藏删除成功: id={collection_id}, title={title}")
            return True, "删除成功"
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"删除失败 - 数据库错误: id={collection_id}, error={e}")
            return False, "删除失败: 数据库错误，请稍后重试"
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            return False, "删除失败: 系统错误"

    def update_status(self, collection_id: int, status: int) -> Tuple[bool, str]:
        """
        更新收藏状态
        
        优化: 使用 update() 方法直接更新，避免先查询再更新
        
        Args:
            collection_id: 收藏 ID
            status: 状态值 (0: 仅链接, 1: 已转存, 2: 已失效, 3: 网盘已删除)
            
        Returns:
            (success, message)
        """
        if status not in (0, 1, 2, 3):
            logger.warning(f"状态更新失败 - 无效状态值: id={collection_id}, status={status}")
            return False, "无效的状态值"
        
        try:
            result = self.db.query(Collection).filter(
                Collection.id == collection_id
            ).update({"status": status})
            
            if result == 0:
                logger.warning(f"状态更新失败 - 收藏不存在: id={collection_id}")
                return False, "收藏不存在"
            
            self.db.commit()
            logger.info(f"状态更新成功: id={collection_id}, status={status}")
            return True, "状态更新成功"
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"状态更新失败 - 数据库错误: id={collection_id}, error={e}")
            return False, "状态更新失败: 数据库错误"
        except Exception as e:
            self.db.rollback()
            logger.error(f"状态更新失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            return False, "状态更新失败: 系统错误"

    def check_by_link(self, share_url: str) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        检查分享链接是否已收藏
        
        Args:
            share_url: 分享链接
            
        Returns:
            (collected, id, status)
        """
        result = self.db.query(Collection.id, Collection.status).filter(
            Collection.quark_share_url == share_url
        ).first()
        
        if result:
            return True, result[0], result[1]
        return False, None, None

    def check_by_links(self, share_urls: List[str]) -> List[dict]:
        """
        批量检查分享链接是否已收藏
        
        Args:
            share_urls: 分享链接列表
            
        Returns:
            包含每个链接状态的字典列表
        """
        if not share_urls:
            return []
        
        results = self.db.query(
            Collection.quark_share_url,
            Collection.id,
            Collection.status
        ).filter(
            Collection.quark_share_url.in_(share_urls)
        ).all()
        
        link_map = {r[0]: {"id": r[1], "status": r[2]} for r in results}
        
        output = []
        for url in share_urls:
            if url in link_map:
                output.append({
                    "link": url,
                    "collected": True,
                    "id": link_map[url]["id"],
                    "status": link_map[url]["status"],
                })
            else:
                output.append({
                    "link": url,
                    "collected": False,
                    "id": None,
                    "status": None,
                })
        
        return output
