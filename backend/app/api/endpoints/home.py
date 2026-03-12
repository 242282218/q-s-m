from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from fastapi import APIRouter, Request

from ...services.tmdb import TmdbClient, adapt_detail, adapt_poster, gather_sections
from ..schemas.common import ApiResponse, ok, utc_now_iso
from ..schemas.home import HomeData, HomeHeroItem, HomePosterItem, HomeSectionMeta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/home", tags=["home"])

SECTION_META: list[HomeSectionMeta] = [
    HomeSectionMeta(key="anime_latest", title="动漫新番", tag="新"),
    HomeSectionMeta(key="tv_latest", title="TV新作", tag="新"),
    HomeSectionMeta(key="top_rated", title="高分佳作", tag=None),
    HomeSectionMeta(key="tv_popular", title="热播剧集", tag="热"),
    HomeSectionMeta(key="anime_popular", title="热播动漫", tag="热"),
]

HERO_CACHE_TTL = 300
_hero_cache: dict[str, Any] = {"data": None, "timestamp": 0}


def get_tmdb_client(request: Request) -> TmdbClient | None:
    return getattr(request.app.state, "tmdb_client", None)


def parse_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def to_poster_item(raw: dict[str, Any]) -> HomePosterItem:
    return HomePosterItem(
        id=int(raw["id"]),
        media_type=str(raw.get("media_type", "movie")),
        title=str(raw.get("title") or ""),
        subtitle=str(raw.get("subtitle") or ""),
        overview=str(raw.get("overview") or ""),
        genres=[int(g) for g in (raw.get("genres") or []) if isinstance(g, int)],
        tone=str(raw.get("tone") or "neutral"),
        poster_url=raw.get("poster_url"),
        backdrop_url=raw.get("backdrop_url"),
    )


def to_hero_item(raw: dict[str, Any]) -> HomeHeroItem:
    return HomeHeroItem(
        id=int(raw["id"]),
        media_type=str(raw.get("media_type", "movie")),
        title=str(raw.get("title") or ""),
        year=parse_year(raw.get("year")),
        genres=[str(g) for g in (raw.get("genres") or []) if isinstance(g, str)],
        runtime=int(raw["runtime"]) if isinstance(raw.get("runtime"), int) else None,
        vote=float(raw["vote"]) if isinstance(raw.get("vote"), (int, float)) else None,
        tagline=str(raw.get("tagline") or ""),
        overview=str(raw.get("overview") or ""),
        poster_url=raw.get("poster_url"),
        backdrop_url=raw.get("backdrop_url"),
    )


@router.get("", summary="获取首页数据", response_model=ApiResponse[HomeData])
async def get_home_feed(request: Request) -> ApiResponse[HomeData]:
    tmdb_client = get_tmdb_client(request)
    section_keys = [meta.key for meta in SECTION_META]

    if tmdb_client is None:
        return ok(
            HomeData(
                hero_items=[],
                sections={key: [] for key in section_keys},
                section_order=SECTION_META,
                generated_at=utc_now_iso(),
            ),
            message="未配置 TMDB_API_KEY，首页返回空数据",
        )

    try:
        sections_raw = await gather_sections(tmdb_client)
    except Exception as e:
        error_msg = f"Failed to fetch home sections: {type(e).__name__}: {str(e) or 'Unknown error'}"
        logger.error(error_msg, exc_info=True)
        sections_raw = {key: [] for key in section_keys}

    sections: dict[str, list[HomePosterItem]] = {}
    for key in section_keys:
        section_items = sections_raw.get(key) or []
        posters: list[HomePosterItem] = []
        for item in section_items:
            if not item.get("id"):
                continue
            adapted = adapt_poster(item, tmdb_client)
            posters.append(to_poster_item(adapted))
        sections[key] = posters

    hero_items = await _get_hero_items(tmdb_client, sections)

    return ok(
        HomeData(
            hero_items=hero_items,
            sections=sections,
            section_order=SECTION_META,
            generated_at=utc_now_iso(),
        )
    )


async def _get_hero_items(
    tmdb_client: TmdbClient, 
    sections: dict[str, list[HomePosterItem]]
) -> list[HomeHeroItem]:
    """
    获取 Hero 数据，带缓存和并发优化
    """
    import time
    now = time.time()
    
    if _hero_cache["data"] and (now - _hero_cache["timestamp"]) < HERO_CACHE_TTL:
        return _hero_cache["data"]
    
    hero_candidates: list[HomePosterItem] = []
    hero_candidates.extend(sections.get("tv_popular", [])[:3])
    hero_candidates.extend(sections.get("tv_latest", [])[:2])
    hero_candidates.extend(sections.get("top_rated", [])[:2])
    hero_candidates.extend(sections.get("anime_popular", [])[:2])

    if not hero_candidates:
        return []
    
    selected = random.sample(hero_candidates, min(5, len(hero_candidates)))
    
    async def fetch_hero_detail(candidate: HomePosterItem) -> HomeHeroItem:
        try:
            detail_data = await tmdb_client.details(candidate.media_type, candidate.id)
            adapted = adapt_detail(detail_data, tmdb_client)
            
            backdrop_url = await tmdb_client.get_best_backdrop(
                candidate.media_type, candidate.id
            )
            if not backdrop_url:
                backdrop_url = adapted.get("backdrop_url")
            
            return HomeHeroItem(
                id=candidate.id,
                media_type=candidate.media_type,
                title=adapted.get("title", candidate.title),
                year=parse_year(adapted.get("year", "")),
                genres=[str(g) for g in adapted.get("genres", [])],
                runtime=adapted.get("runtime"),
                vote=adapted.get("vote"),
                tagline=adapted.get("tagline", ""),
                overview=adapted.get("overview", candidate.overview),
                poster_url=adapted.get("poster_url") or candidate.poster_url,
                backdrop_url=backdrop_url,
            )
        except Exception as e:
            error_msg = f"Failed to fetch hero detail for {candidate.media_type}/{candidate.id}: {type(e).__name__}: {str(e) or 'Unknown error'}"
            logger.warning(error_msg)
            return HomeHeroItem(
                id=candidate.id,
                media_type=candidate.media_type,
                title=candidate.title,
                year=parse_year(candidate.subtitle[:4]) if candidate.subtitle else None,
                genres=[],
                runtime=None,
                vote=None,
                tagline="",
                overview=candidate.overview,
                poster_url=candidate.poster_url,
                backdrop_url=candidate.backdrop_url,
            )
    
    hero_items = await asyncio.gather(*[fetch_hero_detail(c) for c in selected])
    
    _hero_cache["data"] = hero_items
    _hero_cache["timestamp"] = now
    
    return hero_items

