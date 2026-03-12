"""
Pydantic Schemas for Collection API
"""
from datetime import datetime
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from ..api.schemas.common import Pagination, CursorPagination


MediaType = Literal["movie", "tv"]
CategoryType = Literal["movie", "tv", "anime", "documentary"]


class CollectionAddRequest(BaseModel):
    """添加收藏的请求体"""
    model_config = ConfigDict(defer_build=True)

    tmdb_id: int = Field(..., gt=0, description="TMDB ID")
    media_type: MediaType = Field(..., description="媒体类型: movie 或 tv")
    title: str = Field(..., min_length=1, max_length=255, description="标题")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="年份")
    poster_path: Optional[str] = Field(None, max_length=255, description="海报路径")
    backdrop_path: Optional[str] = Field(None, max_length=255, description="背景图路径")
    share_url: str = Field(..., min_length=1, max_length=1024, description="夸克分享链接")
    share_pwd: Optional[str] = Field(None, max_length=20, description="分享密码")
    file_structure: Optional[Any] = Field(None, description="文件结构 (JSON)")
    category: Optional[CategoryType] = Field(None, description="分类: movie, tv, anime, documentary")


# ==================== Data Schemas ====================

class CollectionAddData(BaseModel):
    """添加收藏数据"""
    model_config = ConfigDict(defer_build=True)

    created: bool
    id: Optional[int] = None


class CollectionItem(BaseModel):
    """收藏列表项"""
    model_config = ConfigDict(defer_build=True, from_attributes=True)

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


class CollectionListData(BaseModel):
    """收藏列表数据"""
    model_config = ConfigDict(defer_build=True)

    items: List[CollectionItem]
    pagination: Pagination


class CollectionListCursorData(BaseModel):
    """收藏列表数据（游标分页）"""
    model_config = ConfigDict(defer_build=True)

    items: List[CollectionItem]
    pagination: CursorPagination


class CollectionCheckData(BaseModel):
    """检查收藏状态数据"""
    model_config = ConfigDict(defer_build=True)

    collected: bool
    id: Optional[int] = None


class CollectionDeleteData(BaseModel):
    """删除收藏数据"""
    model_config = ConfigDict(defer_build=True)

    deleted: bool


class CollectionCheckLinkData(BaseModel):
    """检查链接收藏状态数据"""
    model_config = ConfigDict(defer_build=True)

    collected: bool
    id: Optional[int] = None
    status: Optional[int] = None


class CollectionCheckLinksRequest(BaseModel):
    """批量检查链接收藏状态请求"""
    model_config = ConfigDict(defer_build=True)

    links: List[str] = Field(..., description="分享链接列表")


class CollectionLinkStatus(BaseModel):
    """单个链接的收藏状态"""
    model_config = ConfigDict(defer_build=True)

    link: str
    collected: bool
    id: Optional[int] = None
    status: Optional[int] = None


class CollectionCheckLinksData(BaseModel):
    """批量检查链接收藏状态数据"""
    model_config = ConfigDict(defer_build=True)

    results: List[CollectionLinkStatus]


class CollectionVerifyRequest(BaseModel):
    """批量验证收藏网盘状态请求"""
    model_config = ConfigDict(defer_build=True)

    collection_ids: Optional[List[int]] = Field(
        default=None,
        description="可选，仅验证这些收藏 ID（为空时验证全部状态为 1/3 的收藏）",
    )


class CollectionVerifyResult(BaseModel):
    """收藏网盘状态验证结果"""
    model_config = ConfigDict(defer_build=True)

    collection_id: int
    title: str
    previous_status: int
    current_status: int
    exists: bool
    checked_path: str
    path_source: str


class CollectionVerifySingleData(BaseModel):
    """单条收藏网盘状态验证数据"""
    model_config = ConfigDict(defer_build=True)

    result: CollectionVerifyResult


# ==================== Batch Operation Schemas ====================

class CollectionBatchAddRequest(BaseModel):
    """批量添加收藏请求"""
    model_config = ConfigDict(defer_build=True)

    items: List[CollectionAddRequest] = Field(..., description="收藏列表", max_length=50)


class CollectionBatchAddResult(BaseModel):
    """批量添加收藏结果项"""
    model_config = ConfigDict(defer_build=True)

    index: int
    success: bool
    id: Optional[int] = None
    message: str = ""


class CollectionBatchAddData(BaseModel):
    """批量添加收藏响应数据"""
    model_config = ConfigDict(defer_build=True)

    total: int
    success_count: int
    failed_count: int
    results: List[CollectionBatchAddResult]


class CollectionBatchDeleteRequest(BaseModel):
    """批量删除收藏请求"""
    model_config = ConfigDict(defer_build=True)

    ids: List[int] = Field(..., description="收藏ID列表", max_length=100)


class CollectionBatchDeleteResult(BaseModel):
    """批量删除收藏结果项"""
    model_config = ConfigDict(defer_build=True)

    id: int
    success: bool
    message: str = ""


class CollectionBatchDeleteData(BaseModel):
    """批量删除收藏响应数据"""
    model_config = ConfigDict(defer_build=True)

    total: int
    success_count: int
    failed_count: int
    results: List[CollectionBatchDeleteResult]
