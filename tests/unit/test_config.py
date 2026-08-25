import pytest
from pydantic import ValidationError

from rootlens.config import Settings


def test_settings_use_rootlens_environment_prefix(monkeypatch: object) -> None:
    monkeypatch.setenv("ROOTLENS_ENVIRONMENT", "test")  # type: ignore[attr-defined]

    settings = Settings()

    assert settings.environment == "test"
    assert settings.service_name == "rootlens-api"


def test_production_rejects_insecure_defaults() -> None:
    with pytest.raises(ValidationError, match="staging/production requires authentication"):
        Settings(environment="production")


def test_openai_provider_requires_a_key() -> None:
    with pytest.raises(ValidationError, match="OpenAI provider requires"):
        Settings(agent_provider="openai", openai_api_key=None)
