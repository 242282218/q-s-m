from __future__ import annotations

from pydantic import BaseModel, Field


class PosterCardData(BaseModel):
    id: int
    media_type: str
    title: str
    subtitle: str = ""
    overview: str = ""
    genres: list[int] = Field(default_factory=list)
    tone: str = "neutral"
    poster_url: str | None = None
    backdrop_url: str | None = None


class CastMemberData(BaseModel):
    id: int
    name: str
    character: str = ""
    profile_url: str | None = None


class VideoData(BaseModel):
    key: str
    name: str
    type: str = ""
    official: bool = False


class DetailItemData(BaseModel):
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
    poster_path: str | None = None
    backdrop_path: str | None = None
    cast: list[CastMemberData] = Field(default_factory=list)
    videos: list[VideoData] = Field(default_factory=list)


class DetailPageData(BaseModel):
    item: DetailItemData
    recommendations: list[PosterCardData] = Field(default_factory=list)


class PersonCreditData(BaseModel):
    id: int
    media_type: str
    title: str
    year: str = ""
    role: str = ""


class PersonData(BaseModel):
    id: int
    name: str
    known_for: str = ""
    biography: str = ""
    birthday: str = ""
    place_of_birth: str = ""
    profile_url: str | None = None
    top_credits: list[PosterCardData] = Field(default_factory=list)
    all_credits: list[PersonCreditData] = Field(default_factory=list)


class SearchPageData(BaseModel):
    query: str = ""
    posters: list[PosterCardData] = Field(default_factory=list)
