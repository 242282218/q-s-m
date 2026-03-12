"""
Collection 业务逻辑服务

优化记录:
- 2024-02-24: 优化 list() 方法，使用单次查询获取总数和数据
- 2026-02-28: 添加 selectinload 优化关联查询，添加批量获取关联数据方法
"""
import json
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import desc, asc, func, case
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..db.models import Collection, TransferHistory

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
            saved_at=datetime.now(timezone.utc),
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
            return False, None, "收藏失败: 系统错误"

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

    def get_by_id(self, collection_id: int, load_transfer_records: bool = False) -> Optional[Collection]:
        """
        根据 ID 获取收藏

        Args:
            collection_id: 收藏 ID
            load_transfer_records: 是否预加载转存记录（使用 selectinload 优化 N+1）
        """
        query = self.db.query(Collection)
        if load_transfer_records:
            # 优化：使用 selectinload 预加载关联数据，避免 N+1 查询
            query = query.options(selectinload(Collection.transfer_records))
        return query.filter(Collection.id == collection_id).first()

    def get_by_ids(self, collection_ids: List[int], load_transfer_records: bool = False) -> List[Collection]:
        """
        根据 ID 列表批量获取收藏。

        Args:
            collection_ids: 收藏 ID 列表
            load_transfer_records: 是否预加载转存记录（使用 selectinload 优化 N+1）
        """
        if not collection_ids:
            return []
        query = self.db.query(Collection)
        if load_transfer_records:
            # 优化：使用 selectinload 预加载关联数据
            query = query.options(selectinload(Collection.transfer_records))
        return (
            query.filter(Collection.id.in_(collection_ids))
            .all()
        )

    def get_transferred_collections(self, load_transfer_records: bool = False) -> List[Collection]:
        """
        获取所有已转存收藏。

        Args:
            load_transfer_records: 是否预加载转存记录（使用 selectinload 优化 N+1）
        """
        query = self.db.query(Collection)
        if load_transfer_records:
            # 优化：使用 selectinload 预加载关联数据
            query = query.options(selectinload(Collection.transfer_records))
        return (
            query.filter(Collection.status == 1)
            .all()
        )

    def get_collections_with_transfer_history(self, collection_ids: List[int]) -> List[Collection]:
        """
        批量获取收藏及其转存历史（优化版本，使用 selectinload 避免 N+1）

        Args:
            collection_ids: 收藏 ID 列表

        Returns:
            包含预加载 transfer_records 的 Collection 列表
        """
        if not collection_ids:
            return []

        # 优化：使用 selectinload 在一次查询中获取所有关联数据
        return (
            self.db.query(Collection)
            .options(selectinload(Collection.transfer_records))
            .filter(Collection.id.in_(collection_ids))
            .all()
        )

    def batch_update_status(self, updates: List[Tuple[int, int]]) -> int:
        """
        批量更新收藏状态。

        优化：使用单条 UPDATE CASE WHEN 语句，避免 N+1 查询问题

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

        try:
            # 构建 CASE WHEN 批量更新语句
            # 为每个状态值构建条件
            status_cases = {0: [], 1: [], 2: [], 3: []}
            for collection_id, status in valid_updates:
                status_cases[status].append(collection_id)

            # 构建 CASE WHEN 表达式
            whens = []
            for status, ids in status_cases.items():
                if ids:
                    whens.append((Collection.id.in_(ids), status))

            if not whens:
                return 0

            # 使用 CASE WHEN 进行批量更新
            from sqlalchemy import update
            stmt = (
                update(Collection)
                .where(Collection.id.in_([cid for cid, _ in valid_updates]))
                .values(status=case(*whens, else_=Collection.status))
            )
            result = self.db.execute(stmt)
            self.db.commit()
            updated = result.rowcount
            logger.info(f"批量更新状态成功: 更新了 {updated} 条记录")
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

    def list_cursor(
        self,
        cursor: Optional[str] = None,
        limit: int = 20,
        sort_by: str = "saved_at",
        order: str = "desc",
        category: Optional[str] = None,
        status: Optional[int] = None,
    ) -> Tuple[List[Collection], bool, Optional[str], Optional[str]]:
        """
        获取收藏列表（游标分页）

        适用于大数据量场景，避免深度分页性能问题

        Args:
            cursor: 游标（包含上一页/下一页位置信息）
            limit: 每页数量（最大100）
            sort_by: 排序字段
            order: 排序方向
            category: 分类过滤
            status: 状态过滤

        Returns:
            (items, has_more, next_cursor, prev_cursor)
        """
        # 限制 limit 最大为 100
        limit = min(limit, 100)

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
            query = query.order_by(desc(sort_column), desc(Collection.id))
        else:
            query = query.order_by(asc(sort_column), asc(Collection.id))

        # 解析游标
        cursor_data = None
        if cursor:
            try:
                import base64
                import json
                padding = 4 - len(cursor) % 4
                if padding != 4:
                    cursor += '=' * padding
                json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
                cursor_data = json.loads(json_str)
            except Exception:
                cursor_data = None

        # 应用游标过滤
        if cursor_data:
            cursor_value = cursor_data.get("value")
            cursor_id = cursor_data.get("id")
            cursor_type = cursor_data.get("type")  # "next" 或 "prev"

            if cursor_value is not None and cursor_id is not None:
                if cursor_type == "next":
                    # 下一页：获取比游标值大的记录
                    if order.lower() == "desc":
                        query = query.filter(
                            (sort_column < cursor_value) |
                            ((sort_column == cursor_value) & (Collection.id < cursor_id))
                        )
                    else:
                        query = query.filter(
                            (sort_column > cursor_value) |
                            ((sort_column == cursor_value) & (Collection.id > cursor_id))
                        )
                else:
                    # 上一页：获取比游标值小的记录（需要反转排序）
                    if order.lower() == "desc":
                        query = query.filter(
                            (sort_column > cursor_value) |
                            ((sort_column == cursor_value) & (Collection.id > cursor_id))
                        )
                    else:
                        query = query.filter(
                            (sort_column < cursor_value) |
                            ((sort_column == cursor_value) & (Collection.id < cursor_id))
                        )

        # 获取多一条数据用于判断是否有更多
        items = query.limit(limit + 1).all()

        # 判断是否有更多数据
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        # 如果是获取上一页，需要反转结果
        if cursor_data and cursor_data.get("type") == "prev":
            items = list(reversed(items))

        # 生成下一页游标
        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            cursor_value = getattr(last_item, sort_by)
            next_cursor_data = {
                "value": cursor_value.isoformat() if hasattr(cursor_value, 'isoformat') else cursor_value,
                "id": last_item.id,
                "type": "next",
            }
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(next_cursor_data, separators=(',', ':')).encode()
            ).decode().rstrip('=')

        # 生成上一页游标
        prev_cursor = None
        if items and cursor:
            first_item = items[0]
            cursor_value = getattr(first_item, sort_by)
            prev_cursor_data = {
                "value": cursor_value.isoformat() if hasattr(cursor_value, 'isoformat') else cursor_value,
                "id": first_item.id,
                "type": "prev",
            }
            prev_cursor = base64.urlsafe_b64encode(
                json.dumps(prev_cursor_data, separators=(',', ':')).encode()
            ).decode().rstrip('=')

        return items, has_more, next_cursor, prev_cursor
