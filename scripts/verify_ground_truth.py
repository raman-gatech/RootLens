#!/usr/bin/env python3
"""Verify a completed experiment journal without printing hidden fault details."""

import argparse
import stat
import sys
from pathlib import Path

from experiment_controller.contracts import GroundTruthEvent


def verify(directory: Path, *, expected_experiments: int = 1) -> None:
    resolved = directory.resolve()
    journal = resolved / "events.jsonl"
    if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
        raise RuntimeError("ground-truth directory permissions are not 0700")
    if stat.S_IMODE(journal.stat().st_mode) != 0o600:
        raise RuntimeError("ground-truth journal permissions are not 0600")
    events = [
        GroundTruthEvent.model_validate_json(line) for line in journal.read_text().splitlines()
    ]
    experiment_ids = tuple(dict.fromkeys(event.spec.experiment_id for event in events))
    if len(experiment_ids) != expected_experiments:
        raise RuntimeError(
            f"expected {expected_experiments} experiments, found {len(experiment_ids)}"
        )
    expected = ["planned", "applied", "recovered"]
    for experiment_id in experiment_ids:
        lifecycle = [
            event.event.value for event in events if event.spec.experiment_id == experiment_id
        ]
        if lifecycle != expected:
            raise RuntimeError("an experiment has an incomplete lifecycle")
    print(f"PASS {len(experiment_ids)} isolated experiment lifecycles")


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("directory", type=Path)
    argument_parser.add_argument("--expected-experiments", type=int, default=1)
    arguments = argument_parser.parse_args()
    try:
        verify(arguments.directory, expected_experiments=arguments.expected_experiments)
    except Exception as error:
        print(f"FAIL ground-truth verification: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
