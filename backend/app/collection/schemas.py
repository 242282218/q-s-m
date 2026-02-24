"""
Pydantic Schemas for Collection API
"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


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


# ==================== Response Schemas ====================

class CollectionAddResponse(BaseModel):
    """添加收藏的响应"""
    success: bool
    id: Optional[int] = None
    message: str


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


class CollectionListResponse(BaseModel):
    """收藏列表响应"""
    total: int
    page: int
    limit: int
    items: List[CollectionItem]


class CollectionCheckResponse(BaseModel):
    """检查收藏状态响应"""
    collected: bool
    id: Optional[int] = None


class CollectionDeleteResponse(BaseModel):
    """删除收藏响应"""
    success: bool
    message: str
