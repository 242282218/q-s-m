import time
from typing import List, Optional, Any

from app.config import get_settings
from app.quark.core.media_fetcher import MediaFetcher
from app.quark.core.models import MatchResult, MediaInfo
from app.quark.core.quark_client import AsyncQuarkAPIClient
from app.quark.core.cache import get_cache, generate_cache_key
from app.quark.core.enhanced_scoring import score_item

settings = get_settings()


class SearchService:
    """
    搜索服务，用于协调夸克资源搜索的各个组件
    """

    def __init__(self):
        self.media_fetcher = MediaFetcher()
        self.quark_client = AsyncQuarkAPIClient()

    async def search_by_tmdb_id(self, tmdb_id: int, max_results: int, media_type: str = "movie") -> Any:
        """
        通过TMDB ID搜索夸克资源
        
        Args:
            tmdb_id: TMDB ID
            max_results: 最大结果数量
            media_type: 媒体类型
            
        Returns:
            搜索结果对象
        """
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.info(f"search_by_tmdb_id called: tmdb_id={tmdb_id}, max_results={max_results}, media_type={media_type}")
        
        from app.quark.schemas.search import SearchResponse, MediaDto, ResourceDto
        
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:tmdb", tmdb_id=tmdb_id, media_type=media_type)
        
        # 检查缓存
        cached_result = await cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached result: {len(cached_result.get('resources', []))} resources")
            return SearchResponse(**cached_result)
        
        try:
            # 获取媒体信息
            media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, media_type)
            if not media_info:
                # 尝试切换媒体类型
                other_type = "tv" if media_type == "movie" else "movie"
                media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, other_type)
            
            if not media_info:
                return SearchResponse(success=False, message="媒体不存在", resources=[], total=0)
            
            result = await self._search_common(media_info, media_info.title, max_results)
            
            # 存入缓存
            await cache.set(cache_key, result.model_dump())
            
            return result
        except Exception as e:
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)

    async def search_by_title(self, title: str, year: Optional[int], max_results: int) -> Any:
        """
        通过标题搜索夸克资源
        
        Args:
            title: 标题
            year: 年份
            max_results: 最大结果数量
            
        Returns:
            搜索结果对象
        """
        from app.quark.schemas.search import SearchResponse, MediaDto, ResourceDto
        
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:title", title=title, year=year)
        
        # 检查缓存
        cached_result = await cache.get(cache_key)
        if cached_result:
            return SearchResponse(**cached_result)
        
        try:
            # 搜索媒体信息
            media_info = await self.media_fetcher.search_by_title(title, year)
            
            # 如果TMDB搜索失败，尝试直接搜索夸克资源
            if not media_info:
                result = await self._search_direct(title, max_results)
            else:
                result = await self._search_common(media_info, title, max_results)
            
            # 存入缓存
            await cache.set(cache_key, result.model_dump())
            
            return result
        except Exception as e:
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)
    
    async def _search_direct(self, keyword: str, max_results: int) -> Any:
        """
        直接搜索夸克资源，不进行TMDB匹配
        
        Args:
            keyword: 搜索关键词
            max_results: 最大结果数量
            
        Returns:
            搜索结果对象
        """
        from app.quark.schemas.search import SearchResponse, ResourceDto
        
        start = time.time()
        
        # 搜索夸克资源
        resources = await self.quark_client.search_resources(keyword, page_size=max_results or settings.quark_search_max_results)
        
        if not resources:
            return SearchResponse(
                success=True, 
                media=None,
                resources=[], 
                total=0, 
                query_time=round(time.time()-start, 3),
                message="未找到相关资源"
            )
        
        # 评估资源质量
        results: List[ResourceDto] = []
        for resource in resources:
            quality_info = self.quality_evaluator.evaluate(resource.name, resource.size)
            quality_score = quality_info.get_score()
            
            # 默认置信度0.5
            confidence = 0.5
            overall = quality_score * 0.5 + confidence * 50  # 综合评分
            
            results.append(
                ResourceDto(
                    name=resource.name,
                    link=resource.link,
                    confidence=confidence,
                    quality_score=quality_score,
                    overall_score=overall,
                    quality_level=quality_info.level,
                    resolution=quality_info.resolution,
                    codec=quality_info.codec,
                    is_best=False,
                )
            )
        
        # 按综合评分排序，保留所有有效资源
        results = sorted(results, key=lambda x: x.overall_score, reverse=True)
        
        # 标记最佳资源
        if results:
            results[0].is_best = True
        
        return SearchResponse(
            success=True,
            media=None,
            resources=results,
            total=len(results),
            query_time=round(time.time()-start, 3)
        )

    async def _search_common(self, media_info: MediaInfo, keyword: str, max_results: int) -> Any:
        """
        通用搜索逻辑
        
        Args:
            media_info: 媒体信息
            keyword: 搜索关键词
            max_results: 最大结果数量
            
        Returns:
            搜索结果对象
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"_search_common called: keyword={keyword}, max_results={max_results}")
        
        from app.quark.schemas.search import SearchResponse, MediaDto, ResourceDto
        
        start = time.time()
        
        # 搜索夸克资源
        resources = await self.quark_client.search_resources(keyword, page_size=max_results or settings.quark_search_max_results)
        logger.info(f"Quark client returned: {len(resources)} resources")
        if not resources:
            return SearchResponse(
                success=True, 
                media=self._to_media_dto(media_info), 
                resources=[], 
                total=0, 
                query_time=round(time.time()-start, 3)
            )
        
        # 使用新的打分系统
        scored_resources = []
        for resource in resources:
            item_dict = {
                "name": resource.name,
                "link": resource.link,
                "size": resource.size,
                "updatetime": resource.updatetime,
                "categoryid": resource.categoryid,
                "uploaderid": resource.uploaderid,
                "views": resource.views,
                "search_keyword": keyword
            }
            
            score_breakdown = score_item(keyword, item_dict)
            if score_breakdown is not None:
                scored_resources.append((resource, score_breakdown))
        
        # 按最终得分排序
        scored_resources.sort(key=lambda x: x[1]["score"], reverse=True)
        
        # 标记最佳结果
        if scored_resources:
            scored_resources[0] = (scored_resources[0][0], scored_resources[0][1])
        
        # 转换为DTO
        resource_dtos = []
        for resource, breakdown in scored_resources:
            resource_dtos.append(
                ResourceDto(
                    name=resource.name,
                    link=resource.link,
                    overall_score=breakdown["score"],
                    quality_level=self._determine_quality_level(breakdown),
                    resolution=self._determine_resolution(breakdown),
                    codec=self._determine_codec(breakdown),
                    is_best=(scored_resources[0][1] == breakdown),
                    Conf=breakdown["Conf"],
                    Qual=breakdown["Qual"],
                    alpha=breakdown["alpha"],
                    tags=breakdown["tags"],
                    size_gb=breakdown["size_gb"],
                    C_text=breakdown["C_text"],
                    C_intent=breakdown["C_intent"],
                    C_plaus=breakdown["C_plaus"],
                    P=breakdown["P"],
                    R=breakdown["R"],
                )
            )
        
        return SearchResponse(
            success=True,
            media=self._to_media_dto(media_info),
            resources=resource_dtos,
            total=len(resource_dtos),
            query_time=round(time.time()-start, 3)
        )
    
    def _determine_quality_level(self, breakdown: dict) -> str:
        tags = breakdown.get("tags", [])
        if "bdmv" in tags or "remux" in tags:
            return "极高"
        elif "4k" in tags:
            return "高"
        elif "1080p" in tags:
            return "中高"
        elif "720p" in tags:
            return "中"
        else:
            return "低"
    
    def _determine_resolution(self, breakdown: dict) -> str:
        tags = breakdown.get("tags", [])
        if "4k" in tags:
            return "4K"
        elif "1080p" in tags:
            return "1080P"
        elif "720p" in tags:
            return "720P"
        else:
            return "未知"
    
    def _determine_codec(self, breakdown: dict) -> str:
        tags = breakdown.get("tags", [])
        if "bdmv" in tags or "remux" in tags or "bluray" in tags:
            return "H.265/H.264"
        else:
            return "未知"

    def _to_media_dto(self, media: MediaInfo) -> Any:
        """
        转换为媒体DTO
        """
        from app.quark.schemas.search import MediaDto
        
        return MediaDto(
            tmdb_id=media.tmdb_id,
            title=media.title,
            original_title=media.original_title,
            year=media.year,
            rating=media.rating,
            overview=media.overview or "",
            poster_path=media.poster_path or "",
            backdrop_path=media.backdrop_path or "",
            media_type=media.media_type,
        )