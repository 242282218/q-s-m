from pydantic import BaseModel
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
    normalized_name: str | None = None
    conf: float | None = None
    qual: float | None = None
    alpha: float | None = None
    tags: list[str] | None = None
    size_gb: float | None = None
    c_text: float | None = None
    c_intent: float | None = None
    c_plaus: float | None = None
    p: float | None = None
    r: float | None = None


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