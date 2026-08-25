from rootlens.config import Settings


def test_settings_use_rootlens_environment_prefix(monkeypatch: object) -> None:
    monkeypatch.setenv("ROOTLENS_ENVIRONMENT", "test")  # type: ignore[attr-defined]

    settings = Settings()

    assert settings.environment == "test"
    assert settings.service_name == "rootlens-api"
