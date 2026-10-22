"""OCI Always Free infrastructure guardrail tests."""

from pathlib import Path

import pytest

from scripts.validate_oci_free_tier import OciFreeTierError, validate


def test_repository_oci_profile_stays_within_encoded_free_limits() -> None:
    root = Path(__file__).resolve().parents[2]

    budget = validate(root)

    assert budget["compute"]["shape"] == "VM.Standard.A1.Flex"
    assert budget["compute"]["ocpus"] == 2
    assert budget["compute"]["memory_gb"] == 12
    assert budget["load_balancer"]["maximum_mbps"] == 10


def test_billable_nat_gateway_is_rejected(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[2]
    budget_target = tmp_path / "infrastructure/oci/free-tier-budget.json"
    terraform_target = tmp_path / "infrastructure/oci/terraform/main.tf"
    budget_target.parent.mkdir(parents=True)
    terraform_target.parent.mkdir(parents=True)
    budget_target.write_text(
        (source_root / "infrastructure/oci/free-tier-budget.json").read_text(),
        encoding="utf-8",
    )
    terraform = (source_root / "infrastructure/oci/terraform/main.tf").read_text()
    terraform_target.write_text(
        terraform.replace(
            'vcn_create_nat_gateway      = "never"',
            'vcn_create_nat_gateway      = "always"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(OciFreeTierError, match="missing required guardrail"):
        validate(tmp_path)
