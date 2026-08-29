"""RootLens self-observability transport tests."""

import pytest

from rootlens.observability import otlp_uses_insecure_transport


def test_plaintext_otlp_must_be_explicit() -> None:
    assert otlp_uses_insecure_transport("http://otel-collector.observability.svc:4317")
    assert not otlp_uses_insecure_transport("https://otel.example.net:4317")


@pytest.mark.parametrize(
    "endpoint",
    ["otel.example.net:4317", "grpc://otel.example.net:4317", "https:///missing-host"],
)
def test_rejects_invalid_otlp_endpoint(endpoint: str) -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        otlp_uses_insecure_transport(endpoint)
