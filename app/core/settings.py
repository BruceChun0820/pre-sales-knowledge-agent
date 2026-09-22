from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated Phase 1 settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_root: Path = Path("data/raw")
    processed_root: Path = Path("data/processed")
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = Field(default="pre_sales_knowledge", min_length=1, max_length=128)
    tenant_id: Literal["demo"] = "demo"
    embedding_model: str | None = None
    parser_version: str = Field(default="parser-v1", min_length=1, max_length=64)
    cleaner_version: str = Field(default="cleaner-v1", min_length=1, max_length=64)
    chunker_version: str = Field(default="chunker-v1", min_length=1, max_length=64)
    max_file_size_mb: int = Field(default=50, ge=1, le=1024)

    @field_validator("qdrant_url")
    @classmethod
    def validate_qdrant_url(cls, value: str) -> str:
        return str(AnyHttpUrl(value)).rstrip("/")

    @field_validator("qdrant_api_key", "embedding_model", mode="before")
    @classmethod
    def normalize_optional_values(cls, value: object) -> object:
        if value == "":
            return None
        return value
