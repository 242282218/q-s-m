import time
import logging
import asyncio
from typing import Optional, Any, List, Dict

from app.core.config import get_settings
from app.quark.core.media_fetcher import MediaFetcher
from app.quark.core.models import MediaInfo
from app.quark.core.quark_client import AsyncQuarkAPIClient
from app.quark.core.cache import get_cache, generate_cache_key, generate_hash_key
from app.quark.core.enhanced_scoring import score_item
from app.quark.core.scoring import QualityEvaluator

from app.quark.schemas.search import SearchResponse, MediaDto, ResourceDto

logger = logging.getLogger(__name__)


class SearchService:
    """
    搜索服务

    优化记录:
    - 2026-02-24: 支持外部传入 tmdb_client 和 quark_client，避免重复创建
    - 2026-02-28: 添加并行搜索、缓存优化、超时控制
    """

    # 默认超时时间（秒）
    DEFAULT_TIMEOUT = 30
    # 缓存 TTL（秒）
    CACHE_TTL_SEARCH = 1800  # 30 分钟
    CACHE_TTL_MEDIA = 3600   # 1 小时

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

    async def close(self) -> None:
        """关闭内部创建的资源"""
        if self._internal_quark_client:
            await self._internal_quark_client.close()
        if self._internal_media_fetcher:
            await self._internal_media_fetcher.close()

    @staticmethod
    def _resolve_page_size(max_results: int) -> int:
        if max_results > 0:
            return max_results
        return get_settings().quark_search_max_results

    async def search_by_tmdb_id(
        self,
        tmdb_id: int,
        max_results: int,
        media_type: str = "movie",
        timeout: Optional[int] = None
    ) -> SearchResponse:
        """
        通过 TMDB ID 搜索资源

        Args:
            tmdb_id: TMDB ID
            max_results: 最大结果数
            media_type: 媒体类型 (movie/tv)
            timeout: 超时时间（秒），默认 30 秒
        """
        effective_timeout = timeout or self.DEFAULT_TIMEOUT
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:tmdb", tmdb_id=tmdb_id, media_type=media_type)

        # 1. 检查缓存
        cached_result = await cache.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached result: {len(cached_result.get('resources', []))} resources")
            return SearchResponse(**cached_result)

        try:
            # 2. 使用 asyncio.wait_for 添加超时控制
            result = await asyncio.wait_for(
                self._search_by_tmdb_id_impl(tmdb_id, max_results, media_type),
                timeout=effective_timeout
            )

            # 3. 缓存结果
            if result.success:
                await cache.set(cache_key, result.model_dump(), ttl=self.CACHE_TTL_SEARCH)

            return result

        except asyncio.TimeoutError:
            logger.error(f"search_by_tmdb_id timeout after {effective_timeout}s: tmdb_id={tmdb_id}")
            return SearchResponse(
                success=False,
                message=f"搜索超时（{effective_timeout}秒），请稍后重试",
                resources=[],
                total=0
            )
        except Exception as e:
            logger.error(f"search_by_tmdb_id failed: {e}")
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)

    async def _search_by_tmdb_id_impl(self, tmdb_id: int, max_results: int, media_type: str) -> SearchResponse:
        """内部实现：通过 TMDB ID 搜索"""
        media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, media_type)
        if not media_info:
            # 尝试另一种类型
            other_type = "tv" if media_type == "movie" else "movie"
            media_info = await self.media_fetcher.fetch_by_tmdb_id(tmdb_id, other_type)

        if not media_info:
            return SearchResponse(success=False, message="媒体不存在", resources=[], total=0)

        return await self._search_common(media_info, media_info.title, max_results)

    async def search_by_title(
        self,
        title: str,
        year: Optional[int],
        max_results: int,
        timeout: Optional[int] = None
    ) -> SearchResponse:
        """
        通过标题搜索资源

        Args:
            title: 标题
            year: 年份
            max_results: 最大结果数
            timeout: 超时时间（秒），默认 30 秒
        """
        effective_timeout = timeout or self.DEFAULT_TIMEOUT
        cache = get_cache()
        cache_key = generate_cache_key("quark:search:title", title=title, year=year)

        # 1. 检查缓存
        cached_result = await cache.get(cache_key)
        if cached_result:
            return SearchResponse(**cached_result)

        try:
            # 2. 使用 asyncio.wait_for 添加超时控制
            result = await asyncio.wait_for(
                self._search_by_title_impl(title, year, max_results),
                timeout=effective_timeout
            )

            # 3. 缓存结果
            if result.success:
                await cache.set(cache_key, result.model_dump(), ttl=self.CACHE_TTL_SEARCH)

            return result

        except asyncio.TimeoutError:
            logger.error(f"search_by_title timeout after {effective_timeout}s: title={title}")
            return SearchResponse(
                success=False,
                message=f"搜索超时（{effective_timeout}秒），请稍后重试",
                resources=[],
                total=0
            )
        except Exception as e:
            logger.error(f"search_by_title failed: {e}")
            return SearchResponse(success=False, message=f"搜索失败: {str(e)}", resources=[], total=0)

    async def _search_by_title_impl(self, title: str, year: Optional[int], max_results: int) -> SearchResponse:
        """内部实现：通过标题搜索"""
        media_info = await self.media_fetcher.search_by_title(title, year)

        if not media_info:
            result = await self._search_direct(title, max_results)
        else:
            result = await self._search_common(media_info, title, max_results)

        return result

    async def batch_search(
        self,
        queries: List[Dict[str, Any]],
        max_results: int = 10,
        timeout: Optional[int] = None
    ) -> List[SearchResponse]:
        """
        批量搜索（并行处理）

        Args:
            queries: 查询列表，每个查询为 {"tmdb_id": int, "media_type": str} 或 {"title": str, "year": int}
            max_results: 每个查询的最大结果数
            timeout: 每个查询的超时时间（秒）

        Returns:
            SearchResponse 列表，与 queries 顺序一致
        """
        async def search_one(query: Dict[str, Any]) -> SearchResponse:
            if "tmdb_id" in query:
                return await self.search_by_tmdb_id(
                    query["tmdb_id"],
                    max_results,
                    query.get("media_type", "movie"),
                    timeout
                )
            else:
                return await self.search_by_title(
                    query.get("title", ""),
                    query.get("year"),
                    max_results,
                    timeout
                )

        # 使用 asyncio.gather 并行执行所有搜索
        results = await asyncio.gather(*[search_one(q) for q in queries])
        return list(results)

    async def _search_direct(self, keyword: str, max_results: int) -> SearchResponse:
        """直接搜索（无媒体信息）"""
        start = time.time()
        page_size = self._resolve_page_size(max_results)

        resources = await self.quark_client.search_resources(
            keyword,
            page_size=page_size
        )

        if not resources:
            return SearchResponse(
                success=True,
                media=None,
                resources=[],
                total=0,
                query_time=round(time.time() - start, 3),
                message="未找到相关资源"
            )

        # 并行处理资源评分
        results = await self._process_resources_parallel(resources, keyword)

        results = sorted(results, key=lambda x: x.overall_score, reverse=True)

        if results:
            results[0].is_best = True

        return SearchResponse(
            success=True,
            media=None,
            resources=results,
            total=len(results),
            query_time=round(time.time() - start, 3)
        )

    async def _search_common(self, media_info: MediaInfo, keyword: str, max_results: int) -> SearchResponse:
        """通用搜索逻辑"""
        logger.info(f"_search_common called: keyword={keyword}, max_results={max_results}")

        start = time.time()
        page_size = self._resolve_page_size(max_results)

        resources = await self.quark_client.search_resources(
            keyword,
            page_size=page_size
        )
        logger.info(f"Quark client returned: {len(resources)} resources")

        if not resources:
            return SearchResponse(
                success=True,
                media=self._to_media_dto(media_info),
                resources=[],
                total=0,
                query_time=round(time.time() - start, 3)
            )

        # 并行处理资源评分
        resource_dtos = await self._score_resources_parallel(resources, keyword)

        return SearchResponse(
            success=True,
            media=self._to_media_dto(media_info),
            resources=resource_dtos,
            total=len(resource_dtos),
            query_time=round(time.time() - start, 3)
        )

    async def _process_resources_parallel(
        self,
        resources: List[Any],
        keyword: str
    ) -> List[ResourceDto]:
        """并行处理资源评分"""
        async def process_one(resource: Any) -> Optional[ResourceDto]:
            quality_info = self.quality_evaluator.evaluate(resource.name, resource.size)
            quality_score = quality_info.get_score()
            confidence = 0.5
            overall = quality_score * 0.5 + confidence * 50

            return ResourceDto(
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

        # 使用 asyncio.gather 并行处理
        results = await asyncio.gather(*[process_one(r) for r in resources])
        return [r for r in results if r is not None]

    async def _score_resources_parallel(
        self,
        resources: List[Any],
        keyword: str
    ) -> List[ResourceDto]:
        """并行评分资源"""
        async def score_one(resource: Any) -> Optional[tuple]:
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
                return None
            return (resource, score_breakdown)

        # 并行评分
        scored_results = await asyncio.gather(*[score_one(r) for r in resources])
        scored_resources = [r for r in scored_results if r is not None]

        # 排序
        scored_resources.sort(key=lambda x: x[1]["score"], reverse=True)

        # 构建 DTO
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
                    conf=breakdown.get("Conf") or breakdown.get("conf"),
                    qual=breakdown.get("Qual") or breakdown.get("qual"),
                    alpha=breakdown.get("alpha"),
                    tags=breakdown.get("tags", []),
                    size_gb=breakdown.get("size_gb"),
                    c_text=breakdown.get("C_text") or breakdown.get("c_text"),
                    c_intent=breakdown.get("C_intent") or breakdown.get("c_intent"),
                    c_plaus=breakdown.get("C_plaus") or breakdown.get("c_plaus"),
                    p=breakdown.get("P") or breakdown.get("p"),
                    r=breakdown.get("R") or breakdown.get("r"),
                )
            )

        return resource_dtos

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

    async def get_cached_search(self, cache_key: str) -> Optional[SearchResponse]:
        """获取缓存的搜索结果"""
        cache = get_cache()
        cached = await cache.get(cache_key)
        if cached:
            return SearchResponse(**cached)
        return None

    async def cache_search_result(self, cache_key: str, result: SearchResponse) -> None:
        """缓存搜索结果"""
        if result.success:
            cache = get_cache()
            await cache.set(cache_key, result.model_dump(), ttl=self.CACHE_TTL_SEARCH)
