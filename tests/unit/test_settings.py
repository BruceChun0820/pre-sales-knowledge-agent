from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_settings_have_safe_defaults_without_a_secret() -> None:
    settings = Settings(_env_file=None)

    assert settings.tenant_id == "demo"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.qdrant_api_key is None
    assert settings.data_root.as_posix() == "data/raw"


def test_settings_load_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.example:6333/")
    monkeypatch.setenv("QDRANT_COLLECTION", "test_collection")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "12")
    monkeypatch.setenv("QDRANT_API_KEY", "")
    monkeypatch.setenv("EMBEDDING_MODEL", "baseline-model")

    settings = Settings(_env_file=None)

    assert settings.qdrant_url == "http://qdrant.example:6333"
    assert settings.qdrant_collection == "test_collection"
    assert settings.max_file_size_mb == 12
    assert settings.qdrant_api_key is None
    assert settings.embedding_model == "baseline-model"


def test_settings_reject_invalid_controlled_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_ID", "customer-controlled")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("TENANT_ID", "demo")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
