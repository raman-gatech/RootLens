"""Command-line boundary for rendering, validating, and running experiments."""

import argparse
import asyncio
from pathlib import Path

from experiment_controller.catalog import catalog, scenario
from experiment_controller.contracts import FaultType
from experiment_controller.controller import ExperimentController
from experiment_controller.ground_truth import GroundTruthJournal
from experiment_controller.kubectl import KubectlRunner
from experiment_controller.manifests import manifest_yaml


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(description=__doc__)
    command_parser.add_argument("command", choices=("catalog", "render", "validate", "run"))
    command_parser.add_argument("--fault", choices=[fault.value for fault in FaultType])
    command_parser.add_argument("--duration", type=int, default=30)
    command_parser.add_argument("--context", default="kind-rootlens")
    command_parser.add_argument("--kubectl", type=Path, default=Path("kubectl"))
    command_parser.add_argument("--ground-truth-dir", type=Path)
    command_parser.add_argument("--confirm", action="store_true")
    return command_parser


async def execute(arguments: argparse.Namespace) -> int:
    if arguments.command == "catalog":
        for item in catalog():
            print(item.fault_type.value)
        return 0
    if arguments.fault is None:
        raise ValueError("--fault is required for render, validate, and run")
    spec = scenario(FaultType(arguments.fault), duration_seconds=arguments.duration)
    if arguments.command == "render":
        print(manifest_yaml(spec), end="")
        return 0

    runner = KubectlRunner(binary=arguments.kubectl, context=arguments.context)
    if arguments.command == "validate":
        await runner.require_target(spec)
        await runner.server_dry_run(manifest_yaml(spec))
        print(f"validated {spec.fault_type.value}")
        return 0

    if not arguments.confirm:
        raise ValueError("run requires --confirm")
    if arguments.ground_truth_dir is None:
        raise ValueError("run requires --ground-truth-dir outside the RootLens runtime")
    controller = ExperimentController(
        runner=runner,
        journal=GroundTruthJournal(arguments.ground_truth_dir),
    )
    receipt = await controller.run(spec)
    print(receipt.model_dump_json())
    return 0


def main() -> int:
    return asyncio.run(execute(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
