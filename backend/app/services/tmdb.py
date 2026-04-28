from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from asyncio import AbstractEventLoop
from typing import Any, Dict, List, Optional
import logging
import time
from weakref import WeakKeyDictionary

import httpx

from ..core.config import get_settings
from ..quark.core.cache import get_cache

DEFAULT_POSTER_SIZE = "w500"
DEFAULT_BACKDROP_SIZE = "w780"
DEFAULT_LANG = "zh-CN"
HOME_SECTIONS_CACHE_TTL = 300
DETAIL_CACHE_TTL = 600  # 详情页缓存10分钟
SEARCH_CACHE_TTL = 180  # 搜索结果缓存3分钟

GENRE_TONE = {
    10749: "romance",
    10751: "family",
    18: "drama",
    80: "action",
    9648: "mystery",
    53: "mystery",
    27: "mystery",
    878: "scifi",
    14: "scifi",
}

logger = logging.getLogger(__name__)
HOME_SECTIONS_CACHE_KEY = "tmdb:home_sections"
_home_sections_cache_locks: WeakKeyDictionary[AbstractEventLoop, asyncio.Lock] = (
    WeakKeyDictionary()
)


def _build_tmdb_cache_key(path: str, params: Dict[str, Any]) -> str:
    serialized = json.dumps(
        params,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.md5(serialized.encode("utf-8")).hexdigest()[:16]
    return f"tmdb:{path}:{digest}"


def _get_home_sections_cache_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _home_sections_cache_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _home_sections_cache_locks[loop] = lock
    return lock


class TmdbClient:
    """
    TMDB API 客户端 - 性能优化版本
    
    优化记录:
    - 2026-02-26: 添加连接池、keep-alive、请求缓存、批量请求优化
    """
    
    # 类级别的共享连接池
    _shared_transport: Optional[httpx.AsyncHTTPTransport] = None
    _shared_limits: Optional[httpx.Limits] = None
    
    def __init__(
        self,
        api_key: str,
        *,
        api_base: Optional[str] = None,
        image_base: Optional[str] = None,
        language: str = DEFAULT_LANG,
        proxy: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key
        self.api_base = api_base or settings.tmdb_api_base
        self.image_base = image_base or settings.tmdb_image_base
        self.language = language or settings.default_language
        
        # 代理配置
        import os
        system_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        settings_proxy = settings.http_proxy
        final_proxy = proxy or settings_proxy or system_proxy
        
        if final_proxy:
            logger.info(f"TmdbClient utilizing proxy: {final_proxy}")
        else:
            logger.info("TmdbClient initialized without explicit proxy")
        
        # 优化：使用共享连接池配置
        if TmdbClient._shared_limits is None:
            TmdbClient._shared_limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=60.0
            )
        
        if TmdbClient._shared_transport is None:
            TmdbClient._shared_transport = httpx.AsyncHTTPTransport(
                limits=TmdbClient._shared_limits,
                retries=2  # 自动重试
            )
        
        self._client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",  # 启用压缩
            },
            timeout=httpx.Timeout(timeout, connect=3.0),
            proxy=final_proxy,
            trust_env=True,
            transport=TmdbClient._shared_transport,
            # http2=True,  # 需要安装 httpx[http2]，暂不使用
        )
        
        # 请求统计
        self._request_count = 0
        self._cache_hits = 0

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        """
        发送 GET 请求，支持缓存
        
        Args:
            path: API 路径
            params: 查询参数
            use_cache: 是否使用缓存
        """
        params = params or {}
        params.setdefault("api_key", self.api_key)
        params.setdefault("language", self.language)
        
        # 生成缓存键
        cache_key = None
        if use_cache:
            cache_key = _build_tmdb_cache_key(path, params)
            cache = get_cache()
            cached = await cache.get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                logger.debug(f"Cache hit for {path}")
                return cached
        
        self._request_count += 1
        start_time = time.time()
        
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            # 缓存结果
            if use_cache and cache_key:
                cache = get_cache()
                ttl = DETAIL_CACHE_TTL if "/" in path and path.split("/")[-1].isdigit() else SEARCH_CACHE_TTL
                await cache.set(cache_key, data, ttl=ttl)
            
            elapsed = time.time() - start_time
            if elapsed > 0.5:
                logger.warning(f"Slow TMDB request: {elapsed:.2f}s for {path}")
            
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"TMDB HTTP error {e.response.status_code} for {path}: {e}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"TMDB request timeout for {path}: {e}")
            raise
        except httpx.NetworkError as e:
            logger.error(f"TMDB network error for {path}: {e}")
            raise
        except httpx.ProtocolError as e:
            logger.error(f"TMDB protocol error for {path}: {e}")
            raise
        except Exception as e:
            error_msg = f"TMDB request failed for {path}: {type(e).__name__}: {str(e) or 'Unknown error'}"
            logger.error(error_msg, exc_info=True)
            raise

    async def trending(self, media_type: str = "all", window: str = "week") -> List[Dict[str, Any]]:
        data = await self._get(f"/trending/{media_type}/{window}")
        return data.get("results", [])

    async def movies(self, category: str = "popular") -> List[Dict[str, Any]]:
        data = await self._get(f"/movie/{category}")
        return data.get("results", [])

    async def tv(self, category: str = "popular") -> List[Dict[str, Any]]:
        data = await self._get(f"/tv/{category}")
        return data.get("results", [])

    async def discover_movies(
        self,
        *,
        with_genres: Optional[str] = None,
        with_original_language: Optional[str] = None,
        region: Optional[str] = None,
        with_origin_country: Optional[str] = None,
        sort_by: str = "popularity.desc",
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"page": page, "sort_by": sort_by}
        if with_genres:
            params["with_genres"] = with_genres
        if with_original_language:
            params["with_original_language"] = with_original_language
        if region:
            params["region"] = region
        if with_origin_country:
            params["with_origin_country"] = with_origin_country
        data = await self._get("/discover/movie", params=params)
        return data.get("results", [])

    async def discover_tv(
        self,
        *,
        with_genres: Optional[str] = None,
        with_original_language: Optional[str] = None,
        with_origin_country: Optional[str] = None,
        with_type: Optional[str] = None,
        sort_by: str = "popularity.desc",
        page: int = 1,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"page": page, "sort_by": sort_by}
        if with_genres:
            params["with_genres"] = with_genres
        if with_original_language:
            params["with_original_language"] = with_original_language
        if with_origin_country:
            params["with_origin_country"] = with_origin_country
        if with_type:
            params["with_type"] = with_type
        if extra_params:
            params.update(extra_params)
        data = await self._get("/discover/tv", params=params)
        return data.get("results", [])

    def _merge_and_sort_results(
        self, 
        results: List, 
        limit: int = 20,
        default_media_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        合并多个搜索结果并按热度排序。
        """
        combined = []
        seen_ids = set()
        for r in results:
            if isinstance(r, list):
                for item in r:
                    item_id = item.get("id")
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        if not item.get("media_type"):
                            if default_media_type:
                                item["media_type"] = default_media_type
                            else:
                                item["media_type"] = "movie" if "title" in item else "tv"
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:limit]

    async def china_trending(self) -> List[Dict[str, Any]]:
        results = await asyncio.gather(
            self.discover_movies(with_original_language="zh", sort_by="popularity.desc"),
            self.discover_tv(with_original_language="zh", sort_by="popularity.desc"),
            return_exceptions=True,
        )
        return self._merge_and_sort_results(results)

    async def anime_popular(self) -> List[Dict[str, Any]]:
        results = await asyncio.gather(
            self.discover_tv(
                with_genres="16",
                with_original_language="ja",
                sort_by="popularity.desc",
            ),
            self.discover_movies(
                with_genres="16",
                with_original_language="ja",
                sort_by="popularity.desc",
            ),
            self.discover_tv(
                with_genres="16",
                with_original_language="zh",
                sort_by="popularity.desc",
            ),
            self.discover_movies(
                with_genres="16",
                with_original_language="zh",
                sort_by="popularity.desc",
            ),
            return_exceptions=True,
        )
        return self._merge_and_sort_results(results)

    async def anime_latest(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        two_months_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        
        results = await asyncio.gather(
            self.discover_tv(
                with_genres="16",
                with_original_language="ja",
                sort_by="popularity.desc",
                extra_params={"first_air_date.gte": two_months_ago, "first_air_date.lte": today},
            ),
            self.discover_tv(
                with_genres="16",
                with_original_language="zh",
                sort_by="popularity.desc",
                extra_params={"first_air_date.gte": two_months_ago, "first_air_date.lte": today},
            ),
            return_exceptions=True,
        )
        return self._merge_and_sort_results(results, default_media_type="tv")

    async def tv_latest(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        two_months_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        
        results = await asyncio.gather(
            self.discover_tv(
                with_original_language="zh",
                sort_by="popularity.desc",
                extra_params={"first_air_date.gte": two_months_ago, "first_air_date.lte": today},
            ),
            self.discover_tv(
                with_original_language="ja",
                sort_by="popularity.desc",
                extra_params={"first_air_date.gte": two_months_ago, "first_air_date.lte": today},
            ),
            self.discover_tv(
                with_original_language="ko",
                sort_by="popularity.desc",
                extra_params={"first_air_date.gte": two_months_ago, "first_air_date.lte": today},
            ),
            return_exceptions=True,
        )
        return self._merge_and_sort_results(results, default_media_type="tv")

    async def tv_popular(self) -> List[Dict[str, Any]]:
        results = await asyncio.gather(
            self.discover_tv(
                with_original_language="zh",
                sort_by="popularity.desc",
            ),
            return_exceptions=True,
        )
        return self._merge_and_sort_results(results, default_media_type="tv")

    async def search_multi(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            return []
        data = await self._get("/search/multi", params={"query": query, "include_adult": "false"})
        return data.get("results", [])

    async def search_movies(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        if not query:
            return []
        params = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        data = await self._get("/search/movie", params=params)
        return data.get("results", [])

    async def search_tv(self, query: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
        if not query:
            return []
        params = {"query": query, "include_adult": "false"}
        if year:
            params["first_air_date_year"] = year
        data = await self._get("/search/tv", params=params)
        return data.get("results", [])

    async def alternative_titles(self, media_type: str, item_id: int) -> List[Dict[str, Any]]:
        """
        获取电影/剧集别名列表。
        """
        path = f"/{media_type}/{item_id}/alternative_titles"
        data = await self._get(path, params={})

        if media_type == "movie":
            return data.get("titles", [])
        return data.get("results", [])

    async def details(
        self, media_type: str, item_id: int, language_override: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "append_to_response": "videos,images,credits,recommendations,similar",
            "include_image_language": "zh,null,en",
            "include_video_language": "zh,en,null",
        }
        if language_override:
            params["language"] = language_override
        return await self._get(f"/{media_type}/{item_id}", params=params)

    async def get_images(
        self,
        media_type: str,
        item_id: int,
        include_image_language: str = "zh,cn,null,en",
    ) -> Dict[str, Any]:
        """
        获取影片剧照，优先中国地区，美国兜底。
        
        Args:
            media_type: movie 或 tv
            item_id: TMDB ID
            include_image_language: 语言优先级，默认 zh,cn,null,en
        
        Returns:
            {"backdrops": [...], "posters": [...], "stills": [...]}
        """
        params = {"include_image_language": include_image_language}
        return await self._get(f"/{media_type}/{item_id}/images", params=params)

    async def get_best_backdrop(
        self,
        media_type: str,
        item_id: int,
        min_width: int = 1280,
    ) -> Optional[str]:
        """
        获取最佳剧照（优先中国地区）。
        
        Returns:
            剧照完整 URL 或 None
        """
        try:
            data = await self.get_images(media_type, item_id, include_image_language="zh,cn,null,en")
            backdrops = data.get("backdrops", [])
            
            if not backdrops:
                # 尝试美国地区兜底
                data = await self.get_images(media_type, item_id, include_image_language="en,null")
                backdrops = data.get("backdrops", [])
            
            if not backdrops:
                return None
            
            # 过滤符合最小宽度的剧照，按投票数排序
            valid_backdrops = [
                b for b in backdrops
                if b.get("width", 0) >= min_width and b.get("file_path")
            ]
            
            if not valid_backdrops:
                # 如果没有符合宽度的，取第一个
                if backdrops and backdrops[0].get("file_path"):
                    return self.image_url(backdrops[0]["file_path"], "w1280")
                return None
            
            # 按投票数排序
            valid_backdrops.sort(key=lambda x: x.get("vote_count", 0), reverse=True)
            return self.image_url(valid_backdrops[0]["file_path"], "w1280")
            
        except Exception as e:
            logger.warning(f"获取剧照失败: {media_type}/{item_id}: {e}")
            return None

    async def person(
        self, person_id: int, language_override: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "append_to_response": "combined_credits,images,external_ids",
            "include_image_language": "zh,null,en",
        }
        if language_override:
            params["language"] = language_override
        return await self._get(f"/person/{person_id}", params=params)

    def image_url(self, path: Optional[str], size: str = DEFAULT_POSTER_SIZE) -> Optional[str]:
        if not path:
            return None
        return f"{self.image_base}{size}{path}"
    
    def get_stats(self) -> Dict[str, int]:
        """获取客户端统计信息"""
        return {
            "request_count": self._request_count,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": round(self._cache_hits / max(self._request_count, 1) * 100, 1)
        }


def tone_from_genres(genre_ids: Optional[List[int]]) -> str:
    if not genre_ids:
        return "neutral"
    for gid in genre_ids:
        if gid in GENRE_TONE:
            return GENRE_TONE[gid]
    return "neutral"


def adapt_poster(item: Dict[str, Any], client: TmdbClient) -> Dict[str, Any]:
    media_type = item.get("media_type") or ("movie" if "title" in item else "tv")
    title = item.get("title") or item.get("name") or "未命名"
    date_field = item.get("release_date") or item.get("first_air_date") or ""
    year = date_field.split("-")[0] if date_field else ""
    vote = item.get("vote_average")
    subtitle = ""
    if year and vote:
        subtitle = f"{year} · 评分 {vote:.1f}"
    elif year:
        subtitle = year
    elif vote:
        subtitle = f"评分 {vote:.1f}"

    poster_path = item.get("poster_path") or item.get("backdrop_path")
    backdrop_path = item.get("backdrop_path") or item.get("poster_path")

    return {
        "id": item.get("id"),
        "media_type": media_type,
        "title": title,
        "subtitle": subtitle,
        "overview": item.get("overview") or "",
        "genres": item.get("genre_ids") or [],
        "tone": tone_from_genres(item.get("genre_ids")),
        "poster_url": client.image_url(poster_path, DEFAULT_POSTER_SIZE),
        "backdrop_url": client.image_url(backdrop_path, DEFAULT_BACKDROP_SIZE),
    }


def is_tmdb_auth_error(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403)


async def gather_sections(client: TmdbClient) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取首页各分区数据，支持缓存
    
    优化:
    - 使用并发请求
    - 缓存结果
    - 错误隔离
    """
    cache = get_cache()
    cache_key = HOME_SECTIONS_CACHE_KEY
    
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        logger.debug("返回缓存的首页分区数据")
        return cached_data

    lock = _get_home_sections_cache_lock()
    async with lock:
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            logger.debug("返回缓存的首页分区数据（锁内命中）")
            return cached_data

        start_time = time.time()

        # 并发获取所有分区数据
        results = await asyncio.gather(
            client.anime_latest(),
            client.tv_latest(),
            client.movies("top_rated"),
            client.tv_popular(),
            client.anime_popular(),
            return_exceptions=True
        )

        keys = ["anime_latest", "tv_latest", "top_rated", "tv_popular", "anime_popular"]
        data: Dict[str, List[Dict[str, Any]]] = {}

        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                if is_tmdb_auth_error(result):
                    raise result
                error_msg = f"Failed to fetch section {key}: {type(result).__name__}: {str(result) or 'Unknown error'}"
                logger.error(error_msg)
                data[key] = []
            else:
                data[key] = result

        await cache.set(cache_key, data, ttl=HOME_SECTIONS_CACHE_TTL)

        elapsed = time.time() - start_time
        logger.info(f"首页分区数据获取完成，耗时 {elapsed:.2f}s，已缓存 {HOME_SECTIONS_CACHE_TTL}s")

        return data


def adapt_detail(item: Dict, client: TmdbClient) -> Dict:
    title = item.get("title") or item.get("name") or "未命名"
    date_field = item.get("release_date") or item.get("first_air_date") or ""
    year = date_field.split("-")[0] if date_field else ""
    genres = [g.get("name") for g in item.get("genres", []) if g.get("name")]
    runtime = item.get("runtime") or (item.get("episode_run_time") or [None])[0]
    vote = item.get("vote_average")

    # 优化：使用列表推导式减少循环
    cast_raw = (item.get("credits") or {}).get("cast") or []
    cast = [
        {
            "id": c.get("id"),
            "name": c.get("name") or "",
            "character": c.get("character") or "",
            "profile_url": client.image_url(c.get("profile_path"), "w300"),
        }
        for c in cast_raw[:12]
    ]

    # 优化：过滤和限制视频数量
    videos_raw = (item.get("videos") or {}).get("results") or []
    videos = [
        {
            "key": v.get("key"),
            "name": v.get("name") or "",
            "type": v.get("type") or "",
            "official": v.get("official") or False,
        }
        for v in videos_raw
        if v.get("site") == "YouTube" and v.get("key")
    ][:2]

    recommendations = (item.get("recommendations") or {}).get("results") or []
    if not recommendations:
        recommendations = (item.get("similar") or {}).get("results") or []

    return {
        "id": item.get("id"),
        "media_type": item.get("media_type") or ("movie" if "title" in item else "tv"),
        "title": title,
        "year": year,
        "genres": genres,
        "runtime": runtime,
        "vote": vote,
        "tagline": item.get("tagline") or "",
        "overview": item.get("overview") or "",
        "poster_url": client.image_url(item.get("poster_path")),
        "backdrop_url": client.image_url(item.get("backdrop_path")),
        "cast": cast,
        "videos": videos,
        "recommendations": recommendations,
    }


def adapt_person(person: Dict, client: TmdbClient, credits: List[Dict]) -> Dict:
    profile_url = client.image_url(person.get("profile_path"), "w500")

    def credit_score(c: Dict) -> tuple:
        va = c.get("vote_average") or 0
        pop = c.get("popularity") or 0
        date = c.get("release_date") or c.get("first_air_date") or ""
        return (va, pop, date)

    # 优化：单次遍历完成过滤
    filtered = []
    for c in credits:
        mt = c.get("media_type") or ("movie" if "title" in c else "tv")
        if mt in ("movie", "tv") and c.get("id"):
            filtered.append(c)

    top_sorted = sorted(filtered, key=credit_score, reverse=True)[:12]
    top_credits = []
    for c in top_sorted:
        adapted = adapt_poster(c, client)
        year = (c.get("release_date") or c.get("first_air_date") or "").split("-")[0] if (
            c.get("release_date") or c.get("first_air_date")
        ) else ""
        role = c.get("character") or c.get("job") or ""
        subtitle_parts = [p for p in [year, role] if p]
        if subtitle_parts:
            adapted["subtitle"] = " · ".join(subtitle_parts)
        top_credits.append(adapted)

    # 优化：列表推导式
    all_credits = [
        {
            "id": c.get("id"),
            "media_type": c.get("media_type") or ("movie" if "title" in c else "tv"),
            "title": c.get("title") or c.get("name") or "未命名",
            "year": (c.get("release_date") or c.get("first_air_date") or "").split("-")[0] if (
                c.get("release_date") or c.get("first_air_date")
            ) else "",
            "role": c.get("character") or c.get("job") or "",
        }
        for c in filtered
    ]
    all_credits.sort(key=lambda x: x.get("year") or "", reverse=True)

    return {
        "id": person.get("id"),
        "name": person.get("name") or "",
        "known_for": person.get("known_for_department") or "",
        "biography": person.get("biography") or "",
        "birthday": person.get("birthday") or "",
        "place_of_birth": person.get("place_of_birth") or "",
        "profile_url": profile_url,
        "top_credits": top_credits,
        "all_credits": all_credits,
    }
