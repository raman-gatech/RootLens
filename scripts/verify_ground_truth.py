#!/usr/bin/env python3
"""Verify a completed experiment journal without printing hidden fault details."""

import argparse
import stat
import sys
from pathlib import Path

from experiment_controller.contracts import GroundTruthEvent


def verify(directory: Path) -> None:
    resolved = directory.resolve()
    journal = resolved / "events.jsonl"
    if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
        raise RuntimeError("ground-truth directory permissions are not 0700")
    if stat.S_IMODE(journal.stat().st_mode) != 0o600:
        raise RuntimeError("ground-truth journal permissions are not 0600")
    events = [
        GroundTruthEvent.model_validate_json(line) for line in journal.read_text().splitlines()
    ]
    if len(events) < 3:
        raise RuntimeError("ground-truth journal does not contain a complete lifecycle")
    experiment_id = events[-1].spec.experiment_id
    lifecycle = [event.event.value for event in events if event.spec.experiment_id == experiment_id]
    if lifecycle != ["planned", "applied", "recovered"]:
        raise RuntimeError(f"latest experiment has incomplete lifecycle: {lifecycle}")
    print(f"PASS isolated lifecycle for experiment {experiment_id}")


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("directory", type=Path)
    arguments = argument_parser.parse_args()
    try:
        verify(arguments.directory)
    except Exception as error:
        print(f"FAIL ground-truth verification: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
