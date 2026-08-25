"""Read-only Kubernetes API client for workload state and change evidence."""

import re
from collections.abc import Mapping
from datetime import datetime

import httpx

from rootlens.telemetry.contracts import (
    ChangeEvent,
    DeploymentSnapshot,
    KubernetesEvent,
    PodSnapshot,
    QueryProvenance,
    TelemetryEnvelope,
    TelemetrySource,
)
from rootlens.telemetry.http import AsyncTelemetryHttpClient
from rootlens.telemetry.parsing import integer, mapping, optional_text, sequence, string_map

_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")


class KubernetesClient(AsyncTelemetryHttpClient):
    """Expose only Kubernetes GET/list operations; no mutation methods exist."""

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        max_response_bytes: int = 10_485_760,
        max_concurrency: int = 8,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_backoff_seconds: float = 0.1,
    ) -> None:
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
        super().__init__(
            source=TelemetrySource.KUBERNETES,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_response_bytes=max_response_bytes,
            max_concurrency=max_concurrency,
            headers=headers,
            verify=verify,
            transport=transport,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    async def list_pods(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
    ) -> TelemetryEnvelope[list[PodSnapshot]]:
        path = f"/api/v1/namespaces/{_namespace(namespace)}/pods"
        params = _selector_params(label_selector=label_selector)
        payload = await self.get_json(path, params=params)
        pods = [_pod(item) for item in _items(payload)]
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=path,
                parameters=params,
            ),
            data=pods,
        )

    async def list_deployments(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
    ) -> TelemetryEnvelope[list[DeploymentSnapshot]]:
        path = f"/apis/apps/v1/namespaces/{_namespace(namespace)}/deployments"
        params = _selector_params(label_selector=label_selector)
        payload = await self.get_json(path, params=params)
        deployments = [_deployment(item) for item in _items(payload)]
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=path,
                parameters=params,
            ),
            data=deployments,
        )

    async def list_events(
        self,
        namespace: str,
        *,
        field_selector: str | None = None,
    ) -> TelemetryEnvelope[list[KubernetesEvent]]:
        path = f"/api/v1/namespaces/{_namespace(namespace)}/events"
        params = _selector_params(field_selector=field_selector)
        payload = await self.get_json(path, params=params)
        events = [_event(item) for item in _items(payload)]
        return TelemetryEnvelope(
            provenance=QueryProvenance.create(
                source=self.source,
                query=path,
                parameters=params,
            ),
            data=events,
            warnings=("Kubernetes Events are best-effort supplemental evidence.",),
        )

    async def list_change_events(
        self,
        namespace: str,
    ) -> TelemetryEnvelope[list[ChangeEvent]]:
        """Normalize deployment/ReplicaSet events without assigning causality."""

        evidence = await self.list_events(namespace)
        changes = [
            ChangeEvent(
                timestamp=event.last_seen or event.first_seen,
                namespace=event.namespace,
                resource_kind=event.involved_kind or "Unknown",
                resource_name=event.involved_name or "unknown",
                change_type=event.reason or event.event_type or "event",
                details={
                    key: value
                    for key, value in {
                        "message": event.message,
                        "count": event.count,
                    }.items()
                    if value is not None
                },
            )
            for event in evidence.data
            if event.involved_kind in {"Deployment", "ReplicaSet"}
        ]
        return TelemetryEnvelope(
            provenance=evidence.provenance,
            data=changes,
            warnings=evidence.warnings,
        )


def _namespace(value: str) -> str:
    if not _NAMESPACE_PATTERN.fullmatch(value):
        raise ValueError("namespace must be a valid DNS label")
    return value


def _selector_params(
    *,
    label_selector: str | None = None,
    field_selector: str | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if label_selector:
        params["labelSelector"] = label_selector
    if field_selector:
        params["fieldSelector"] = field_selector
    return params


def _items(payload: object) -> list[object]:
    root = mapping(payload, TelemetrySource.KUBERNETES, "response")
    return sequence(root.get("items"), TelemetrySource.KUBERNETES, "items")


def _pod(value: object) -> PodSnapshot:
    item = mapping(value, TelemetrySource.KUBERNETES, "pod")
    metadata = mapping(item.get("metadata"), TelemetrySource.KUBERNETES, "pod.metadata")
    spec = _optional_mapping(item.get("spec"))
    status = _optional_mapping(item.get("status"))
    owner_references = metadata.get("ownerReferences")
    owner: Mapping[str, object] = {}
    if isinstance(owner_references, list) and owner_references:
        owner = _optional_mapping(owner_references[0])
    return PodSnapshot(
        namespace=optional_text(metadata.get("namespace")) or "default",
        name=optional_text(metadata.get("name")) or "unknown",
        uid=optional_text(metadata.get("uid")),
        phase=optional_text(status.get("phase")),
        node_name=optional_text(spec.get("nodeName")),
        labels=string_map(metadata.get("labels")),
        created_at=_timestamp(metadata.get("creationTimestamp")),
        owner_kind=optional_text(owner.get("kind")),
        owner_name=optional_text(owner.get("name")),
    )


def _deployment(value: object) -> DeploymentSnapshot:
    item = mapping(value, TelemetrySource.KUBERNETES, "deployment")
    metadata = mapping(item.get("metadata"), TelemetrySource.KUBERNETES, "deployment.metadata")
    spec = _optional_mapping(item.get("spec"))
    status = _optional_mapping(item.get("status"))
    return DeploymentSnapshot(
        namespace=optional_text(metadata.get("namespace")) or "default",
        name=optional_text(metadata.get("name")) or "unknown",
        uid=optional_text(metadata.get("uid")),
        generation=integer(metadata.get("generation")),
        observed_generation=integer(status.get("observedGeneration")),
        replicas=integer(spec.get("replicas")),
        ready_replicas=integer(status.get("readyReplicas")),
        labels=string_map(metadata.get("labels")),
        annotations=string_map(metadata.get("annotations")),
        created_at=_timestamp(metadata.get("creationTimestamp")),
    )


def _event(value: object) -> KubernetesEvent:
    item = mapping(value, TelemetrySource.KUBERNETES, "event")
    metadata = mapping(item.get("metadata"), TelemetrySource.KUBERNETES, "event.metadata")
    involved_object = _optional_mapping(item.get("involvedObject"))
    return KubernetesEvent(
        namespace=optional_text(metadata.get("namespace")) or "default",
        name=optional_text(metadata.get("name")) or "unknown",
        event_type=optional_text(item.get("type")),
        reason=optional_text(item.get("reason")),
        message=optional_text(item.get("message")) or optional_text(item.get("note")),
        involved_kind=optional_text(involved_object.get("kind")),
        involved_name=optional_text(involved_object.get("name")),
        count=integer(item.get("count")),
        first_seen=_timestamp(item.get("firstTimestamp")),
        last_seen=_timestamp(item.get("lastTimestamp")) or _timestamp(item.get("eventTime")),
    )


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}
