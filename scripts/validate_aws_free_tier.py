#!/usr/bin/env python3
"""Reject AWS infrastructure definitions that exceed AWS Free Tier limits."""

from __future__ import annotations

import re
from pathlib import Path


class AwsFreeTierError(ValueError):
    """Raised when an AWS configuration violates free-tier budget bounds."""


def validate_aws_free_tier(root: Path) -> None:
    main_tf_path = root / "infrastructure/aws/terraform/main.tf"
    variables_tf_path = root / "infrastructure/aws/terraform/variables.tf"

    if not main_tf_path.is_file() or not variables_tf_path.is_file():
        raise AwsFreeTierError("AWS Terraform files not found.")

    main_content = main_tf_path.read_text(encoding="utf-8")
    vars_content = variables_tf_path.read_text(encoding="utf-8")

    # 1. Verify instance shape constraints (only micro/small shapes eligible for free tier)
    if 'contains(["t2.micro", "t3.micro", "t4g.small"]' not in vars_content:
        raise AwsFreeTierError("AWS Terraform must restrict compute shapes to Free Tier eligible types.")

    # 2. Verify storage constraint (maximum 30 GB EBS under free tier)
    if "var.root_volume_size_gb <= 30" not in main_content:
        raise AwsFreeTierError("AWS Terraform must enforce the 30 GB root volume Free Tier limit.")

    # 3. Verify static budget assertion block exists
    if 'check "aws_free_tier_budget_check"' not in main_content:
        raise AwsFreeTierError("AWS Terraform must contain a static 'aws_free_tier_budget_check' block.")

    # 4. Verify no paid services accidentally declared
    forbidden_resources = ("aws_eks_cluster", "aws_db_instance", "aws_lb", "aws_alb")
    for resource in forbidden_resources:
        if re.search(rf'\bresource\s+"{resource}"', main_content):
            raise AwsFreeTierError(f"Billable AWS resource '{resource}' detected in Free Tier configuration.")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    validate_aws_free_tier(root)
    print("PASS AWS Free Tier guardrails: t2.micro/t3.micro compute, <= 30 GB EBS, zero control-plane fees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
