from typing import Optional, Any

from app.tmdb import TmdbClient


class MediaFetcher:
    """
    媒体获取器，用于从TMDB获取媒体信息
    """
    
    def __init__(self):
        from app.config import get_settings
        settings = get_settings()
        self.tmdb = TmdbClient(
            settings.tmdb_api_key,
            api_base=settings.tmdb_api_base,
            image_base=settings.tmdb_image_base,
            language=settings.default_language,
        )
    
    async def fetch_by_tmdb_id(self, tmdb_id: int, media_type: str = "movie") -> Optional[Any]:
        """
        通过TMDB ID获取媒体信息
        
        Args:
            tmdb_id: TMDB ID
            media_type: 媒体类型（movie或tv）
            
        Returns:
            MediaInfo对象或None
        """
        from app.quark.core.models import MediaInfo
        
        try:
            data = await self.tmdb.details(media_type, tmdb_id)
            
            if not data:
                return None
            
            # 提取年份
            release_date = data.get("release_date") or data.get("first_air_date")
            year = int(release_date[:4]) if release_date else None
            
            # 构建MediaInfo对象
            return MediaInfo(
                tmdb_id=tmdb_id,
                title=data.get("title") or data.get("name"),
                original_title=data.get("original_title") or data.get("original_name"),
                year=year,
                rating=data.get("vote_average"),
                overview=data.get("overview"),
                poster_path=data.get("poster_path"),
                backdrop_path=data.get("backdrop_path"),
                media_type=media_type,
                genres=[genre["name"] for genre in data.get("genres", [])],
                release_date=release_date,
                first_air_date=data.get("first_air_date"),
            )
        except Exception:
            return None
    
    async def search_by_title(self, title: str, year: Optional[int] = None) -> Optional[Any]:
        """
        通过标题搜索媒体信息
        
        Args:
            title: 标题
            year: 年份
            
        Returns:
            MediaInfo对象或None
        """
        try:
            # 先搜索电影
            movie_results = await self.tmdb.search_movies(title, year)
            if movie_results and len(movie_results) > 0:
                first_result = movie_results[0]
                return await self.fetch_by_tmdb_id(first_result["id"], "movie")
            
            # 如果没有找到电影，搜索电视剧
            tv_results = await self.tmdb.search_tv(title, year)
            if tv_results and len(tv_results) > 0:
                first_result = tv_results[0]
                return await self.fetch_by_tmdb_id(first_result["id"], "tv")
            
            return None
        except Exception:
            return None