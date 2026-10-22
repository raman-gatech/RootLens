"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local-development defaults."""

    model_config = SettingsConfigDict(
        env_prefix="ROOTLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    service_name: str = "rootlens-api"
    service_version: str = "1.0.2"
    schema_revision: str = "20260825_0008"
    docs_enabled: bool = True
    auth_enabled: bool = False
    auth_credentials_file: str | None = None
    trusted_hosts: tuple[str, ...] = ("*",)
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
    agent_provider: Literal["deterministic", "openai"] = "deterministic"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.4-mini"
    investigation_log_limit: int = Field(default=500, gt=0, le=5_000)
    remediation_execution_enabled: bool = False
    remediation_kubectl_path: str = "kubectl"
    remediation_kubernetes_context: str = "kind-rootlens"
    remediation_allowed_namespaces: tuple[str, ...] = ("otel-demo",)
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    @model_validator(mode="after")
    def validate_security_boundaries(self) -> Settings:
        if self.agent_provider == "openai" and not self.openai_api_key:
            raise ValueError("the OpenAI provider requires ROOTLENS_OPENAI_API_KEY")
        if self.auth_enabled and not self.auth_credentials_file:
            raise ValueError("authentication requires ROOTLENS_AUTH_CREDENTIALS_FILE")
        if self.remediation_execution_enabled and not self.auth_enabled:
            raise ValueError("remediation execution requires authentication")
        if self.environment in {"staging", "production"}:
            if not self.auth_enabled:
                raise ValueError("staging/production requires authentication")
            if not self.trusted_hosts or "*" in self.trusted_hosts:
                raise ValueError("staging/production requires an explicit trusted-host allowlist")
            if "rootlens:rootlens@" in self.database_url:
                raise ValueError("staging/production cannot use development database credentials")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
