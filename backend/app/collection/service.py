"""
Collection 业务逻辑服务
"""
import json
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from sqlalchemy.exc import IntegrityError

from ..db.models import Collection


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
        
        Returns:
            (success, id, message)
        """
        # 检查是否已存在（按分享链接判断，支持同一影片多版本收藏）
        existing = self.db.query(Collection).filter(
            Collection.quark_share_url == share_url
        ).first()
        
        if existing:
            return False, existing.id, "该链接已收藏"
        
        # 自动识别分类
        if not category:
            category = media_type  # 默认使用 media_type
        
        # 处理 file_structure
        file_structure_json = None
        if file_structure:
            file_structure_json = json.dumps(file_structure, ensure_ascii=False)
        
        # 创建新收藏
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
            return True, collection.id, "收藏成功"
        except IntegrityError:
            self.db.rollback()
            return False, None, "收藏失败: 数据冲突"
        except Exception as e:
            self.db.rollback()
            return False, None, f"收藏失败: {str(e)}"

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
        
        Returns:
            (total, items)
        """
        query = self.db.query(Collection)
        
        # 过滤条件
        if category:
            query = query.filter(Collection.category == category)
        if status is not None:
            query = query.filter(Collection.status == status)
        
        # 总数
        total = query.count()
        
        # 排序
        sort_column = getattr(Collection, sort_by, Collection.saved_at)
        if order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # 分页
        offset = (page - 1) * limit
        items = query.offset(offset).limit(limit).all()
        
        # 注意：暂时不在这里调用TMDB API获取海报
        # 因为list方法是同步的，而TMDB客户端的方法是异步的
        # 这里返回原始数据，让前端处理
        
        return total, items

    def check(self, tmdb_id: int, media_type: str) -> Tuple[bool, Optional[int]]:
        """
        检查是否已收藏
        
        Returns:
            (collected, id)
        """
        collection = self.db.query(Collection).filter(
            Collection.tmdb_id == tmdb_id,
            Collection.media_type == media_type
        ).first()
        
        if collection:
            return True, collection.id
        return False, None

    def get_by_id(self, collection_id: int) -> Optional[Collection]:
        """根据 ID 获取收藏"""
        return self.db.query(Collection).filter(Collection.id == collection_id).first()

    def delete(self, collection_id: int) -> Tuple[bool, str]:
        """
        删除收藏
        
        Returns:
            (success, message)
        """
        collection = self.get_by_id(collection_id)
        if not collection:
            return False, "收藏不存在"
        
        try:
            self.db.delete(collection)
            self.db.commit()
            return True, "删除成功"
        except Exception as e:
            self.db.rollback()
            return False, f"删除失败: {str(e)}"

    def update_status(self, collection_id: int, status: int) -> Tuple[bool, str]:
        """更新收藏状态"""
        collection = self.get_by_id(collection_id)
        if not collection:
            return False, "收藏不存在"
        
        collection.status = status
        self.db.commit()
        return True, "状态更新成功"

    def update_last_played(self, collection_id: int) -> Tuple[bool, str]:
        """更新最后播放时间"""
        collection = self.get_by_id(collection_id)
        if not collection:
            return False, "收藏不存在"
        
        collection.last_played_at = datetime.utcnow()
        self.db.commit()
        return True, "更新成功"
