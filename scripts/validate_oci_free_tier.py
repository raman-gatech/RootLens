#!/usr/bin/env python3
"""Reject OCI infrastructure changes that can escape the Always Free profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class OciFreeTierError(ValueError):
    """Raised when the OCI production foundation violates a cost guardrail."""


def validate(root: Path) -> dict[str, Any]:
    budget_path = root / "infrastructure/oci/free-tier-budget.json"
    terraform_path = root / "infrastructure/oci/terraform/main.tf"
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    terraform = terraform_path.read_text(encoding="utf-8")

    expected = {
        "compute.shape": "VM.Standard.A1.Flex",
        "compute.ocpus": 2,
        "compute.memory_gb": 12,
        "storage.total_boot_and_block_gb": 200,
        "load_balancer.count": 1,
        "load_balancer.minimum_mbps": 10,
        "load_balancer.maximum_mbps": 10,
    }
    for dotted_name, expected_value in expected.items():
        value: Any = budget
        for component in dotted_name.split("."):
            if not isinstance(value, dict) or component not in value:
                raise OciFreeTierError(f"budget is missing {dotted_name}")
            value = value[component]
        if value != expected_value:
            raise OciFreeTierError(f"{dotted_name} must remain {expected_value!r}, found {value!r}")

    required_fragments = (
        'version = "5.5.1"',
        'vcn_create_nat_gateway      = "never"',
        'cluster_type       = "basic"',
        'shape            = "VM.Standard.A1.Flex"',
        'check "always_free_compute_budget"',
        'check "always_free_boot_volume_budget"',
    )
    for fragment in required_fragments:
        if fragment not in terraform:
            raise OciFreeTierError(f"Terraform is missing required guardrail: {fragment}")
    forbidden_fragments = (
        'vcn_create_nat_gateway      = "always"',
        'cluster_type       = "enhanced"',
        'shape            = "VM.Standard.E4.Flex"',
    )
    for fragment in forbidden_fragments:
        if fragment in terraform:
            raise OciFreeTierError(f"Terraform contains billable profile: {fragment}")
    return budget


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    budget = validate(root)
    print(
        "PASS OCI Always Free guardrails: "
        f"{budget['compute']['ocpus']} OCPUs, {budget['compute']['memory_gb']} GB RAM, "
        f"{budget['storage']['total_boot_and_block_gb']} GB storage, "
        f"{budget['load_balancer']['maximum_mbps']} Mbps load balancer"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
