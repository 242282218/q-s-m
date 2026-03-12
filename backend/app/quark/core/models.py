"""
Quark 核心数据模型
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class MediaInfo:
    """
    媒体信息
    """
    tmdb_id: int
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    rating: Optional[float] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    media_type: str = "movie"  # movie 或 tv
    genres: List[str] = field(default_factory=list)
    release_date: Optional[str] = None
    first_air_date: Optional[str] = None


@dataclass
class MatchDetails:
    """
    匹配详情
    """
    exact_title_match: bool = False
    title_match: bool = False
    partial_title_match: bool = False
    year_match: bool = False
    episode_match: bool = False
    season_match: bool = False


@dataclass
class MatchResult:
    """
    匹配结果
    """
    name: str
    link: str
    confidence: float = 0.0
    quality_score: float = 0.0
    overall_score: float = 0.0
    quality_level: str = "未知"
    resolution: str = "未知"
    codec: str = "未知"
    is_best: bool = False
    size: Optional[int] = None
    updatetime: Optional[str] = None
    categoryid: Optional[int] = None
    uploaderid: Optional[str] = None
    views: Optional[int] = None
