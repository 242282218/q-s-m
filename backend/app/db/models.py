"""
SQLAlchemy ORM 模型定义

优化记录:
- 2026-02-28: 添加复合索引优化常用查询场景
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, desc
from sqlalchemy.orm import relationship

from .session import Base


def utc_now() -> datetime:
    """返回带时区信息的 UTC 时间"""
    return datetime.now(timezone.utc)


class Collection(Base):
    """
    虚拟收藏表 - 存储收藏的影视资源元数据
    """
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, nullable=False, index=True)
    media_type = Column(String(10), nullable=False, index=True)  # 'movie' 或 'tv'
    title = Column(String(255), nullable=False, index=True)  # 添加索引支持标题搜索
    year = Column(Integer, nullable=True, index=True)  # 添加索引支持年份筛选
    poster_path = Column(String(255), nullable=True)
    backdrop_path = Column(String(255), nullable=True)
    quark_share_url = Column(String(1024), nullable=False)
    quark_share_pwd = Column(String(20), nullable=True)
    file_structure = Column(Text, nullable=True)  # JSON 格式存储文件夹结构
    category = Column(String(20), nullable=True, index=True)  # 'movie', 'tv', 'anime', 'documentary'
    status = Column(Integer, default=0, index=True)  # 0: 仅链接, 1: 已转存, 2: 已失效, 3: 网盘已删除
    saved_at = Column(DateTime, default=utc_now, index=True)  # 添加索引支持时间排序
    last_played_at = Column(DateTime, nullable=True, index=True)

    # 关联转存记录 - 使用 selectinload 优化 N+1 查询
    transfer_records = relationship(
        "TransferHistory",
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy="selectin"  # 优化：使用 selectin 加载策略避免 N+1
    )

    # 索引配置（按share_url唯一，支持多版本收藏）
    __table_args__ = (
        Index('idx_collections_share_url', 'quark_share_url', unique=True),
        Index('idx_collections_tmdb', 'tmdb_id', 'media_type'),  # 复合索引用于 TMDB 查询
        Index('idx_collections_status_saved', 'status', 'saved_at'),  # 优化：状态+时间复合索引用于列表筛选排序
        Index('idx_collections_category_status', 'category', 'status'),  # 优化：分类+状态复合索引
        Index('idx_collections_year_type', 'year', 'media_type'),  # 优化：年份+类型复合索引
        Index('idx_collections_title', 'title'),  # 标题索引用于搜索
    )

    def __repr__(self):
        return f"<Collection(id={self.id}, title='{self.title}', tmdb_id={self.tmdb_id})>"


class TransferHistory(Base):
    """
    转存记录表 - 记录已转存到网盘的文件
    """
    __tablename__ = "transfer_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    quark_fid = Column(String(64), nullable=False, index=True)  # 夸克网盘文件 ID，添加索引
    local_path = Column(String(512), nullable=False, index=True)  # 网盘内路径，添加索引
    file_name = Column(String(255), nullable=False, index=True)  # 文件名索引用于搜索
    file_size = Column(Integer, nullable=True)
    transferred_at = Column(DateTime, default=utc_now, index=True)  # 时间索引用于排序

    # 关联收藏 - 使用 selectin 加载策略
    collection = relationship(
        "Collection",
        back_populates="transfer_records",
        lazy="selectin"  # 优化：使用 selectin 加载策略避免 N+1
    )

    # 复合索引优化常用查询
    __table_args__ = (
        Index('idx_transfer_collection_time', 'collection_id', 'transferred_at'),  # 优化：收藏+时间复合索引
        Index('idx_transfer_path_name', 'local_path', 'file_name'),  # 优化：路径+文件名复合索引
    )

    def __repr__(self):
        return f"<TransferHistory(id={self.id}, file_name='{self.file_name}')>"
