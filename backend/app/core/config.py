"""Application settings, loaded from environment / .env via Pydantic v2."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # Security
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    rate_limit_per_minute: int = 120

    # Database
    database_url: str = (
        "postgresql+asyncpg://athlete:athlete_dev_pwd@postgres:5432/athlete_hub"
    )

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # LLM
    llm_provider: Literal["anthropic", "openai", "local", "mock"] = "mock"
    llm_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    embedding_provider: Literal["mock", "openai", "local"] = "mock"
    # Local (fastembed/ONNX) multilingual model, 384 dims. mock also uses this dim
    # so the pgvector column stays consistent across providers. openai's
    # text-embedding-3-small is 1536 — switching to it requires EMBEDDING_DIM=1536
    # and a matching column migration.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384

    # Bootstrap admin
    bootstrap_admin_email: str = "admin@athletehub.example.com"
    bootstrap_admin_password: str = "admin_dev_pwd"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Synchronous URL for Alembic (psycopg driver)."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
