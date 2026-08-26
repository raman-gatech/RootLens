"""CLI for the blind 100-incident live evaluation."""

import argparse
import asyncio
from pathlib import Path

from evaluation_harness.live import run_live_evaluation
from evaluation_harness.openai_live import DEFAULT_OPENAI_MODEL, OpenAILiveBaselineSuite
from rootlens.investigation.provider import OpenAIResponsesProvider


def _token(path: Path | None) -> str | None:
    if path is None:
        return None
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("token file is empty")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", default="kind-rootlens")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ground-truth-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--settle-seconds", type=float, default=2)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--openai-api-key-file", type=Path)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    openai_suite = None
    if args.openai_api_key_file is not None:
        provider = OpenAIResponsesProvider(
            api_key=_token(args.openai_api_key_file) or "",
            model=args.openai_model,
        )
        openai_suite = OpenAILiveBaselineSuite(provider=provider, model=args.openai_model)

    report = asyncio.run(
        run_live_evaluation(
            context=args.context,
            base_url=args.base_url,
            ground_truth_directory=args.ground_truth_dir,
            repetitions=args.repetitions,
            duration_seconds=args.duration,
            settle_seconds=args.settle_seconds,
            token=_token(args.token_file),
            publish=args.publish,
            openai_suite=openai_suite,
            progress=lambda current, total: print(
                f"Completed blind live incident {current}/{total}", flush=True
            ),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote aggregate-only live report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
