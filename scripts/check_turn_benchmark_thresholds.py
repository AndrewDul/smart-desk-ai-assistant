from __future__ import annotations

import pathlib
import sys


def _print_metric_lines(metrics: dict[str, object]) -> None:
    if not metrics:
        print("    - no metrics")
        return

    for key in sorted(metrics):
        print(f"    - {key}: {metrics[key]}")


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.runtime.validation import TurnBenchmarkValidationService

    service = TurnBenchmarkValidationService()
    result = service.run()

    print("NeXa turn benchmark validation")
    print(f"- result: {'PASS' if result.ok else 'FAIL'}")
    print(f"- path: {result.path}")
    print(f"- total samples: {result.sample_count}")
    print(f"- window samples: {result.window_sample_count}")
    print(f"- latest turn: {result.latest_turn_id or '-'}")

    print("\nOverall:")
    _print_metric_lines(result.metrics.get("overall", {}))

    if result.segments:
        print("\nSegments:")
        for segment in result.segments:
            print(f"- {segment.label} [{segment.key}] samples={segment.sample_count}")
            _print_metric_lines(segment.metrics)
            for check in segment.checks:
                state = "OK" if check.ok else "FAIL"
                print(
                    f"    [{state}] {check.key} -> actual={check.actual} {check.comparator} expected={check.expected}"
                )
                print(f"        details: {check.details}")

    global_checks = [
        check
        for check in result.checks
        if not any(check.key.startswith(f"{segment.key}.") for segment in result.segments)
    ]
    print("\nGlobal checks:")
    for check in global_checks:
        state = "OK" if check.ok else "FAIL"
        print(
            f"[{state}] {check.key} -> actual={check.actual} {check.comparator} expected={check.expected}"
        )
        print(f"    details: {check.details}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())