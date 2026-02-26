"""
Pydantic Schemas for Collection API
"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field

from ..api.schemas.common import Pagination


# ==================== Request Schemas ====================

class CollectionAddRequest(BaseModel):
    """添加收藏的请求体"""
    tmdb_id: int = Field(..., description="TMDB ID")
    media_type: str = Field(..., description="媒体类型: movie 或 tv")
    title: str = Field(..., description="标题")
    year: Optional[int] = Field(None, description="年份")
    poster_path: Optional[str] = Field(None, description="海报路径")
    backdrop_path: Optional[str] = Field(None, description="背景图路径")
    share_url: str = Field(..., description="夸克分享链接")
    share_pwd: Optional[str] = Field(None, description="分享密码")
    file_structure: Optional[Any] = Field(None, description="文件结构 (JSON)")
    category: Optional[str] = Field(None, description="分类: movie, tv, anime, documentary")

    class Config:
        json_schema_extra = {
            "example": {
                "tmdb_id": 27205,
                "media_type": "movie",
                "title": "盗梦空间",
                "year": 2010,
                "poster_path": "/poster.jpg",
                "share_url": "https://pan.quark.cn/s/xxxxx"
            }
        }


# ==================== Data Schemas ====================

class CollectionAddData(BaseModel):
    """添加收藏数据"""
    created: bool
    id: Optional[int] = None


class CollectionItem(BaseModel):
    """收藏列表项"""
    id: int
    tmdb_id: int
    media_type: str
    title: str
    year: Optional[int] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    quark_share_url: str
    category: Optional[str] = None
    status: int = 0
    saved_at: datetime

    class Config:
        from_attributes = True  # 支持 ORM 模型转换


class CollectionListData(BaseModel):
    """收藏列表数据"""
    items: List[CollectionItem]
    pagination: Pagination


class CollectionCheckData(BaseModel):
    """检查收藏状态数据"""
    collected: bool
    id: Optional[int] = None


class CollectionDeleteData(BaseModel):
    """删除收藏数据"""
    deleted: bool


class CollectionCheckLinkData(BaseModel):
    """检查链接收藏状态数据"""
    collected: bool
    id: Optional[int] = None
    status: Optional[int] = None


class CollectionCheckLinksRequest(BaseModel):
    """批量检查链接收藏状态请求"""
    links: List[str] = Field(..., description="分享链接列表")


class CollectionLinkStatus(BaseModel):
    """单个链接的收藏状态"""
    link: str
    collected: bool
    id: Optional[int] = None
    status: Optional[int] = None


class CollectionCheckLinksData(BaseModel):
    """批量检查链接收藏状态数据"""
    results: List[CollectionLinkStatus]


class CollectionVerifyRequest(BaseModel):
    """批量验证收藏网盘状态请求"""
    collection_ids: Optional[List[int]] = Field(
        default=None,
        description="可选，仅验证这些收藏 ID（为空时验证全部状态为 1/3 的收藏）",
    )


class CollectionVerifyResult(BaseModel):
    """收藏网盘状态验证结果"""
    collection_id: int
    title: str
    previous_status: int
    current_status: int
    exists: bool
    checked_path: str
    path_source: str


class CollectionVerifySingleData(BaseModel):
    """单条收藏网盘状态验证数据"""
    result: CollectionVerifyResult
