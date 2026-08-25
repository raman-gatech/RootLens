"""Tests for the five Chaos Mesh experiment templates."""

from experiment_controller.catalog import catalog, scenario
from experiment_controller.contracts import FaultType
from experiment_controller.manifests import manifest_digest, manifest_yaml, render_manifest


def test_catalog_contains_exactly_five_required_fault_families() -> None:
    assert {item.fault_type for item in catalog()} == set(FaultType)


def test_every_fault_renders_a_scoped_chaos_mesh_resource() -> None:
    expected_kinds = {
        FaultType.POD_KILL: "PodChaos",
        FaultType.CPU_STRESS: "StressChaos",
        FaultType.NETWORK_LATENCY: "NetworkChaos",
        FaultType.PACKET_LOSS: "NetworkChaos",
        FaultType.HTTP_DELAY: "HTTPChaos",
    }

    for fault_type, expected_kind in expected_kinds.items():
        spec = scenario(fault_type)
        manifest = render_manifest(spec)
        metadata = manifest["metadata"]
        chaos_spec = manifest["spec"]

        assert manifest["apiVersion"] == "chaos-mesh.org/v1alpha1"
        assert manifest["kind"] == expected_kind
        assert metadata["namespace"] == "otel-demo"
        assert metadata["labels"]["rootlens.io/experiment-id"] == str(spec.experiment_id)
        assert chaos_spec["selector"]["namespaces"] == ["otel-demo"]
        assert chaos_spec["selector"]["labelSelectors"] == {
            "app.kubernetes.io/component": spec.target_service
        }
        assert chaos_spec["duration"] == "30s"


def test_network_faults_are_limited_to_the_declared_dependency() -> None:
    spec = scenario(FaultType.NETWORK_LATENCY)
    chaos_spec = render_manifest(spec)["spec"]

    assert chaos_spec["action"] == "delay"
    assert chaos_spec["direction"] == "to"
    assert chaos_spec["target"]["selector"]["labelSelectors"] == {
        "app.kubernetes.io/component": "payment"
    }
    assert chaos_spec["delay"]["latency"] == "1500ms"


def test_manifest_serialization_and_digest_are_deterministic() -> None:
    spec = scenario(FaultType.PACKET_LOSS)

    first = manifest_yaml(spec)
    second = manifest_yaml(spec)

    assert first == second
    assert manifest_digest(first) == manifest_digest(second)
