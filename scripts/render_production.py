"""Render strict, placeholder-free RootLens production Kubernetes manifests."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

_DNS_NAME = re.compile(
    r"(?=^.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_KUBERNETES_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_IMAGE = re.compile(r"^ghcr\.io/raman-gatech/rootlens@sha256:[a-f0-9]{64}$")
_PREREQUISITE_KINDS = {
    "Namespace",
    "ServiceAccount",
    "Role",
    "RoleBinding",
    "ConfigMap",
}


class ProductionRenderError(ValueError):
    """Raised when a production input is unsafe or incomplete."""


def render(
    *,
    source_directory: Path,
    output_directory: Path,
    hostname: str,
    image: str,
    ingress_class: str,
    monitored_namespace: str,
    otlp_endpoint: str,
    prometheus_url: str,
    tempo_url: str,
    loki_url: str,
) -> tuple[Path, ...]:
    """Validate deployment inputs and write phased Kubernetes manifests."""
    _validate_hostname(hostname)
    if not _IMAGE.fullmatch(image):
        raise ProductionRenderError("image must be the RootLens GHCR image at a sha256 digest")
    _validate_kubernetes_name("ingress class", ingress_class)
    _validate_kubernetes_name("monitored namespace", monitored_namespace)
    endpoints = {
        "ROOTLENS_OTLP_ENDPOINT": otlp_endpoint,
        "ROOTLENS_PROMETHEUS_URL": prometheus_url,
        "ROOTLENS_TEMPO_URL": tempo_url,
        "ROOTLENS_LOKI_URL": loki_url,
    }
    for name, value in endpoints.items():
        _validate_backend_url(name, value)

    rootlens_documents = _load_documents(source_directory / "rootlens.yaml")
    migration_documents = _load_documents(source_directory / "migrate-job.yaml")
    ingress_documents = _load_documents(source_directory / "ingress.yaml")
    _configure_rootlens(
        rootlens_documents,
        hostname=hostname,
        image=image,
        monitored_namespace=monitored_namespace,
        endpoints=endpoints,
    )
    _configure_migration(migration_documents, image=image)
    _configure_ingress(ingress_documents, hostname=hostname, ingress_class=ingress_class)

    prerequisites = tuple(
        document for document in rootlens_documents if document.get("kind") in _PREREQUISITE_KINDS
    )
    application = tuple(
        document
        for document in rootlens_documents
        if document.get("kind") not in _PREREQUISITE_KINDS
    )
    if not prerequisites or not application:
        raise ProductionRenderError("rootlens template did not contain both deployment phases")

    output_directory.mkdir(parents=True, exist_ok=True)
    outputs = (
        _write_documents(output_directory / "01-prerequisites.yaml", prerequisites),
        _write_documents(output_directory / "02-migration.yaml", migration_documents),
        _write_documents(output_directory / "03-application.yaml", application),
        _write_documents(output_directory / "04-ingress.yaml", ingress_documents),
    )
    for output in outputs:
        rendered_documents = tuple(yaml.safe_load_all(output.read_text(encoding="utf-8")))
        if _contains_placeholder(rendered_documents):
            raise ProductionRenderError(f"placeholder remained in {output.name}")
    return outputs


def _load_documents(path: Path) -> tuple[dict[str, Any], ...]:
    documents = tuple(item for item in yaml.safe_load_all(path.read_text()) if item is not None)
    if not documents or not all(isinstance(item, dict) for item in documents):
        raise ProductionRenderError(f"{path} did not contain Kubernetes objects")
    return documents


def _configure_rootlens(
    documents: tuple[dict[str, Any], ...],
    *,
    hostname: str,
    image: str,
    monitored_namespace: str,
    endpoints: dict[str, str],
) -> None:
    config = _object(documents, "ConfigMap", "rootlens-config")["data"]
    config.update(endpoints)
    config["ROOTLENS_TRUSTED_HOSTS"] = f'["{hostname}"]'
    config["ROOTLENS_KUBERNETES_NAMESPACE"] = monitored_namespace
    config["ROOTLENS_AGENT_PROVIDER"] = "openai"
    config["ROOTLENS_OPENAI_MODEL"] = "gpt-5.4-mini-2026-03-17"
    _object(documents, "Role", "rootlens-production-reader")["metadata"]["namespace"] = (
        monitored_namespace
    )
    _object(documents, "RoleBinding", "rootlens-production-reader")["metadata"]["namespace"] = (
        monitored_namespace
    )
    deployment = _object(documents, "Deployment", "rootlens-api")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    container["image"] = image
    for probe_name in ("readinessProbe", "livenessProbe", "startupProbe"):
        headers = container[probe_name]["httpGet"]["httpHeaders"]
        for header in headers:
            if header["name"] == "Host":
                header["value"] = hostname


def _configure_migration(documents: tuple[dict[str, Any], ...], *, image: str) -> None:
    job = _object(documents, "Job", "rootlens-migrate")
    job["spec"]["template"]["spec"]["containers"][0]["image"] = image


def _configure_ingress(
    documents: tuple[dict[str, Any], ...], *, hostname: str, ingress_class: str
) -> None:
    ingress = _object(documents, "Ingress", "rootlens-api")
    ingress["spec"]["ingressClassName"] = ingress_class
    ingress["spec"]["tls"][0]["hosts"] = [hostname]
    ingress["spec"]["rules"][0]["host"] = hostname


def _object(documents: tuple[dict[str, Any], ...], kind: str, name: str) -> dict[str, Any]:
    matches = [
        item
        for item in documents
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise ProductionRenderError(f"expected exactly one {kind}/{name}")
    return matches[0]


def _validate_hostname(hostname: str) -> None:
    if not _DNS_NAME.fullmatch(hostname) or hostname.endswith(".example.com"):
        raise ProductionRenderError("hostname must be a non-example public DNS name")


def _validate_kubernetes_name(label: str, value: str) -> None:
    if not _KUBERNETES_NAME.fullmatch(value):
        raise ProductionRenderError(f"{label} is not a valid Kubernetes name")


def _validate_backend_url(name: str, value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProductionRenderError(f"{name} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ProductionRenderError(f"{name} must not contain credentials")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ProductionRenderError(f"{name} must not use a loopback address")


def _write_documents(path: Path, documents: tuple[dict[str, Any], ...]) -> Path:
    path.write_text(
        yaml.safe_dump_all(documents, sort_keys=False, explicit_start=True),
        encoding="utf-8",
    )
    return path


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value == "rootlens.example.com" or "REPLACE_WITH" in value
    if isinstance(value, dict):
        return any(
            _contains_placeholder(key) or _contains_placeholder(item) for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_placeholder(item) for item in value)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, default=Path("deploy/production"))
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--ingress-class", required=True)
    parser.add_argument("--monitored-namespace", required=True)
    parser.add_argument("--otlp-endpoint", required=True)
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--tempo-url", required=True)
    parser.add_argument("--loki-url", required=True)
    arguments = parser.parse_args()
    outputs = render(
        source_directory=arguments.source_directory,
        output_directory=arguments.output_directory,
        hostname=arguments.hostname,
        image=arguments.image,
        ingress_class=arguments.ingress_class,
        monitored_namespace=arguments.monitored_namespace,
        otlp_endpoint=arguments.otlp_endpoint,
        prometheus_url=arguments.prometheus_url,
        tempo_url=arguments.tempo_url,
        loki_url=arguments.loki_url,
    )
    print("\n".join(str(item) for item in outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
