"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local-development defaults."""

    model_config = SettingsConfigDict(
        env_prefix="ROOTLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    service_name: str = "rootlens-api"
    service_version: str = "0.4.0"
    database_url: str = Field(
        default="postgresql+asyncpg://rootlens:rootlens@localhost:5432/rootlens",
        repr=False,
    )
    otlp_endpoint: str = "http://localhost:4317"
    telemetry_enabled: bool = True
    prometheus_url: str = "http://localhost:9090"
    tempo_url: str = "http://localhost:3200"
    loki_url: str = "http://localhost:3100"
    query_timeout_seconds: float = Field(default=10.0, gt=0)
    query_max_retries: int = Field(default=2, ge=0, le=5)
    query_max_response_bytes: int = Field(default=10_485_760, gt=0)
    query_max_concurrency: int = Field(default=8, gt=0)
    kubernetes_url: str = "https://kubernetes.default.svc"
    kubernetes_token: str | None = Field(default=None, repr=False)
    kubernetes_token_file: str | None = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    kubernetes_ca_file: str | None = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    kubernetes_verify_ssl: bool = True
    kubernetes_namespace: str = "default"
    topology_trace_limit: int = Field(default=100, gt=0, le=500)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
