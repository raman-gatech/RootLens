#!/usr/bin/env python3
"""Verify the Milestone 4 Kubernetes application and Chaos Mesh control plane."""

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from experiment_controller.contracts import FaultType  # noqa: E402

KUBECTL = "kubectl"
CONTEXT = "kind-rootlens"


def kubectl(*arguments: str) -> str:
    result = subprocess.run(
        [KUBECTL, "--context", CONTEXT, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def verify() -> None:
    nodes = json.loads(kubectl("get", "nodes", "--output", "json"))
    if not nodes.get("items"):
        raise RuntimeError("kind cluster has no nodes")
    if not all(
        any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in node.get("status", {}).get("conditions", [])
        )
        for node in nodes["items"]
    ):
        raise RuntimeError("not all kind nodes are Ready")
    print(f"PASS kind cluster ({len(nodes['items'])} Ready node)")

    pods = json.loads(kubectl("get", "pods", "--namespace", "otel-demo", "--output", "json"))
    components = {
        pod.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component")
        for pod in pods.get("items", [])
        if pod.get("status", {}).get("phase") == "Running"
    }
    required = {"checkout", "payment", "frontend", "frontend-proxy", "load-generator"}
    missing = required - components
    if missing:
        raise RuntimeError(f"required demo components are not running: {sorted(missing)}")
    print(f"PASS OpenTelemetry Demo ({len(components)} running components)")

    crds = set(kubectl("get", "crds", "--output", "name").splitlines())
    required_crds = {
        "customresourcedefinition.apiextensions.k8s.io/podchaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/stresschaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/networkchaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/httpchaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/dnschaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/iochaos.chaos-mesh.org",
        "customresourcedefinition.apiextensions.k8s.io/timechaos.chaos-mesh.org",
    }
    if not required_crds <= crds:
        raise RuntimeError("one or more required Chaos Mesh CRDs are absent")
    kubectl(
        "rollout",
        "status",
        "deployment/chaos-controller-manager",
        "--namespace",
        "chaos-mesh",
        "--timeout=10s",
    )
    kubectl(
        "rollout",
        "status",
        "daemonset/chaos-daemon",
        "--namespace",
        "chaos-mesh",
        "--timeout=10s",
    )
    print("PASS Chaos Mesh controller and daemon")

    with urlopen("http://localhost:18080", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"frontend returned HTTP {response.status}")
    print("PASS Kubernetes demo frontend")

    for fault in FaultType:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "experiment_controller.cli",
                "validate",
                "--fault",
                fault.value,
                "--duration",
                "10",
            ],
            cwd=PROJECT,
            check=True,
            capture_output=True,
            text=True,
        )
    print(f"PASS all {len(FaultType)} fault manifests passed server-side validation")


def main() -> int:
    try:
        verify()
    except Exception as error:
        print(f"FAIL Milestone 4 Kubernetes verification: {error}", file=sys.stderr)
        return 1
    print("Milestone 4 Kubernetes verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
