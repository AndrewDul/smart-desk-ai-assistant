from __future__ import annotations

import argparse
import pathlib
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect recent benchmark samples and explain why they classify as voice, skill, or llm.",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=10,
        help="How many recent samples to inspect.",
    )
    parser.add_argument(
        "--only-non-llm",
        action="store_true",
        help="Show only samples that are not classified as llm.",
    )
    parser.add_argument(
        "--only-skill",
        action="store_true",
        help="Show only samples classified as skill.",
    )
    return parser.parse_args()


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.runtime.validation.sample_diagnostics_service import (
        TurnBenchmarkSampleDiagnosticsService,
    )

    args = _parse_args()
    service = TurnBenchmarkSampleDiagnosticsService()

    samples = service.tail(
        count=max(1, int(args.tail or 10)),
        only_non_llm=bool(args.only_non_llm),
        only_skill=bool(args.only_skill),
    )

    if not samples:
        print("No matching benchmark samples found.")
        return 0

    for index, sample in enumerate(samples, start=1):
        description = service.describe_sample(sample)
        print(service.render_description(description))
        if index < len(samples):
            print("\n" + "=" * 88 + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())