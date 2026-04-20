from __future__ import annotations

import argparse
import pathlib
import sys
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show repeatable premium validation capture guidance and live segment progress.",
    )
    parser.add_argument(
        "--stage",
        choices=["voice_skill", "llm_short", "llm_long", "final_gate"],
        default="",
        help="Focus the capture brief on one validation stage.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the benchmark JSON before showing the capture brief.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip benchmark backup when used together with --reset.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Refresh the capture summary continuously while you collect samples on the Raspberry Pi.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Refresh interval in seconds for --watch mode.",
    )
    return parser.parse_args()


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.runtime.validation.capture_service import PremiumValidationCaptureService

    args = _parse_args()
    service = PremiumValidationCaptureService()

    if args.reset:
        result = service.reset_benchmark_store(backup=not args.no_backup)
        print("Benchmark capture store reset")
        print(f"- path: {result.get('path', '-')}")
        if result.get("backup_path"):
            print(f"- backup: {result['backup_path']}")
        print()

    stage_key = args.stage or None

    def _print_snapshot() -> None:
        snapshot = service.build_snapshot(stage_key=stage_key)
        print(service.render_snapshot(snapshot))

    if not args.watch:
        _print_snapshot()
        return 0

    interval = max(0.5, float(args.interval or 2.0))
    last_render = ""
    try:
        while True:
            snapshot = service.build_snapshot(stage_key=stage_key)
            rendered = service.render_snapshot(snapshot)
            if rendered != last_render:
                if last_render:
                    print("\n" + "=" * 88 + "\n")
                print(rendered)
                last_render = rendered
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped capture watch.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())