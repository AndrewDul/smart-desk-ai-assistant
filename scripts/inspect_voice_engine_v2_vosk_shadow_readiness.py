#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.runtime.voice_engine_v2.vosk_shadow_readiness import (  # noqa: E402
    build_vosk_shadow_readiness_report,
    load_vad_timing_records,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Voice Engine v2 Vosk shadow readiness from VAD timing telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument(
        "--require-records",
        action="store_true",
        help="Fail if no telemetry records were found.",
    )
    parser.add_argument(
        "--require-ready-for-design",
        action="store_true",
        help=(
            "Fail if the telemetry is not ready for the next observe-only "
            "recognizer invocation design step."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    records = load_vad_timing_records(args.log_path)
    report = build_vosk_shadow_readiness_report(records)
    payload = report.to_json_dict()
    payload["validator"] = "vosk_shadow_readiness"
    payload["log_path"] = str(args.log_path)

    if args.require_records and payload["records"] <= 0:
        payload["accepted"] = False
        payload["blockers"] = sorted(
            set([*payload.get("blockers", []), "records_required"])
        )

    if args.require_ready_for_design and not payload[
        "ready_for_observe_only_invocation_design"
    ]:
        payload["accepted"] = False
        payload["blockers"] = sorted(
            set([*payload.get("blockers", []), "ready_for_design_required"])
        )

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bool(payload.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())