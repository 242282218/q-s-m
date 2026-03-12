from __future__ import annotations

from pydantic import BaseModel, Field


class HomePosterItem(BaseModel):
    id: int
    media_type: str
    title: str
    subtitle: str = ""
    overview: str = ""
    genres: list[int] = Field(default_factory=list)
    tone: str = "neutral"
    poster_url: str | None = None
    backdrop_url: str | None = None


class HomeHeroItem(BaseModel):
    id: int
    media_type: str
    title: str
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    runtime: int | None = None
    vote: float | None = None
    tagline: str = ""
    overview: str = ""
    poster_url: str | None = None
    backdrop_url: str | None = None


class HomeSectionMeta(BaseModel):
    key: str
    title: str
    tag: str | None = None


class HomeData(BaseModel):
    hero_items: list[HomeHeroItem]
    sections: dict[str, list[HomePosterItem]]
    section_order: list[HomeSectionMeta]
    generated_at: str = Field(..., description="ISO-8601 timestamp")

