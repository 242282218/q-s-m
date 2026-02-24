from typing import Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx

from ...services.tmdb import TmdbClient, adapt_poster, gather_sections, adapt_detail, adapt_person
from ...core.config import get_settings, Settings

router = APIRouter()

# Templates configuration
# backend/app/api/endpoints/home.py -> backend/app/templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def get_tmdb_client(settings: Settings = Depends(get_settings)) -> TmdbClient:
    return TmdbClient(
        settings.tmdb_api_key,
        api_base=settings.tmdb_api_base,
        image_base=settings.tmdb_image_base,
        language=settings.default_language,
    )

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, tmdb_client: TmdbClient = Depends(get_tmdb_client)) -> HTMLResponse:
    try:
        # gather_sections now handles exceptions internally
        sections_raw = await gather_sections(tmdb_client)
    except Exception:
        sections_raw = {key: [] for key in ["trending", "popular", "top_rated", "now_playing"]}
    finally:
        await tmdb_client.close()

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

@router.get("/collection", response_class=HTMLResponse)
async def collection_page(request: Request) -> HTMLResponse:
    """我的收藏页面"""
    return templates.TemplateResponse(
        request,
        "collection.html",
        {
            "page_title": "我的收藏",
        },
    )

@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request, 
    q: Optional[str] = "",
    tmdb_client: TmdbClient = Depends(get_tmdb_client)
) -> HTMLResponse:
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
    
    await tmdb_client.close()
    
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "query": q or "",
            "posters": posters,
            "page_title": f"搜索：{q}" if q else "搜索",
        },
    )

@router.get("/person/{person_id}", response_class=HTMLResponse)
async def person_detail(
    request: Request, 
    person_id: int,
    tmdb_client: TmdbClient = Depends(get_tmdb_client)
) -> HTMLResponse:
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
        await tmdb_client.close()
        raise HTTPException(status_code=exc.response.status_code, detail="TMDB error") from exc
    except httpx.HTTPError as exc:
        await tmdb_client.close()
        raise HTTPException(status_code=502, detail="TMDB unavailable") from exc
    except Exception:
        await tmdb_client.close()
        raise

    combined = data.get("combined_credits") or {}
    credits_cast = combined.get("cast") or []
    credits_crew = combined.get("crew") or []
    credits = credits_cast + credits_crew
    if not credits and combined:
        credits = credits_cast or credits_crew
    person_data = adapt_person(data, tmdb_client, credits)
    
    await tmdb_client.close()
    
    return templates.TemplateResponse(
        request,
        "person.html",
        {
            "person": person_data,
            "page_title": person_data.get("name", ""),
        },
    )

@router.get("/{media_type}/{item_id}", response_class=HTMLResponse)
async def detail(
    request: Request, 
    media_type: str, 
    item_id: int,
    tmdb_client: TmdbClient = Depends(get_tmdb_client)
) -> HTMLResponse:
    if media_type not in ("movie", "tv"):
        await tmdb_client.close()
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
        await tmdb_client.close()
        raise HTTPException(status_code=exc.response.status_code, detail="TMDB error") from exc
    except httpx.HTTPError as exc:
        await tmdb_client.close()
        raise HTTPException(status_code=502, detail="TMDB unavailable") from exc
    except Exception:
        await tmdb_client.close()
        raise

    detail_data = adapt_detail(data, tmdb_client)
    rec_posters = [
        adapt_poster(rec, tmdb_client) for rec in detail_data.get("recommendations", []) if rec.get("id")
    ][:12]
    video_previews = rec_posters[:2]
    
    await tmdb_client.close()
    
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
