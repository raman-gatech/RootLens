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

    if spec.fault_type in {
        FaultType.POD_KILL,
        FaultType.POD_FAILURE,
        FaultType.CONTAINER_KILL,
    }:
        action = {
            FaultType.POD_KILL: "pod-kill",
            FaultType.POD_FAILURE: "pod-failure",
            FaultType.CONTAINER_KILL: "container-kill",
        }[spec.fault_type]
        pod_spec: dict[str, Any] = {
            "action": action,
            "mode": "one",
            "duration": duration,
            "selector": selector,
        }
        if spec.container_names:
            pod_spec["containerNames"] = list(spec.container_names)
        return {
            **common,
            "kind": "PodChaos",
            "spec": pod_spec,
        }
    if spec.fault_type in {FaultType.CPU_STRESS, FaultType.MEMORY_STRESS}:
        stressors = (
            {"cpu": {"workers": spec.cpu_workers, "load": spec.cpu_load_percent}}
            if spec.fault_type is FaultType.CPU_STRESS
            else {"memory": {"workers": 1, "size": spec.memory_size}}
        )
        return {
            **common,
            "kind": "StressChaos",
            "spec": {
                "mode": "one",
                "duration": duration,
                "selector": selector,
                "stressors": stressors,
            },
        }
    network_faults = {
        FaultType.NETWORK_LATENCY,
        FaultType.PACKET_LOSS,
        FaultType.NETWORK_DUPLICATE,
        FaultType.NETWORK_CORRUPT,
        FaultType.NETWORK_PARTITION,
        FaultType.BANDWIDTH_LIMIT,
    }
    if spec.fault_type in network_faults:
        network_spec: dict[str, Any] = {
            "mode": "all",
            "duration": duration,
            "selector": selector,
        }
        if spec.target_dependency:
            network_spec.update(
                {
                    "direction": "to",
                    "target": {
                        "mode": "all",
                        "selector": {
                            "namespaces": [spec.namespace],
                            "labelSelectors": {
                                "app.kubernetes.io/component": spec.target_dependency
                            },
                        },
                    },
                }
            )
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
        elif spec.fault_type is FaultType.PACKET_LOSS:
            network_spec.update(
                {
                    "action": "loss",
                    "loss": {
                        "loss": str(spec.packet_loss_percent),
                        "correlation": "100",
                    },
                }
            )
        elif spec.fault_type is FaultType.NETWORK_DUPLICATE:
            network_spec.update(
                {
                    "action": "duplicate",
                    "duplicate": {"duplicate": "30", "correlation": "100"},
                }
            )
        elif spec.fault_type is FaultType.NETWORK_CORRUPT:
            network_spec.update(
                {
                    "action": "corrupt",
                    "corrupt": {"corrupt": "10", "correlation": "100"},
                }
            )
        elif spec.fault_type is FaultType.NETWORK_PARTITION:
            network_spec.update({"action": "partition"})
        else:
            network_spec.update(
                {
                    "action": "bandwidth",
                    "bandwidth": {
                        "rate": spec.bandwidth_rate,
                        "limit": 2_097_152,
                        "buffer": 10_000,
                    },
                }
            )
        return {**common, "kind": "NetworkChaos", "spec": network_spec}

    if spec.fault_type in {
        FaultType.HTTP_DELAY,
        FaultType.HTTP_ABORT,
        FaultType.HTTP_REPLACE,
        FaultType.HTTP_PATCH,
    }:
        http_spec: dict[str, Any] = {
            "mode": "all",
            "duration": duration,
            "selector": selector,
            "target": "Response" if spec.fault_type is FaultType.HTTP_REPLACE else "Request",
            "port": spec.http_port,
            "method": spec.http_method,
            "path": spec.http_path,
        }
        if spec.fault_type is FaultType.HTTP_DELAY:
            http_spec["delay"] = f"{spec.latency_ms}ms"
        elif spec.fault_type is FaultType.HTTP_ABORT:
            http_spec["abort"] = True
        elif spec.fault_type is FaultType.HTTP_REPLACE:
            http_spec["replace"] = {"code": 503}
        else:
            http_spec["patch"] = {"headers": [["x-rootlens-test", "patched"]]}
        return {**common, "kind": "HTTPChaos", "spec": http_spec}

    if spec.fault_type in {FaultType.DNS_ERROR, FaultType.DNS_RANDOM}:
        return {
            **common,
            "kind": "DNSChaos",
            "spec": {
                "action": "error" if spec.fault_type is FaultType.DNS_ERROR else "random",
                "mode": "all",
                "duration": duration,
                "patterns": list(spec.dns_patterns),
                "selector": selector,
            },
        }

    if spec.fault_type in {FaultType.IO_LATENCY, FaultType.IO_FAULT}:
        io_spec: dict[str, Any] = {
            "action": "latency" if spec.fault_type is FaultType.IO_LATENCY else "fault",
            "mode": "one",
            "duration": duration,
            "selector": selector,
            "volumePath": spec.io_volume_path,
            "path": spec.io_path,
            "percent": 100,
        }
        if spec.fault_type is FaultType.IO_LATENCY:
            io_spec["delay"] = f"{spec.io_delay_ms}ms"
        else:
            io_spec["errno"] = spec.io_errno
        return {**common, "kind": "IOChaos", "spec": io_spec}

    return {
        **common,
        "kind": "TimeChaos",
        "spec": {
            "mode": "one",
            "duration": duration,
            "selector": selector,
            "timeOffset": spec.time_offset,
            "clockIds": ["CLOCK_REALTIME"],
        },
    }


def manifest_yaml(spec: ExperimentSpec) -> str:
    return yaml.safe_dump(render_manifest(spec), sort_keys=False)


def manifest_digest(manifest: str) -> str:
    return hashlib.sha256(manifest.encode()).hexdigest()
