from __future__ import annotations

import asyncio
import logging
import random
import time
from asyncio import AbstractEventLoop
import os
from typing import Any
from weakref import WeakKeyDictionary

import httpx
from fastapi import APIRouter, Request

from ...core.config import get_settings
from ...core.error_codes import ErrorCode, ErrorContext
from ...core.exceptions import QSMException
from ...services.tmdb import (
    TmdbClient,
    adapt_detail,
    adapt_poster,
    gather_sections,
    is_tmdb_auth_error,
)
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
LOCAL_TMDB_PLACEHOLDER_KEYS = {
    "",
    "replace-with-your-tmdb-api-key",
    "your-tmdb-api-key",
    "your_tmdb_api_key",
}
_demo_image_base = "https://image.tmdb.org/t/p/"
DEMO_HOME_POSTERS: list[dict[str, Any]] = [
    {
        "id": 370172,
        "media_type": "movie",
        "title": "007：无暇赴死",
        "subtitle": "2021 · 评分 7.3 · No Time to Die",
        "overview": "詹姆斯·邦德离开现役后在牙买加过着平静生活，却因老友求助重新卷入危机。他必须追踪一名掌握危险科技的神秘反派，面对过去与未来的最终抉择。",
        "genres": [28, 12, 53],
        "tone": "action",
        "poster_url": f"{_demo_image_base}w780/iUgygt3fscRoKWCV1d0C7FbM9TP.jpg",
        "backdrop_url": f"{_demo_image_base}original/r2GAjd4rNOHJh6i6Y0FntmYuPQW.jpg",
    },
    {
        "id": 37724,
        "media_type": "movie",
        "title": "007：大破天幕杀机",
        "subtitle": "2012 · 评分 7.2 · Skyfall",
        "overview": "军情六处遭到攻击，邦德被迫追查一名与 M 过去有关的敌人。随着组织根基受到威胁，他必须在忠诚、牺牲与复仇之间完成最艰难的任务。",
        "genres": [28, 12, 53],
        "tone": "action",
        "poster_url": f"{_demo_image_base}w780/d0IVecFQvsGdSbnMAHqiYsNYaJT.jpg",
        "backdrop_url": f"{_demo_image_base}original/h3KN24PrOheHVYs9ypuOIdFBEpX.jpg",
    },
    {
        "id": 157336,
        "media_type": "movie",
        "title": "星际穿越",
        "subtitle": "2014 · 评分 8.7",
        "overview": "地球农作物因气候转变逐渐枯萎，人类面临生存危机。一名前 NASA 飞行员加入穿越虫洞的任务，前往遥远星系寻找适合人类延续的新家园。",
        "genres": [878, 18],
        "tone": "scifi",
        "poster_url": f"{_demo_image_base}w780/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",
        "backdrop_url": f"{_demo_image_base}original/rAiYTfKGqDCRIIqo664sY9XZIvQ.jpg",
    },
    {
        "id": 129,
        "media_type": "movie",
        "title": "千与千寻",
        "subtitle": "2001 · 评分 8.5",
        "overview": "少女千寻误入神灵世界，父母被变成猪。为了救回家人并回到现实，她在汤婆婆经营的浴场工作，逐渐学会勇气、责任与告别。",
        "genres": [16, 14],
        "tone": "family",
        "poster_url": f"{_demo_image_base}w780/39wmItIWsg5sZMyRUHLkWBcuVCM.jpg",
        "backdrop_url": f"{_demo_image_base}original/mSDsSDwaP3E7dEfUPWy4J0djt4O.jpg",
    },
    {
        "id": 27205,
        "media_type": "movie",
        "title": "盗梦空间",
        "subtitle": "2010 · 评分 8.4",
        "overview": "一名能够潜入他人梦境窃取秘密的盗梦者接下最后一次任务：不是偷取想法，而是植入想法。他必须带领团队深入多层梦境完成不可能的行动。",
        "genres": [878, 9648],
        "tone": "mystery",
        "poster_url": f"{_demo_image_base}w780/9gk7adHYeDvHkCSEqAvQNLV5Uge.jpg",
        "backdrop_url": f"{_demo_image_base}original/s3TBrRGB1iav7gFOCNx3H31MoES.jpg",
    },
    {
        "id": 603,
        "media_type": "movie",
        "title": "黑客帝国",
        "subtitle": "1999 · 评分 8.2",
        "overview": "程序员尼奥发现自己生活的世界只是机器制造的虚拟现实。被墨菲斯唤醒后，他必须面对真实世界的残酷真相，并寻找人类反抗机器统治的希望。",
        "genres": [878, 28],
        "tone": "scifi",
        "poster_url": f"{_demo_image_base}w780/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg",
        "backdrop_url": f"{_demo_image_base}original/fNG7i7RqMErkcqhohV2a6cV1Ehy.jpg",
    },
    {
        "id": 155,
        "media_type": "movie",
        "title": "蝙蝠侠：黑暗骑士",
        "subtitle": "2008 · 评分 8.5",
        "overview": "哥谭市的犯罪秩序被小丑彻底搅乱。蝙蝠侠、戈登与哈维·丹特试图守住城市的底线，却被迫面对混乱、牺牲与正义代价的终极考验。",
        "genres": [28, 80],
        "tone": "mystery",
        "poster_url": f"{_demo_image_base}w780/qJ2tW6WMUDux911r6m7haRef0WH.jpg",
        "backdrop_url": f"{_demo_image_base}original/hkBaDkMWbLaf8B1lsWsKX7Ew3Xq.jpg",
    },
]
_hero_cache: dict[str, Any] = {"data": None, "timestamp": 0}
_hero_cache_locks: WeakKeyDictionary[AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()


def _is_hero_cache_fresh(now: float) -> bool:
    cache_data = _hero_cache.get("data")
    cache_timestamp = _hero_cache.get("timestamp", 0)
    return bool(cache_data) and (now - cache_timestamp) < HERO_CACHE_TTL


def _get_hero_cache_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _hero_cache_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _hero_cache_locks[loop] = lock
    return lock


def _is_development_home_fallback_enabled() -> bool:
    settings = get_settings()
    env = os.getenv("ENV", "").strip().lower()
    tmdb_key = (settings.tmdb_api_key or "").strip().lower()
    return settings.debug or env in {"dev", "development", "local"} or tmdb_key in LOCAL_TMDB_PLACEHOLDER_KEYS


def _build_demo_home_data() -> HomeData:
    posters = [to_poster_item(item) for item in DEMO_HOME_POSTERS]
    sections = {
        meta.key: [posters[(index + offset) % len(posters)] for offset in range(len(posters))]
        for index, meta in enumerate(SECTION_META)
    }
    hero_items = [
        HomeHeroItem(
            id=poster.id,
            media_type=poster.media_type,
            title=poster.title,
            year=parse_year(poster.subtitle[:4]),
            genres=[],
            runtime=None,
            vote=None,
            tagline="",
            overview=poster.overview,
            poster_url=poster.poster_url,
            backdrop_url=poster.backdrop_url,
        )
        for poster in posters[:3]
    ]
    return HomeData(
        hero_items=hero_items,
        sections=sections,
        section_order=SECTION_META,
        generated_at=utc_now_iso(),
    )


def _tmdb_config_exception(message: str, reason: str, status_code: int | None = None) -> QSMException:
    details: dict[str, Any] = {}
    if status_code is not None:
        details["status_code"] = status_code
    return QSMException(
        message,
        code=ErrorCode.CONFIG_ERROR,
        context=ErrorContext(field="TMDB_API_KEY", reason=reason),
        details=details,
    )


def _raise_or_fallback_home_data(exc: BaseException | None = None) -> ApiResponse[HomeData]:
    if _is_development_home_fallback_enabled():
        return ok(
            _build_demo_home_data(),
            message="TMDB 未可用，开发环境返回演示首页数据",
        )

    if exc is None:
        raise _tmdb_config_exception(
            "未配置 TMDB_API_KEY，无法加载首页数据",
            "missing runtime configuration",
        )

    status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    raise _tmdb_config_exception(
        "TMDB_API_KEY 无效或未授权，无法加载首页数据",
        "TMDB authentication failed",
        status_code=status_code,
    )


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
        return _raise_or_fallback_home_data()

    try:
        sections_raw = await gather_sections(tmdb_client)
    except Exception as e:
        if is_tmdb_auth_error(e):
            return _raise_or_fallback_home_data(e)
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

    if _is_development_home_fallback_enabled() and not any(sections.values()):
        logger.warning("TMDB returned no homepage sections; using development demo data")
        return ok(
            _build_demo_home_data(),
            message="TMDB 未返回首页数据，开发环境返回演示首页数据",
        )

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
    获取 Hero 数据。
    当缓存失效时，通过互斥锁避免并发请求同时触发 TMDB 明细拉取。
    """
    now = time.time()

    if _is_hero_cache_fresh(now):
        return _hero_cache["data"]

    lock = _get_hero_cache_lock()
    async with lock:
        now = time.time()
        if _is_hero_cache_fresh(now):
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

