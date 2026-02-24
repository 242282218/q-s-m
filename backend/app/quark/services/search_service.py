import re
import math
import time
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from app.core.config import get_settings
from app.quark.core.media_fetcher import MediaFetcher
from app.quark.core.models import MatchResult, MediaInfo
from app.quark.core.quark_client import AsyncQuarkAPIClient
from app.quark.core.cache import get_cache, generate_cache_key
from app.quark.core.enhanced_scoring import score_item
from app.quark.core.scoring import QualityEvaluator

from app.quark.schemas.search import SearchResponse, MediaDto, ResourceDto

settings = get_settings()
logger = logging.getLogger(__name__)


class SearchService:
    """
    搜索服务
    
    优化记录:
    - 2026-02-24: 支持外部传入 tmdb_client 和 quark_client，避免重复创建
    """
    def __init__(
        self,
        tmdb_client: Optional[Any] = None,
        quark_client: Optional[AsyncQuarkAPIClient] = None
    ):
        self._external_tmdb_client = tmdb_client
        self._external_quark_client = quark_client
        self._internal_media_fetcher: Optional[MediaFetcher] = None
        self._internal_quark_client: Optional[AsyncQuarkAPIClient] = None
        self.quality_evaluator = QualityEvaluator()
    
    @property
    def media_fetcher(self) -> MediaFetcher:
        if self._internal_media_fetcher is None:
            self._internal_media_fetcher = MediaFetcher(tmdb_client=self._external_tmdb_client)
        return self._internal_media_fetcher
    
    @property
    def quark_client(self) -> AsyncQuarkAPIClient:
        if self._external_quark_client:
            return self._external_quark_client
        if self._internal_quark_client is None:
            self._internal_quark_client = AsyncQuarkAPIClient()
        return self._internal_quark_client

    async def search_by_tmdb_id(self, tmdb_id: int, max_results: int, media_type: str = "movie") -> SearchResponse:
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:tmdb", tmdb_id=tmdb_id, media_type=media_type)
        
        cached_result = await cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached result: {len(cached_result.get('resources', []))} resources")
            return SearchResponse(**cached_result)
        
        try:
            media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, media_type)
            if not media_info:
                other_type = "tv" if media_type == "movie" else "movie"
                media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, other_type)
            
            if not media_info:
                return SearchResponse(success=False, message="媒体不存在", resources=[], total=0)
            
            result = await self._search_common(media_info, media_info.title, max_results)
            
            await cache.set(cache_key, result.model_dump())
            
            return result
        except Exception as e:
            logger.error(f"search_by_tmdb_id failed: {e}")
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)
    
    async def search_by_title(self, title: str, year: Optional[int], max_results: int) -> SearchResponse:
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:title", title=title, year=year)
        
        cached_result = await cache.get(cache_key)
        if cached_result:
            return SearchResponse(**cached_result)
        
        try:
            media_info = await self.media_fetcher.search_by_title(title, year)
            
            if not media_info:
                result = await self._search_direct(title, max_results)
            else:
                result = await self._search_common(media_info, title, max_results)
            
            await cache.set(cache_key, result.model_dump())
            
            return result
        except Exception as e:
            logger.error(f"search_by_title failed: {e}")
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)
    
    async def _search_direct(self, keyword: str, max_results: int) -> SearchResponse:
        start = time.time()
        
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
        
        results: List[ResourceDto] = []
        for resource in resources:
            quality_info = self.quality_evaluator.evaluate(resource.name, resource.size)
            quality_score = quality_info.get_score()
            
            confidence = 0.5
            overall = quality_score * 0.5 + confidence * 50
            
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
        
        results = sorted(results, key=lambda x: x.overall_score, reverse=True)
        
        if results:
            results[0].is_best = True
        
        return SearchResponse(
            success=True,
            media=None,
            resources=results,
            total=len(results),
            query_time=round(time.time()-start, 3)
        )
    
    async def _search_common(self, media_info: MediaInfo, keyword: str, max_results: int) -> SearchResponse:
        logger.info(f"_search_common called: keyword={keyword}, max_results={max_results}")
        
        start = time.time()
        
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
            if score_breakdown is None:
                continue
            scored_resources.append((resource, score_breakdown))
        
        scored_resources.sort(key=lambda x: x[1]["score"], reverse=True)
        
        resource_dtos = []
        for idx, (resource, breakdown) in enumerate(scored_resources):
            resource_dtos.append(
                ResourceDto(
                    name=resource.name,
                    link=resource.link,
                    overall_score=breakdown["score"],
                    quality_level=self._determine_quality_level(breakdown),
                    resolution=self._determine_resolution(breakdown),
                    codec=self._determine_codec(breakdown),
                    is_best=(idx == 0),
                    Conf=breakdown.get("Conf"),
                    Qual=breakdown.get("Qual"),
                    alpha=breakdown.get("alpha"),
                    tags=breakdown.get("tags", []),
                    size_gb=breakdown.get("size_gb"),
                    C_text=breakdown.get("C_text"),
                    C_intent=breakdown.get("C_intent"),
                    C_plaus=breakdown.get("C_plaus"),
                    P=breakdown.get("P"),
                    R=breakdown.get("R"),
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
    
    def _to_media_dto(self, media: MediaInfo) -> MediaDto:
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
