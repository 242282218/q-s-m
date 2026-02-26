from __future__ import annotations

import random
from typing import Any

from fastapi import APIRouter, Request

from ...services.tmdb import TmdbClient, adapt_detail, adapt_poster, gather_sections
from ..schemas.common import ApiResponse, ok, utc_now_iso
from ..schemas.home import HomeData, HomeHeroItem, HomePosterItem, HomeSectionMeta

router = APIRouter(prefix="/home", tags=["home"])

SECTION_META: list[HomeSectionMeta] = [
    HomeSectionMeta(key="anime_latest", title="动漫新番", tag="新"),
    HomeSectionMeta(key="tv_latest", title="TV新作", tag="新"),
    HomeSectionMeta(key="top_rated", title="高分佳作", tag=None),
    HomeSectionMeta(key="tv_popular", title="热播剧集", tag="热"),
    HomeSectionMeta(key="anime_popular", title="热播动漫", tag="热"),
]


def get_tmdb_client(request: Request) -> TmdbClient:
    return request.app.state.tmdb_client


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

    try:
        sections_raw = await gather_sections(tmdb_client)
    except Exception:
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

    hero_candidates: list[HomePosterItem] = []
    hero_candidates.extend(sections.get("tv_popular", [])[:3])
    hero_candidates.extend(sections.get("tv_latest", [])[:2])
    hero_candidates.extend(sections.get("top_rated", [])[:2])
    hero_candidates.extend(sections.get("anime_popular", [])[:2])

    hero_items: list[HomeHeroItem] = []
    if hero_candidates:
        selected = random.sample(hero_candidates, min(5, len(hero_candidates)))
        for candidate in selected:
            try:
                detail_data = await tmdb_client.details(candidate.media_type, candidate.id)
                hero_items.append(to_hero_item(adapt_detail(detail_data, tmdb_client)))
            except Exception:
                hero_items.append(
                    HomeHeroItem(
                        id=candidate.id,
                        media_type=candidate.media_type,
                        title=candidate.title,
                        year=parse_year(candidate.subtitle[:4]),
                        genres=[],
                        runtime=None,
                        vote=None,
                        tagline="",
                        overview=candidate.overview,
                        poster_url=candidate.poster_url,
                        backdrop_url=candidate.backdrop_url,
                    )
                )

    return ok(
        HomeData(
            hero_items=hero_items,
            sections=sections,
            section_order=SECTION_META,
            generated_at=utc_now_iso(),
        )
    )

