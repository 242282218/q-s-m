"""
SQLAlchemy ORM 模型定义
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from .session import Base


class Collection(Base):
    """
    虚拟收藏表 - 存储收藏的影视资源元数据
    """
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, nullable=False, index=True)
    media_type = Column(String(10), nullable=False)  # 'movie' 或 'tv'
    title = Column(String(255), nullable=False)
    year = Column(Integer, nullable=True)
    poster_path = Column(String(255), nullable=True)
    backdrop_path = Column(String(255), nullable=True)
    quark_share_url = Column(String(1024), nullable=False)
    quark_share_pwd = Column(String(20), nullable=True)
    file_structure = Column(Text, nullable=True)  # JSON 格式存储文件夹结构
    category = Column(String(20), nullable=True)  # 'movie', 'tv', 'anime', 'documentary'
    status = Column(Integer, default=0)  # 0: 仅链接, 1: 已转存, 2: 已失效
    saved_at = Column(DateTime, default=datetime.utcnow)
    last_played_at = Column(DateTime, nullable=True)

    # 关联转存记录
    transfer_records = relationship("TransferHistory", back_populates="collection", cascade="all, delete-orphan")

    # 索引配置（按share_url唯一，支持多版本收藏）
    __table_args__ = (
        Index('idx_collections_share_url', 'quark_share_url', unique=True),
        Index('idx_collections_tmdb', 'tmdb_id', 'media_type'),  # 非唯一索引用于查询
        Index('idx_collections_status', 'status'),
    )

    def __repr__(self):
        return f"<Collection(id={self.id}, title='{self.title}', tmdb_id={self.tmdb_id})>"


class TransferHistory(Base):
    """
    转存记录表 - 记录已转存到网盘的文件
    """
    __tablename__ = "transfer_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    quark_fid = Column(String(64), nullable=False)  # 夸克网盘文件 ID
    local_path = Column(String(512), nullable=False)  # 网盘内路径
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    transferred_at = Column(DateTime, default=datetime.utcnow)

    # 关联收藏
    collection = relationship("Collection", back_populates="transfer_records")

    def __repr__(self):
        return f"<TransferHistory(id={self.id}, file_name='{self.file_name}')>"
