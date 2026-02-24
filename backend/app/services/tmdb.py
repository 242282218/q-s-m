from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import logging

import httpx

from ..core.config import get_settings

DEFAULT_POSTER_SIZE = "w500"
DEFAULT_BACKDROP_SIZE = "w780"
DEFAULT_LANG = "zh-CN"

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
    # Use return_exceptions=True to avoid one failure breaking everything
    results = await asyncio.gather(
        client.trending("all", "week"),
        client.movies("popular"),
        client.movies("top_rated"),
        client.movies("now_playing"),
        return_exceptions=True
    )
    
    keys = ["trending", "popular", "top_rated", "now_playing"]
    data = {}
    
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to fetch section {key}: {result}")
            data[key] = []
        else:
            data[key] = result
            
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
