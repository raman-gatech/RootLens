"""CLI for aggregate blind replay evaluation."""

import argparse
from pathlib import Path

from evaluation_harness.runner import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 20:
        parser.error("--repetitions must be between 1 and 20")
    report = run_benchmark(repetitions=args.repetitions)
    rendered = report.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Wrote aggregate report to {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
