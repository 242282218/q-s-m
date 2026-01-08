from pydantic import BaseModel, Field
from typing import List, Optional


class MediaDto(BaseModel):
    """
    媒体信息DTO
    """
    tmdb_id: int
    title: str
    original_title: str
    year: Optional[int]
    rating: Optional[float]
    overview: str
    poster_path: str
    backdrop_path: str
    media_type: str


class ResourceDto(BaseModel):
    """
    资源DTO
    """
    name: str
    link: str
    overall_score: float
    quality_level: str
    resolution: str
    codec: str
    is_best: bool
    normalized_name: Optional[str] = None
    Conf: Optional[float] = None
    Qual: Optional[float] = None
    alpha: Optional[float] = None
    tags: Optional[List[str]] = None
    size_gb: Optional[float] = None
    C_text: Optional[float] = None
    C_intent: Optional[float] = None
    C_plaus: Optional[float] = None
    P: Optional[float] = None
    R: Optional[float] = None


class SearchResponse(BaseModel):
    """
    搜索响应DTO
    """
    success: bool
    message: Optional[str] = None
    media: Optional[MediaDto] = None
    resources: List[ResourceDto]
    total: int
    query_time: Optional[float] = None