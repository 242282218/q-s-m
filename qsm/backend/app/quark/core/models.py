from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class MediaInfo:
    """媒体信息数据类"""
    tmdb_id: int
    title: str
    original_title: str
    year: Optional[int]
    rating: Optional[float]
    overview: str
    poster_path: str
    backdrop_path: str
    media_type: str
    genres: Optional[list] = None
    release_date: Optional[str] = None
    first_air_date: Optional[str] = None


@dataclass
class QualityInfo:
    """画质信息数据类"""
    level: str
    resolution: str
    codec: str
    total_size_gb: Optional[float] = None
    size: Optional[str] = None
    is_dynamic: bool = False
    is_uhd: bool = False

    def get_score(self) -> float:
        """计算画质评分"""
        score = 0.0
        
        # 分辨率评分
        resolution_scores = {
            "8K": 100,
            "4K": 90,
            "2K": 80,
            "1080P": 70,
            "720P": 60,
            "480P": 50,
            "360P": 40,
        }
        score += resolution_scores.get(self.resolution, 0)
        
        # 编解码器评分
        codec_scores = {
            "H.265": 30,
            "HEVC": 30,
            "H.264": 20,
            "AVC": 20,
            "MPEG-4": 10,
        }
        score += codec_scores.get(self.codec, 0)
        
        # 动态范围评分
        if self.is_dynamic:
            score += 20
        
        # 超高清评分
        if self.is_uhd:
            score += 10
        
        return min(score, 100.0)


@dataclass
class MatchDetails:
    """匹配详情数据类"""
    title_match: bool = False
    year_match: bool = False
    exact_title_match: bool = False
    partial_title_match: bool = False
    episode_match: bool = False
    season_match: bool = False
    
    def get_confidence(self, weights: Dict[str, float]) -> float:
        """计算置信度"""
        confidence = 0.0
        
        if self.exact_title_match:
            confidence += weights.get("exact_title_match", 0.5)
        elif self.title_match:
            confidence += weights.get("title_match", 0.3)
        elif self.partial_title_match:
            confidence += weights.get("partial_title_match", 0.2)
        
        if self.year_match:
            confidence += weights.get("year_match", 0.2)
        
        if self.episode_match:
            confidence += weights.get("episode_match", 0.1)
        
        if self.season_match:
            confidence += weights.get("season_match", 0.1)
        
        return min(confidence, 1.0)


@dataclass
class MatchResult:
    """匹配结果数据类"""
    resource: Any  # QuarkResource
    media_info: MediaInfo
    confidence: float
    quality_score: float
    overall_score: float
    match_details: MatchDetails
    quality_info: QualityInfo
    is_best: bool = False