"""Append-only host journal kept outside every RootLens runtime boundary."""

import os
from pathlib import Path

from experiment_controller.contracts import GroundTruthEvent


class GroundTruthJournal:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.path = self.directory / "events.jsonl"

    def append(self, event: GroundTruthEvent) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            payload = (event.model_dump_json() + "\n").encode()
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
