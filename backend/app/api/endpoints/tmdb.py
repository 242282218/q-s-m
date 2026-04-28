from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from ...core.error_codes import ErrorCode
from ...services.tmdb import TmdbClient, adapt_detail, adapt_person, adapt_poster, is_tmdb_auth_error
from ..schemas.common import ApiResponse, ok, business_error, ErrorDetail
from ..schemas.system import TmdbDetailsData
from .home import DEMO_HOME_POSTERS, _is_development_home_fallback_enabled
from ..schemas.tmdb import (
    CastMemberData,
    DetailItemData,
    DetailPageData,
    PersonCreditData,
    PersonData,
    PosterCardData,
    SearchPageData,
    VideoData,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_tmdb_client(request: Request) -> TmdbClient | None:
    return getattr(request.app.state, "tmdb_client", None)


def tmdb_not_configured_response(data=None):
    return business_error(
        data,
        message="未配置 TMDB_API_KEY，TMDB 功能不可用",
        code=ErrorCode.CONFIG_ERROR,
        error=ErrorDetail(field="TMDB_API_KEY", reason="missing runtime configuration"),
    )


def parse_year(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def to_poster_card(raw: dict) -> PosterCardData:
    return PosterCardData(
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


def _find_demo_detail(media_type: str, item_id: int) -> dict | None:
    return next(
        (
            item
            for item in DEMO_HOME_POSTERS
            if item.get("media_type") == media_type and item.get("id") == item_id
        ),
        None,
    )


DEMO_DETAIL_EXTRAS: dict[tuple[str, int], dict[str, Any]] = {
    ("movie", 157336): {
        "genres": ["科幻", "剧情", "冒险"],
        "runtime": 169,
        "vote": 8.7,
        "tagline": "人类的未来，藏在群星之间。",
        "cast": [
            {"id": 10297, "name": "Matthew McConaughey", "character": "Cooper", "profile_path": "/lCySuYjhXix3FzQdS4oceDDrXKI.jpg"},
            {"id": 1813, "name": "Anne Hathaway", "character": "Brand", "profile_path": "/tLelKoPNiyJCSEtQTz1FGv4TLGc.jpg"},
            {"id": 3896, "name": "Jessica Chastain", "character": "Murph", "profile_path": "/lodMzLKSdrPcBry6TdoDsMN3Vge.jpg"},
            {"id": 6489, "name": "Michael Caine", "character": "Professor Brand", "profile_path": "/bVZRMlpjTAO2pJK6v90buFgVbSW.jpg"},
        ],
        "videos": [
            {"key": "zSWdZVtXT7E", "name": "Official Trailer", "type": "Trailer", "official": True},
        ],
    },
    ("movie", 129): {
        "genres": ["动画", "奇幻", "家庭"],
        "runtime": 125,
        "vote": 8.5,
        "tagline": "在不可思议的世界里，找回名字与勇气。",
        "cast": [
            {"id": 19587, "name": "柊瑠美", "character": "荻野千寻", "profile_path": "/z5BSB2QkZ6kWXT3dOQJ4X8dL6Z2.jpg"},
            {"id": 19588, "name": "入野自由", "character": "白龙", "profile_path": "/8NgzG4sVAmuVLvn3b9QfJ0qfe8H.jpg"},
            {"id": 19589, "name": "夏木真理", "character": "汤婆婆 / 钱婆婆", "profile_path": "/hZKQkU6oQZQWwlq7QghQYc8vw8T.jpg"},
            {"id": 19590, "name": "菅原文太", "character": "锅炉爷爷", "profile_path": None},
        ],
        "videos": [
            {"key": "ByXuk9QqQkk", "name": "Official Trailer", "type": "Trailer", "official": True},
        ],
    },
    ("movie", 27205): {
        "genres": ["科幻", "动作", "悬疑"],
        "runtime": 148,
        "vote": 8.4,
        "tagline": "你的梦境，可能不是你的。",
        "cast": [
            {"id": 6193, "name": "Leonardo DiCaprio", "character": "Cobb", "profile_path": "/wo2hJpn04vbtmh0B9utCFdsQhxM.jpg"},
            {"id": 24045, "name": "Joseph Gordon-Levitt", "character": "Arthur", "profile_path": "/4U9G4YwTlIEbAymBaseltS38eH4.jpg"},
            {"id": 27578, "name": "Elliot Page", "character": "Ariadne", "profile_path": "/eCeFgzS8dYH3jD3hR5Z4SVU7Wci.jpg"},
            {"id": 2524, "name": "Tom Hardy", "character": "Eames", "profile_path": "/d81K0RH8UX7tZj49tZaQhZ9ewH.jpg"},
        ],
        "videos": [
            {"key": "YoHD9XEInc0", "name": "Official Trailer", "type": "Trailer", "official": True},
        ],
    },
}


def _demo_image_url(path: str | None, size: str) -> str | None:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _demo_cast(extras: dict[str, Any]) -> list[CastMemberData]:
    return [
        CastMemberData(
            id=int(member["id"]),
            name=str(member.get("name") or ""),
            character=str(member.get("character") or ""),
            profile_url=_demo_image_url(member.get("profile_path"), "w300"),
        )
        for member in extras.get("cast", [])
        if member.get("id")
    ]


def _demo_videos(extras: dict[str, Any]) -> list[VideoData]:
    return [
        VideoData(
            key=str(video.get("key") or ""),
            name=str(video.get("name") or ""),
            type=str(video.get("type") or ""),
            official=bool(video.get("official") or False),
        )
        for video in extras.get("videos", [])
        if video.get("key")
    ]


def _build_demo_detail_page_data(media_type: str, item_id: int) -> DetailPageData | None:
    detail = _find_demo_detail(media_type, item_id)
    if detail is None:
        return None

    year_text = str(detail.get("subtitle") or "")[:4]
    extras = DEMO_DETAIL_EXTRAS.get((media_type, item_id), {})
    item = DetailItemData(
        id=int(detail["id"]),
        media_type=str(detail.get("media_type") or media_type),
        title=str(detail.get("title") or ""),
        year=parse_year(year_text),
        genres=[str(genre) for genre in extras.get("genres", [])],
        runtime=extras.get("runtime"),
        vote=extras.get("vote"),
        tagline=str(extras.get("tagline") or ""),
        overview=str(detail.get("overview") or ""),
        poster_url=detail.get("poster_url"),
        backdrop_url=detail.get("backdrop_url"),
        poster_path=None,
        backdrop_path=None,
        cast=_demo_cast(extras),
        videos=_demo_videos(extras),
    )
    recommendations = [
        to_poster_card(raw)
        for raw in DEMO_HOME_POSTERS
        if raw.get("id") != item_id and raw.get("media_type") in ("movie", "tv")
    ][:12]
    return DetailPageData(item=item, recommendations=recommendations)


def _demo_detail_response(media_type: str, item_id: int) -> ApiResponse[DetailPageData] | None:
    if not _is_development_home_fallback_enabled():
        return None

    data = _build_demo_detail_page_data(media_type, item_id)
    if data is None:
        return None

    return ok(data, message="TMDB 未可用，开发环境返回演示详情数据")


@router.get(
    "/search",
    summary="搜索影视海报",
    response_model=ApiResponse[SearchPageData],
)
async def search_media(
    request: Request,
    q: str = "",
):
    query = (q or "").strip()
    if not query:
        return ok(SearchPageData(query="", posters=[]))

    tmdb_client = get_tmdb_client(request)
    if tmdb_client is None:
        return tmdb_not_configured_response(SearchPageData(query=query, posters=[]))
    try:
        results = await tmdb_client.search_multi(query)
    except httpx.HTTPError as exc:
        logger.error("TMDB搜索失败: %s", str(exc))
        return business_error(
            SearchPageData(query=query, posters=[]),
            message="TMDB 服务暂时不可用",
            code=502,
        )

    posters = [
        to_poster_card(adapt_poster(item, tmdb_client))
        for item in results
        if item.get("id") and (item.get("media_type") in ("movie", "tv"))
    ]
    return ok(SearchPageData(query=query, posters=posters))


@router.get("/details", summary="获取TMDB详情", response_model=ApiResponse[TmdbDetailsData])
async def get_tmdb_details(
    request: Request,
    media_type: str,
    tmdb_id: int,
):
    if tmdb_id <= 0:
        return business_error(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
            message="TMDB ID 必须为正整数",
            code=400,
        )

    tmdb_client = get_tmdb_client(request)
    if tmdb_client is None:
        return tmdb_not_configured_response(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None)
        )
    try:
        logger.info("获取TMDB详情: media_type=%s, tmdb_id=%s", media_type, tmdb_id)
        data = await tmdb_client.details(media_type, tmdb_id)
        year_value = None
        raw_date = data.get("release_date") or data.get("first_air_date")
        if isinstance(raw_date, str) and raw_date:
            year_text = raw_date.split("-")[0]
            if year_text.isdigit():
                year_value = int(year_text)
        return ok(
            TmdbDetailsData(
                poster_path=data.get("poster_path"),
                backdrop_path=data.get("backdrop_path"),
                title=data.get("title") or data.get("name"),
                year=year_value,
            )
        )
    except httpx.HTTPStatusError as e:
        logger.error("TMDB API HTTP错误: %s - %s", e.response.status_code, e.response.text)
        if e.response.status_code == 404:
            return business_error(
                TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
                message="TMDB 资源不存在",
                code=404,
            )
        return business_error(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
            message="TMDB 服务暂时不可用",
            code=502,
        )
    except httpx.ConnectError as e:
        logger.error("TMDB API连接错误: %s", str(e))
        return business_error(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
            message="无法连接到TMDB服务",
            code=503,
        )
    except httpx.TimeoutException as e:
        logger.error("TMDB API超时错误: %s", str(e))
        return business_error(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
            message="TMDB服务请求超时",
            code=504,
        )
    except Exception as e:
        logger.error("获取TMDB详情失败: %s", str(e), exc_info=True)
        return business_error(
            TmdbDetailsData(poster_path=None, backdrop_path=None, title=None, year=None),
            message="获取TMDB详情失败",
            code=500,
        )


@router.get(
    "/detail/{media_type}/{item_id}",
    summary="获取详情页数据",
    response_model=ApiResponse[DetailPageData],
)
async def get_detail_page_data(
    request: Request,
    media_type: str,
    item_id: int,
):
    if media_type not in ("movie", "tv"):
        return business_error(
            None,
            message="不支持的媒体类型",
            code=404,
            error=ErrorDetail(field="media_type", value=media_type, reason="必须是 movie 或 tv"),
        )
    if item_id <= 0:
        return business_error(
            None,
            message="item_id 必须为正整数",
            code=400,
            error=ErrorDetail(field="item_id", value=str(item_id), reason="必须大于 0"),
        )

    tmdb_client = get_tmdb_client(request)
    if tmdb_client is None:
        demo_response = _demo_detail_response(media_type, item_id)
        return demo_response or tmdb_not_configured_response(None)
    try:
        data = await tmdb_client.details(media_type, item_id)
        need_fallback = False
        videos_has = (data.get("videos") or {}).get("results")
        rec_has = (data.get("recommendations") or {}).get("results")
        sim_has = (data.get("similar") or {}).get("results")
        if not videos_has or not rec_has:
            need_fallback = True
        if need_fallback:
            try:
                data_en = await tmdb_client.details(media_type, item_id, language_override="en-US")
                if not videos_has:
                    data["videos"] = data_en.get("videos") or {}
                if not rec_has:
                    data["recommendations"] = data_en.get("recommendations") or {}
                if not sim_has:
                    data["similar"] = data_en.get("similar") or {}
            except httpx.HTTPError:
                pass
    except httpx.HTTPStatusError as exc:
        logger.error("TMDB API HTTP错误: %s", str(exc))
        if is_tmdb_auth_error(exc):
            demo_response = _demo_detail_response(media_type, item_id)
            if demo_response is not None:
                return demo_response
        return business_error(
            None,
            message="TMDB 服务错误",
            code=exc.response.status_code,
        )
    except httpx.HTTPError as exc:
        logger.error("TMDB API连接错误: %s", str(exc))
        return business_error(
            None,
            message="TMDB 服务暂时不可用",
            code=502,
        )

    detail_data = adapt_detail(data, tmdb_client)
    recommendation_items = [
        adapt_poster(rec, tmdb_client)
        for rec in detail_data.get("recommendations", [])
        if rec.get("id")
    ][:12]

    item = DetailItemData(
        id=int(detail_data.get("id")),
        media_type=str(detail_data.get("media_type") or media_type),
        title=str(detail_data.get("title") or ""),
        year=parse_year(detail_data.get("year")),
        genres=[str(g) for g in (detail_data.get("genres") or []) if isinstance(g, str)],
        runtime=detail_data.get("runtime"),
        vote=detail_data.get("vote"),
        tagline=str(detail_data.get("tagline") or ""),
        overview=str(detail_data.get("overview") or ""),
        poster_url=detail_data.get("poster_url"),
        backdrop_url=detail_data.get("backdrop_url"),
        poster_path=data.get("poster_path"),
        backdrop_path=data.get("backdrop_path"),
        cast=[
            CastMemberData(
                id=int(c.get("id")),
                name=str(c.get("name") or ""),
                character=str(c.get("character") or ""),
                profile_url=c.get("profile_url"),
            )
            for c in (detail_data.get("cast") or [])
            if c.get("id")
        ],
        videos=[
            VideoData(
                key=str(v.get("key") or ""),
                name=str(v.get("name") or ""),
                type=str(v.get("type") or ""),
                official=bool(v.get("official") or False),
            )
            for v in (detail_data.get("videos") or [])
            if v.get("key")
        ],
    )

    return ok(
        DetailPageData(
            item=item,
            recommendations=[to_poster_card(raw) for raw in recommendation_items],
        )
    )


@router.get(
    "/person/{person_id}",
    summary="获取人物页数据",
    response_model=ApiResponse[PersonData],
)
async def get_person_page_data(
    request: Request,
    person_id: int,
):
    if person_id <= 0:
        raise HTTPException(status_code=400, detail="person_id 必须为正整数")

    tmdb_client = get_tmdb_client(request)
    if tmdb_client is None:
        return tmdb_not_configured_response(None)
    try:
        data = await tmdb_client.person(person_id)
        if not data.get("biography") or not data.get("profile_path"):
            try:
                data_en = await tmdb_client.person(person_id, language_override="en-US")
                data["biography"] = data.get("biography") or data_en.get("biography")
                data["profile_path"] = data.get("profile_path") or data_en.get("profile_path")
                data["combined_credits"] = data.get("combined_credits") or data_en.get("combined_credits")
            except httpx.HTTPError:
                pass
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="TMDB error") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="TMDB unavailable") from exc

    combined = data.get("combined_credits") or {}
    credits_cast = combined.get("cast") or []
    credits_crew = combined.get("crew") or []
    credits = credits_cast + credits_crew
    if not credits and combined:
        credits = credits_cast or credits_crew

    person_data = adapt_person(data, tmdb_client, credits)

    return ok(
        PersonData(
            id=int(person_data.get("id")),
            name=str(person_data.get("name") or ""),
            known_for=str(person_data.get("known_for") or ""),
            biography=str(person_data.get("biography") or ""),
            birthday=str(person_data.get("birthday") or ""),
            place_of_birth=str(person_data.get("place_of_birth") or ""),
            profile_url=person_data.get("profile_url"),
            top_credits=[
                to_poster_card(raw)
                for raw in (person_data.get("top_credits") or [])
                if raw.get("id")
            ],
            all_credits=[
                PersonCreditData(
                    id=int(c.get("id")),
                    media_type=str(c.get("media_type") or "movie"),
                    title=str(c.get("title") or ""),
                    year=str(c.get("year") or ""),
                    role=str(c.get("role") or ""),
                )
                for c in (person_data.get("all_credits") or [])
                if c.get("id")
            ],
        )
    )
