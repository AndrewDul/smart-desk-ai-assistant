#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_vision_tracking_execution_readiness import load_settings, validate_settings


def _as_bool_label(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def _print_check_line(label: str, value: bool, *, expected: bool = True) -> None:
    status = "OK" if bool(value) is expected else "FAIL"
    print(f"[{status}] {label}: {_as_bool_label(value)}")


def _motion_gate_summary(result: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "safe_to_execute_physical_motion": bool(
            result.get("safe_to_execute_physical_motion", False)
        ),
        "movement_execution_allowed": bool(result.get("movement_execution_allowed", False)),
        "pan_tilt_execution_allowed": bool(result.get("pan_tilt_execution_allowed", False)),
        "base_yaw_assist_execution_allowed": bool(
            result.get("base_yaw_assist_execution_allowed", False)
        ),
        "base_forward_backward_movement_allowed": bool(
            result.get("base_forward_backward_movement_allowed", False)
        ),
    }


def print_developer_checklist(
    *,
    settings_path: Path,
    result: Mapping[str, Any],
) -> None:
    summary = dict(result.get("summary", {}) or {})
    issues = list(result.get("issues", []) or [])
    motion = _motion_gate_summary(result)

    print("NEXA Vision Runtime — tracking execution readiness checklist")
    print(f"settings: {settings_path}")
    print()
    _print_check_line("validator passed", bool(result.get("ok", False)), expected=True)
    _print_check_line(
        "physical movement is allowed",
        motion["safe_to_execute_physical_motion"],
        expected=False,
    )
    _print_check_line(
        "global movement execution is allowed",
        motion["movement_execution_allowed"],
        expected=False,
    )
    _print_check_line(
        "pan-tilt execution is allowed",
        motion["pan_tilt_execution_allowed"],
        expected=False,
    )
    _print_check_line(
        "base yaw assist execution is allowed",
        motion["base_yaw_assist_execution_allowed"],
        expected=False,
    )
    _print_check_line(
        "base forward/backward movement is allowed",
        motion["base_forward_backward_movement_allowed"],
        expected=False,
    )
    print()
    print("Safety interpretation:")
    if bool(result.get("ok", False)):
        print("- Config is valid for continued dry-run vision tracking development.")
        print("- Config is NOT a permission to execute physical pan-tilt movement.")
        print("- Config is NOT a permission to rotate or drive the mobile base.")
    else:
        print("- Config is not ready even for the current dry-run tracking stage.")
        print("- Fix all ERROR issues before continuing.")
    print()
    print(
        "Issue summary: "
        f"errors={summary.get('errors', 0)} "
        f"warnings={summary.get('warnings', 0)} "
        f"total={summary.get('issues', len(issues))}"
    )

    if issues:
        print()
        print("Issues:")
        for issue in issues:
            severity = str(issue.get("severity", "unknown")).upper()
            path = str(issue.get("path", "-"))
            message = str(issue.get("message", ""))
            print(f"- {severity} {path}: {message}")


def run_check(*, settings_path: Path, json_output: bool = False) -> int:
    settings = load_settings(settings_path)
    result = validate_settings(settings)

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print_developer_checklist(settings_path=settings_path, result=result)

    return 0 if bool(result.get("ok", False)) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the NEXA Vision Runtime tracking execution readiness checklist. "
            "This command never enables or executes hardware movement."
        )
    )
    parser.add_argument(
        "--settings",
        default="config/settings.json",
        help="Path to settings JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validator result instead of the checklist.",
    )
    args = parser.parse_args(argv)

    return run_check(settings_path=Path(args.settings), json_output=bool(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
