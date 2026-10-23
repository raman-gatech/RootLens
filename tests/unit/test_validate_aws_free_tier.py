"""Unit tests for AWS Free Tier Terraform configuration and budget validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_aws_free_tier import AwsFreeTierError, validate_aws_free_tier


def test_validate_aws_free_tier_valid() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    validate_aws_free_tier(root)


def test_validate_aws_free_tier_missing_files(tmp_path: Path) -> None:
    with pytest.raises(AwsFreeTierError, match="AWS Terraform files not found"):
        validate_aws_free_tier(tmp_path)
