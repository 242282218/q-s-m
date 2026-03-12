from functools import lru_cache
from typing import Optional
import logging
import json

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .paths import resolve_default_env_path, resolve_runtime_env_path

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    app_name: str = "TMDB 海报墙"
    debug: bool = False
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_dir: str = Field("storage/logs", alias="LOG_DIR")

    api_key: Optional[str] = Field(None, alias="API_KEY")

    tmdb_api_key: Optional[str] = Field(None, alias="TMDB_API_KEY")
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

    quark_transfer_cookie: Optional[str] = Field(None, alias="QUARK_TRANSFER_COOKIE")

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

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        default_env_settings = DotEnvSettingsSource(
            settings_cls,
            env_file=resolve_default_env_path(),
            env_file_encoding="utf-8",
        )
        runtime_env_settings = DotEnvSettingsSource(
            settings_cls,
            env_file=resolve_runtime_env_path(),
            env_file_encoding="utf-8",
        )
        return (
            init_settings,
            runtime_env_settings,
            env_settings,
            default_env_settings,
            file_secret_settings,
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def validate_production_security(self) -> list[str]:
        """验证生产环境安全配置"""
        warnings = []

        if not self.debug and not self.api_key:
            warnings.append("生产环境未设置 API_KEY，所有端点无认证保护")

        if self.api_key and len(self.api_key) < 16:
            warnings.append("API_KEY 长度过短，建议至少 32 字符")

        if "*" in self.cors_origins or "http://localhost" in str(self.cors_origins):
            if not self.debug:
                warnings.append("生产环境 CORS 配置包含不安全的源")

        if not self.tmdb_api_key:
            warnings.append("未配置 TMDB_API_KEY，TMDB 相关功能将不可用")

        if not self.quark_transfer_cookie:
            warnings.append("未配置 QUARK_TRANSFER_COOKIE，转存和网盘校验功能将不可用")

        return warnings

    @property
    def quark_cookie(self) -> str:
        """Backward-compatible alias for legacy code paths."""
        return self.quark_transfer_cookie


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    if not settings.debug:
        warnings = settings.validate_production_security()
        for warning in warnings:
            logger.warning(f"安全警告: {warning}")

    return settings
