"""Production manifest rendering tests."""

from pathlib import Path

import pytest
import yaml

from scripts.render_production import ProductionRenderError, render

_DIGEST = "sha256:" + "a" * 64
_IMAGE = f"ghcr.io/raman-gatech/rootlens@{_DIGEST}"
_SOURCE = Path(__file__).parents[2] / "deploy" / "production"


def test_render_writes_ordered_placeholder_free_phases(tmp_path: Path) -> None:
    outputs = render(
        source_directory=_SOURCE,
        output_directory=tmp_path,
        hostname="rootlens.ops.example.net",
        image=_IMAGE,
        ingress_class="nginx",
        monitored_namespace="payments",
        otlp_endpoint="https://otel.internal.example.net:4317",
        prometheus_url="https://prometheus.internal.example.net",
        tempo_url="https://tempo.internal.example.net",
        loki_url="https://loki.internal.example.net",
    )

    assert [item.name for item in outputs] == [
        "01-prerequisites.yaml",
        "02-migration.yaml",
        "03-application.yaml",
        "04-ingress.yaml",
    ]
    assert all("rootlens.example.com" not in item.read_text() for item in outputs)
    prerequisites = tuple(yaml.safe_load_all(outputs[0].read_text()))
    config = next(item for item in prerequisites if item["kind"] == "ConfigMap")
    assert config["data"]["ROOTLENS_TRUSTED_HOSTS"] == '["rootlens.ops.example.net"]'
    assert config["data"]["ROOTLENS_AGENT_PROVIDER"] == "openai"
    assert config["data"]["ROOTLENS_OPENAI_MODEL"] == "gpt-5.4-mini-2026-03-17"
    role = next(item for item in prerequisites if item["kind"] == "Role")
    binding = next(item for item in prerequisites if item["kind"] == "RoleBinding")
    assert role["metadata"]["namespace"] == "payments"
    assert binding["metadata"]["namespace"] == "payments"
    migration = next(yaml.safe_load_all(outputs[1].read_text()))
    assert migration["spec"]["template"]["spec"]["containers"][0]["image"] == _IMAGE
    application = tuple(yaml.safe_load_all(outputs[2].read_text()))
    deployment = next(item for item in application if item["kind"] == "Deployment")
    assert deployment["spec"]["template"]["spec"]["containers"][0]["image"] == _IMAGE
    ingress = next(yaml.safe_load_all(outputs[3].read_text()))
    assert ingress["spec"]["rules"][0]["host"] == "rootlens.ops.example.net"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"hostname": "rootlens.example.com"}, "public DNS"),
        ({"image": "ghcr.io/raman-gatech/rootlens:latest"}, "sha256 digest"),
        ({"prometheus_url": "http://localhost:9090"}, "loopback"),
        ({"tempo_url": "https://user:secret@tempo.example.net"}, "credentials"),
    ],
)
def test_render_rejects_unsafe_inputs(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    arguments = {
        "source_directory": _SOURCE,
        "output_directory": tmp_path,
        "hostname": "rootlens.ops.example.net",
        "image": _IMAGE,
        "ingress_class": "nginx",
        "monitored_namespace": "payments",
        "otlp_endpoint": "https://otel.internal.example.net:4317",
        "prometheus_url": "https://prometheus.internal.example.net",
        "tempo_url": "https://tempo.internal.example.net",
        "loki_url": "https://loki.internal.example.net",
    }
    arguments.update(overrides)

    with pytest.raises(ProductionRenderError, match=message):
        render(**arguments)
