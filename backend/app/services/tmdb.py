from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import logging
import time

import httpx

from ..core.config import get_settings
from ..quark.core.cache import get_cache

DEFAULT_POSTER_SIZE = "w500"
DEFAULT_BACKDROP_SIZE = "w780"
DEFAULT_LANG = "zh-CN"
HOME_SECTIONS_CACHE_TTL = 300

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

class TmdbClient:
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
        
        # 优先使用传入的代理，其次检查 settings（如果有），最后是环境变量
        import os
        
        system_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        # Also check settings
        settings_proxy = settings.http_proxy
        final_proxy = proxy or settings_proxy or system_proxy
        
        if final_proxy:
            logger.info(f"TmdbClient utilizing proxy: {final_proxy}")
        else:
            logger.info("TmdbClient initialized without explicit proxy (will use env if set)")
            
        self._client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={"Accept": "application/json"},
            timeout=timeout,
            proxy=final_proxy,
            trust_env=True
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        params.setdefault("api_key", self.api_key)
        params.setdefault("language", self.language)
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

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

    async def china_trending(self) -> List[Dict[str, Any]]:
        results = await asyncio.gather(
            self.discover_movies(with_original_language="zh", sort_by="popularity.desc"),
            self.discover_tv(with_original_language="zh", sort_by="popularity.desc"),
            return_exceptions=True,
        )
        combined = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if item.get("id") and item.get("id") not in [c.get("id") for c in combined]:
                        item["media_type"] = item.get("media_type") or ("movie" if "title" in item else "tv")
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:20]

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
        combined = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if item.get("id") and item.get("id") not in [c.get("id") for c in combined]:
                        item["media_type"] = item.get("media_type") or ("movie" if "title" in item else "tv")
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:20]

    async def anime_latest(self) -> List[Dict[str, Any]]:
        from datetime import datetime, timedelta
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
        combined = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if item.get("id") and item.get("id") not in [c.get("id") for c in combined]:
                        item["media_type"] = item.get("media_type") or "tv"
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:20]

    async def tv_latest(self) -> List[Dict[str, Any]]:
        from datetime import datetime, timedelta
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
        combined = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if item.get("id") and item.get("id") not in [c.get("id") for c in combined]:
                        item["media_type"] = item.get("media_type") or "tv"
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:20]

    async def tv_popular(self) -> List[Dict[str, Any]]:
        results = await asyncio.gather(
            self.discover_tv(
                with_original_language="zh",
                sort_by="popularity.desc",
            ),
            return_exceptions=True,
        )
        combined = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    if item.get("id") and item.get("id") not in [c.get("id") for c in combined]:
                        item["media_type"] = item.get("media_type") or "tv"
                        combined.append(item)
        combined.sort(key=lambda x: x.get("popularity", 0) or 0, reverse=True)
        return combined[:20]

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
        - movie: /movie/{id}/alternative_titles
        - tv: /tv/{id}/alternative_titles
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


async def gather_sections(client: TmdbClient) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取首页各分区数据，支持缓存
    
    分区配置（针对国内用户优化）：
    1. anime_latest - 动漫 · 新番（日漫+中国漫画）
    2. tv_latest - TV · 新作（华语+日韩新剧）
    3. top_rated - 高分佳作
    4. tv_popular - TV · 热播（国产剧集）
    5. anime_popular - 动漫 · 热播（日漫+中国漫画）
    
    缓存策略：
    - 缓存时间：300秒（5分钟）
    - 缓存键：home_sections
    - 失败时返回空列表，不影响其他分区
    """
    cache = get_cache()
    cache_key = "tmdb:home_sections"
    
    cached_data = await cache.get(cache_key)
    if cached_data:
        logger.debug("返回缓存的首页分区数据")
        return cached_data
    
    start_time = time.time()
    
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
            logger.error(f"Failed to fetch section {key}: {result}")
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

    cast_raw = (item.get("credits") or {}).get("cast") or []
    cast = []
    for c in cast_raw[:12]:
        cast.append(
            {
                "id": c.get("id"),
                "name": c.get("name") or "",
                "character": c.get("character") or "",
                "profile_url": client.image_url(c.get("profile_path"), "w300"),
            }
        )

    videos_raw = (item.get("videos") or {}).get("results") or []
    videos = []
    for v in videos_raw:
        if v.get("site") != "YouTube" or not v.get("key"):
            continue
        videos.append(
            {
                "key": v.get("key"),
                "name": v.get("name") or "",
                "type": v.get("type") or "",
                "official": v.get("official") or False,
            }
        )
    videos = videos[:2]

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

    filtered = []
    for c in credits:
        mt = c.get("media_type") or ("movie" if "title" in c else "tv")
        if mt not in ("movie", "tv") or not c.get("id"):
            continue
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

    all_credits = []
    for c in filtered:
        mt = c.get("media_type") or ("movie" if "title" in c else "tv")
        title = c.get("title") or c.get("name") or "未命名"
        date_field = c.get("release_date") or c.get("first_air_date") or ""
        year = date_field.split("-")[0] if date_field else ""
        role = c.get("character") or c.get("job") or ""
        all_credits.append(
            {
                "id": c.get("id"),
                "media_type": mt,
                "title": title,
                "year": year,
                "role": role,
            }
        )
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
