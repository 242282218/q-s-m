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

    quark_transfer_cookie: str = Field(..., alias="QUARK_TRANSFER_COOKIE")

    transfer_keep_extras: bool = Field(False, alias="TRANSFER_KEEP_EXTRAS")
    transfer_keep_subtitles: bool = Field(False, alias="TRANSFER_KEEP_SUBTITLES")
    transfer_dry_run: bool = Field(False, alias="TRANSFER_DRY_RUN")
    transfer_cleanup_enabled: bool = Field(True, alias="TRANSFER_CLEANUP_ENABLED")
    transfer_cleanup_delete_non_video: bool = Field(True, alias="TRANSFER_CLEANUP_DELETE_NON_VIDEO")
    transfer_cleanup_delete_unselected_video: bool = Field(True, alias="TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO")
    transfer_cleanup_delete_empty_dirs: bool = Field(True, alias="TRANSFER_CLEANUP_DELETE_EMPTY_DIRS")

    base_movie_dir: str = Field("/影视收藏/电影", alias="BASE_MOVIE_DIR")
    base_tv_dir: str = Field("/影视收藏/电视剧", alias="BASE_TV_DIR")
    base_anime_dir: str = Field("/影视收藏/动漫", alias="BASE_ANIME_DIR")
    base_documentary_dir: str = Field("/影视收藏/纪录片", alias="BASE_DOCUMENTARY_DIR")

    cors_origins: list[str] = Field(
        ["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ORIGINS"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
