from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass
except Exception:
    pass


class Settings(BaseSettings):
    app_name: str = "TMDB 海报墙"
    debug: bool = False
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    tmdb_api_key: str = Field(..., alias="TMDB_API_KEY")
    default_language: str = Field("zh-CN", alias="DEFAULT_LANG")
    tmdb_api_base: str = Field("https://api.themoviedb.org/3", alias="TMDB_API_BASE")
    tmdb_image_base: str = Field("https://image.tmdb.org/t/p/", alias="TMDB_IMAGE_BASE")
    http_proxy: Optional[str] = Field(None, alias="HTTP_PROXY")

    quark_search_api_prefix: str = Field("/api/quark", alias="QUARK_SEARCH_API_PREFIX")
    quark_search_base_url: str = Field("https://b.funletu.com", alias="QUARK_SEARCH_BASE_URL")
    quark_search_max_retries: int = Field(3, alias="QUARK_SEARCH_MAX_RETRIES")
    quark_search_rate_limit: float = Field(0.5, alias="QUARK_SEARCH_RATE_LIMIT")
    quark_search_timeout: int = Field(10, alias="QUARK_SEARCH_TIMEOUT")
    quark_search_confidence_weight: float = Field(0.7, alias="QUARK_SEARCH_CONFIDENCE_WEIGHT")
    quark_search_quality_weight: float = Field(0.3, alias="QUARK_SEARCH_QUALITY_WEIGHT")
    quark_search_max_results: int = Field(20, alias="QUARK_SEARCH_MAX_RESULTS")

    cache_enabled: bool = Field(True, alias="CACHE_ENABLED")
    cache_type: str = Field("memory", alias="CACHE_TYPE")
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    cache_ttl: int = Field(3600, alias="CACHE_TTL")
    
    quark_cookie: str = Field("", alias="QUARK_COOKIE")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
