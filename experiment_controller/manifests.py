"""Render validated ExperimentSpec instances into Chaos Mesh resources."""

import hashlib
from typing import Any

import yaml

from experiment_controller.contracts import ExperimentSpec, FaultType


def render_manifest(spec: ExperimentSpec) -> dict[str, Any]:
    common = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "metadata": {
            "name": spec.resource_name,
            "namespace": spec.namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "rootlens-experiment-controller",
                "rootlens.io/experiment-id": str(spec.experiment_id),
            },
        },
    }
    selector = {
        "namespaces": [spec.namespace],
        "labelSelectors": {"app.kubernetes.io/component": spec.target_service},
    }
    duration = f"{spec.duration_seconds}s"

    if spec.fault_type is FaultType.POD_KILL:
        return {
            **common,
            "kind": "PodChaos",
            "spec": {
                "action": "pod-kill",
                "mode": "one",
                "duration": duration,
                "selector": selector,
            },
        }
    if spec.fault_type is FaultType.CPU_STRESS:
        return {
            **common,
            "kind": "StressChaos",
            "spec": {
                "mode": "one",
                "duration": duration,
                "selector": selector,
                "stressors": {
                    "cpu": {
                        "workers": spec.cpu_workers,
                        "load": spec.cpu_load_percent,
                    }
                },
            },
        }
    if spec.fault_type in {FaultType.NETWORK_LATENCY, FaultType.PACKET_LOSS}:
        network_spec: dict[str, Any] = {
            "mode": "all",
            "duration": duration,
            "selector": selector,
            "direction": "to",
            "target": {
                "mode": "all",
                "selector": {
                    "namespaces": [spec.namespace],
                    "labelSelectors": {"app.kubernetes.io/component": spec.target_dependency},
                },
            },
        }
        if spec.fault_type is FaultType.NETWORK_LATENCY:
            network_spec.update(
                {
                    "action": "delay",
                    "delay": {
                        "latency": f"{spec.latency_ms}ms",
                        "jitter": f"{spec.jitter_ms}ms",
                        "correlation": "100",
                    },
                }
            )
        else:
            network_spec.update(
                {
                    "action": "loss",
                    "loss": {
                        "loss": str(spec.packet_loss_percent),
                        "correlation": "100",
                    },
                }
            )
        return {**common, "kind": "NetworkChaos", "spec": network_spec}

    return {
        **common,
        "kind": "HTTPChaos",
        "spec": {
            "mode": "all",
            "duration": duration,
            "selector": selector,
            "target": "Request",
            "port": spec.http_port,
            "method": spec.http_method,
            "path": spec.http_path,
            "delay": f"{spec.latency_ms}ms",
        },
    }


def manifest_yaml(spec: ExperimentSpec) -> str:
    return yaml.safe_dump(render_manifest(spec), sort_keys=False)


def manifest_digest(manifest: str) -> str:
    return hashlib.sha256(manifest.encode()).hexdigest()
