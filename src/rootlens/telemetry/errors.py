"""Typed failures returned by telemetry backends."""

from enum import StrEnum

from rootlens.telemetry.contracts import TelemetrySource


class TelemetryErrorCode(StrEnum):
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    HTTP_STATUS = "http_status"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION = "configuration"


class TelemetryQueryError(RuntimeError):
    """A safe, machine-readable backend query failure."""

    def __init__(
        self,
        *,
        source: TelemetrySource,
        code: TelemetryErrorCode,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.code = code
        self.retryable = retryable
        self.status_code = status_code

    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.source.value} {self.code.value}{status}: {super().__str__()}"
