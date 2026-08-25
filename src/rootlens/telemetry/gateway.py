"""Lifecycle facade for backend-specific telemetry clients."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from rootlens.config import Settings
from rootlens.telemetry.kubernetes import KubernetesClient
from rootlens.telemetry.loki import LokiClient
from rootlens.telemetry.prometheus import PrometheusClient
from rootlens.telemetry.tempo import TempoClient


class TelemetryGateway:
    """Own the four evidence clients without performing incident reasoning."""

    def __init__(
        self,
        *,
        prometheus: PrometheusClient,
        tempo: TempoClient,
        loki: LokiClient,
        kubernetes: KubernetesClient,
    ) -> None:
        self.prometheus = prometheus
        self.tempo = tempo
        self.loki = loki
        self.kubernetes = kubernetes

    @classmethod
    def from_settings(cls, settings: Settings) -> TelemetryGateway:
        token = settings.kubernetes_token or _read_optional(settings.kubernetes_token_file)
        verify: bool | str = settings.kubernetes_verify_ssl
        if (
            settings.kubernetes_verify_ssl
            and settings.kubernetes_ca_file
            and Path(settings.kubernetes_ca_file).is_file()
        ):
            verify = settings.kubernetes_ca_file
        return cls(
            prometheus=PrometheusClient(
                settings.prometheus_url,
                timeout_seconds=settings.query_timeout_seconds,
                max_retries=settings.query_max_retries,
                max_response_bytes=settings.query_max_response_bytes,
                max_concurrency=settings.query_max_concurrency,
            ),
            tempo=TempoClient(
                settings.tempo_url,
                timeout_seconds=settings.query_timeout_seconds,
                max_retries=settings.query_max_retries,
                max_response_bytes=settings.query_max_response_bytes,
                max_concurrency=settings.query_max_concurrency,
            ),
            loki=LokiClient(
                settings.loki_url,
                timeout_seconds=settings.query_timeout_seconds,
                max_retries=settings.query_max_retries,
                max_response_bytes=settings.query_max_response_bytes,
                max_concurrency=settings.query_max_concurrency,
            ),
            kubernetes=KubernetesClient(
                settings.kubernetes_url,
                bearer_token=token,
                verify=verify,
                timeout_seconds=settings.query_timeout_seconds,
                max_retries=settings.query_max_retries,
                max_response_bytes=settings.query_max_response_bytes,
                max_concurrency=settings.query_max_concurrency,
            ),
        )

    async def aclose(self) -> None:
        await self.prometheus.aclose()
        await self.tempo.aclose()
        await self.loki.aclose()
        await self.kubernetes.aclose()

    async def __aenter__(self) -> TelemetryGateway:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def _read_optional(path: str | None) -> str | None:
    if path is None:
        return None
    token_file = Path(path)
    if not token_file.is_file():
        return None
    return token_file.read_text(encoding="utf-8").strip()
