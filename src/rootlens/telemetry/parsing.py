"""Small defensive JSON parsing helpers for external backend payloads."""

from collections.abc import Mapping

from rootlens.telemetry.contracts import TelemetrySource
from rootlens.telemetry.errors import TelemetryErrorCode, TelemetryQueryError


def mapping(value: object, source: TelemetrySource, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise invalid(source, f"{field} must be an object")
    return value


def sequence(value: object, source: TelemetrySource, field: str) -> list[object]:
    if not isinstance(value, list):
        raise invalid(source, f"{field} must be an array")
    return value


def text(value: object, source: TelemetrySource, field: str) -> str:
    if not isinstance(value, str):
        raise invalid(source, f"{field} must be a string")
    return value


def optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def invalid(source: TelemetrySource, message: str) -> TelemetryQueryError:
    return TelemetryQueryError(
        source=source,
        code=TelemetryErrorCode.INVALID_RESPONSE,
        message=message,
    )
