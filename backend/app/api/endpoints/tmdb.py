from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from ...services.tmdb import TmdbClient, adapt_detail, adapt_person, adapt_poster
from ..schemas.common import ApiResponse, ok
from ..schemas.system import TmdbDetailsData
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


def get_tmdb_client(request: Request) -> TmdbClient:
    return request.app.state.tmdb_client


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
    try:
        results = await tmdb_client.search_multi(query)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="TMDB unavailable") from exc

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
        raise HTTPException(status_code=400, detail="TMDB ID 必须为正整数")

    tmdb_client = get_tmdb_client(request)
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
            raise HTTPException(status_code=404, detail="TMDB 资源不存在")
        raise HTTPException(status_code=502, detail=f"TMDB API错误: {e.response.status_code}")
    except httpx.ConnectError as e:
        logger.error("TMDB API连接错误: %s", str(e))
        raise HTTPException(status_code=503, detail=f"无法连接到TMDB API: {str(e)}")
    except httpx.TimeoutException as e:
        logger.error("TMDB API超时错误: %s", str(e))
        raise HTTPException(status_code=504, detail=f"TMDB API请求超时: {str(e)}")
    except Exception as e:
        logger.error("获取TMDB详情失败: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取TMDB详情失败: {str(e)}")


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
        raise HTTPException(status_code=404, detail="Unsupported media type")
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="item_id 必须为正整数")

    tmdb_client = get_tmdb_client(request)
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
        raise HTTPException(status_code=exc.response.status_code, detail="TMDB error") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="TMDB unavailable") from exc

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
