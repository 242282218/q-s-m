from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    status: str
    message: str


class HealthData(BaseModel):
    status: str
    service: str
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    checks: dict[str, HealthCheck] = Field(default_factory=dict)


class RequestMetrics(BaseModel):
    total: int
    avg_time: float
    slow_requests_count: int


class SlowQuery(BaseModel):
    duration: float
    statement: str


class DatabaseMetrics(BaseModel):
    total_queries: int
    total_time: float
    avg_time: float
    slow_queries_count: int
    recent_slow_queries: list[SlowQuery]


class MetricsData(BaseModel):
    requests: RequestMetrics
    database: DatabaseMetrics
    timestamp: str = Field(..., description="ISO-8601 timestamp")


class MetricsResetData(BaseModel):
    reset: bool
    timestamp: str = Field(..., description="ISO-8601 timestamp")


class TmdbDetailsData(BaseModel):
    poster_path: str | None = None
    backdrop_path: str | None = None
    title: str | None = None
    year: int | None = None


class SettingsUpdateData(BaseModel):
    updated_keys: list[str]
    restart_required: bool = True


class SettingsCurrentData(BaseModel):
    LOG_LEVEL: str
    HTTP_PROXY: str | None = None
    TRANSFER_KEEP_EXTRAS: bool
    TRANSFER_KEEP_SUBTITLES: bool
    TRANSFER_DRY_RUN: bool
    TRANSFER_CLEANUP_ENABLED: bool
    TRANSFER_CLEANUP_DELETE_NON_VIDEO: bool
    TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: bool
    TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: bool
    API_KEY_CONFIGURED: bool
    API_KEY_MASKED: str | None = None
    TMDB_API_KEY_CONFIGURED: bool
    TMDB_API_KEY_MASKED: str | None = None
    QUARK_TRANSFER_COOKIE_CONFIGURED: bool
    QUARK_TRANSFER_COOKIE_MASKED: str | None = None

