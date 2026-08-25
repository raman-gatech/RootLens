"""Read-only Kubernetes state and event contract tests."""

import httpx
import pytest

from rootlens.telemetry import TelemetrySource
from rootlens.telemetry.kubernetes import KubernetesClient


@pytest.mark.asyncio
async def test_kubernetes_client_uses_get_and_never_leaks_token_to_provenance() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.headers["authorization"] == "Bearer test-secret"
        assert request.url.path == "/api/v1/namespaces/demo/pods"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "metadata": {
                            "namespace": "demo",
                            "name": "checkout-abc",
                            "uid": "pod-1",
                            "labels": {"app": "checkout"},
                            "creationTimestamp": "2026-08-24T12:00:00Z",
                        },
                        "spec": {"nodeName": "node-a"},
                        "status": {"phase": "Running"},
                    }
                ]
            },
        )

    client = KubernetesClient(
        "https://kubernetes.test",
        bearer_token="test-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.list_pods("demo", label_selector="app=checkout")
    finally:
        await client.aclose()

    assert methods == ["GET"]
    assert result.provenance.source is TelemetrySource.KUBERNETES
    assert result.provenance.parameters == {"labelSelector": "app=checkout"}
    assert "test-secret" not in result.provenance.model_dump_json()
    assert result.data[0].phase == "Running"
    assert not hasattr(client, "post")
    assert not hasattr(client, "delete")


@pytest.mark.asyncio
async def test_kubernetes_events_become_factual_change_records() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "metadata": {"namespace": "demo", "name": "rollout"},
                        "type": "Normal",
                        "reason": "ScalingReplicaSet",
                        "message": "Scaled up replica set checkout-2",
                        "involvedObject": {"kind": "Deployment", "name": "checkout"},
                        "count": 1,
                        "lastTimestamp": "2026-08-24T12:01:00Z",
                    }
                ]
            },
        )

    client = KubernetesClient("https://kubernetes.test", transport=httpx.MockTransport(handler))
    try:
        result = await client.list_change_events("demo")
    finally:
        await client.aclose()

    assert result.data[0].change_type == "ScalingReplicaSet"
    assert result.data[0].resource_name == "checkout"
    assert result.warnings
