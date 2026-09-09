"""Unit test for OCI Always Free Terraform definitions."""

from __future__ import annotations

from pathlib import Path


def test_oci_terraform_files_exist() -> None:
    tf_dir = Path("infrastructure/oci/terraform")
    assert (tf_dir / "main.tf").is_file()
    assert (tf_dir / "variables.tf").is_file()
    assert (tf_dir / "outputs.tf").is_file()


def test_oci_terraform_always_free_shape() -> None:
    main_tf = Path("infrastructure/oci/terraform/main.tf").read_text()
    vars_tf = Path("infrastructure/oci/terraform/variables.tf").read_text()

    assert "VM.Standard.A1.Flex" in vars_tf
    assert "always_free_budget_check" in main_tf
    assert "BASIC_CLUSTER" in main_tf
    assert "node_shape_config" in main_tf

