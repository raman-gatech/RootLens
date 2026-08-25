"""Bounded and resilient asynchronous HTTP transport for telemetry queries."""

from __future__ import annotations

import asyncio
import json
from types import TracebackType
from typing import cast

import httpx

from rootlens.telemetry.contracts import TelemetrySource
from rootlens.telemetry.errors import TelemetryErrorCode, TelemetryQueryError


class AsyncTelemetryHttpClient:
    """Shared GET-only transport with retries, timeouts, and response limits."""

    def __init__(
        self,
        *,
        source: TelemetrySource,
        base_url: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        max_response_bytes: int = 10_485_760,
        max_concurrency: int = 8,
        headers: dict[str, str] | None = None,
        verify: bool | str = True,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        self.source = source
        self._max_retries = max_retries
        self._max_response_bytes = max_response_bytes
        self._retry_backoff_seconds = retry_backoff_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
            verify=verify,
            transport=transport,
        )

    async def get_json(self, path: str, *, params: dict[str, str]) -> object:
        """Return decoded JSON or raise a typed, non-fabricated query error."""

        async with self._semaphore:
            for attempt in range(self._max_retries + 1):
                try:
                    retry_status: int | None = None
                    async with self._client.stream("GET", path, params=params) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            retry_status = response.status_code
                        elif response.is_error:
                            raise self._status_error(response.status_code, retryable=False)
                        else:
                            content_length = response.headers.get("content-length")
                            if content_length is not None:
                                try:
                                    declared_size = int(content_length)
                                except ValueError:
                                    declared_size = 0
                                if declared_size > self._max_response_bytes:
                                    raise self._too_large()

                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > self._max_response_bytes:
                                    raise self._too_large()
                            try:
                                return cast(object, json.loads(content))
                            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                                raise TelemetryQueryError(
                                    source=self.source,
                                    code=TelemetryErrorCode.INVALID_RESPONSE,
                                    message="backend returned invalid JSON",
                                ) from exc
                except httpx.TimeoutException as exc:
                    if attempt < self._max_retries:
                        await self._backoff(attempt)
                        continue
                    raise TelemetryQueryError(
                        source=self.source,
                        code=TelemetryErrorCode.TIMEOUT,
                        message="backend request timed out",
                        retryable=True,
                    ) from exc
                except httpx.TransportError as exc:
                    if attempt < self._max_retries:
                        await self._backoff(attempt)
                        continue
                    raise TelemetryQueryError(
                        source=self.source,
                        code=TelemetryErrorCode.TRANSPORT,
                        message="backend transport failed",
                        retryable=True,
                    ) from exc
                if retry_status is not None:
                    if attempt < self._max_retries:
                        await self._backoff(attempt)
                        continue
                    raise self._status_error(retry_status, retryable=True)

        raise AssertionError("retry loop exhausted without returning or raising")

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._retry_backoff_seconds * (2**attempt), 1.0)
        if delay > 0:
            await asyncio.sleep(delay)

    def _status_error(self, status_code: int, *, retryable: bool) -> TelemetryQueryError:
        return TelemetryQueryError(
            source=self.source,
            code=TelemetryErrorCode.HTTP_STATUS,
            message="backend rejected the query",
            retryable=retryable,
            status_code=status_code,
        )

    def _too_large(self) -> TelemetryQueryError:
        return TelemetryQueryError(
            source=self.source,
            code=TelemetryErrorCode.RESPONSE_TOO_LARGE,
            message=f"backend response exceeded {self._max_response_bytes} bytes",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncTelemetryHttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
