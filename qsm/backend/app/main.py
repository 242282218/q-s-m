import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .tmdb import TmdbClient, adapt_poster, gather_sections

# 导入夸克搜索路由
from .quark.api.routes import router as quark_router

settings = get_settings()
tmdb_client = TmdbClient(
    settings.tmdb_api_key,
    api_base=settings.tmdb_api_base,
    image_base=settings.tmdb_image_base,
    language=settings.default_language,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await tmdb_client.close()


app = FastAPI(title="TMDB 海报墙", lifespan=lifespan)

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 包含夸克搜索路由，添加/api前缀
app.include_router(quark_router, prefix="/api")


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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    try:
        sections_raw = await gather_sections(tmdb_client)
    except httpx.HTTPError:
        sections_raw = {key: [] for key in ["trending", "popular", "top_rated", "now_playing"]}

    sections = {
        key: [adapt_poster(item, tmdb_client) for item in value if item.get("id")]
        for key, value in sections_raw.items()
    }
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "sections": sections,
            "page_title": "TMDB 海报墙",
        },
    )


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: Optional[str] = "") -> HTMLResponse:
    posters: List[Dict] = []
    if q:
        try:
            results = await tmdb_client.search_multi(q)
        except httpx.HTTPError:
            results = []
        posters = [
            adapt_poster(item, tmdb_client)
            for item in results
            if item.get("id") and (item.get("media_type") in ("movie", "tv"))
        ]
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "query": q or "",
            "posters": posters,
            "page_title": f"搜索：{q}" if q else "搜索",
        },
    )


@app.get("/person/{person_id}", response_class=HTMLResponse)
async def person_detail(request: Request, person_id: int) -> HTMLResponse:
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
    return templates.TemplateResponse(
        request,
        "person.html",
        {
            "person": person_data,
            "page_title": person_data.get("name", ""),
        },
    )


@app.get("/{media_type}/{item_id}", response_class=HTMLResponse)
async def detail(request: Request, media_type: str, item_id: int) -> HTMLResponse:
    if media_type not in ("movie", "tv"):
        raise HTTPException(status_code=404, detail="Unsupported media type")
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
    rec_posters = [
        adapt_poster(rec, tmdb_client) for rec in detail_data.get("recommendations", []) if rec.get("id")
    ][:12]
    video_previews = rec_posters[:2]
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "item": detail_data,
            "recommendations": rec_posters,
            "video_previews": video_previews,
            "page_title": detail_data.get("title", ""),
        },
    )
