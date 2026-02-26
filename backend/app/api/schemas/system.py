from __future__ import annotations

from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: str
    service: str
    timestamp: str = Field(..., description="ISO-8601 timestamp")


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

