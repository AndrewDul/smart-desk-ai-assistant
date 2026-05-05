#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _path_label(parts: tuple[str, ...]) -> str:
    return ".".join(parts)


def _get(settings: Mapping[str, Any], *parts: str) -> Any:
    value: Any = settings
    for part in parts:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _add_issue(
    issues: list[ValidationIssue],
    *,
    severity: str,
    path: tuple[str, ...],
    message: str,
) -> None:
    issues.append(
        ValidationIssue(
            severity=severity,
            path=_path_label(path),
            message=message,
        )
    )


def _expect_mapping(
    settings: Mapping[str, Any],
    issues: list[ValidationIssue],
    *parts: str,
) -> Mapping[str, Any] | None:
    value = _get(settings, *parts)
    mapped = _mapping(value)
    if mapped is None:
        _add_issue(
            issues,
            severity="error",
            path=parts,
            message="Expected a settings object.",
        )
    return mapped


def _expect_bool(
    settings: Mapping[str, Any],
    issues: list[ValidationIssue],
    *parts: str,
    expected: bool,
    message: str,
) -> None:
    value = _get(settings, *parts)
    if value is not expected:
        _add_issue(
            issues,
            severity="error",
            path=parts,
            message=f"{message} Expected {expected!r}, got {value!r}.",
        )


def _expect_number(
    settings: Mapping[str, Any],
    issues: list[ValidationIssue],
    *parts: str,
    message: str,
) -> float | None:
    value = _get(settings, *parts)
    if not isinstance(value, (int, float)):
        _add_issue(
            issues,
            severity="error",
            path=parts,
            message=f"{message} Expected number, got {value!r}.",
        )
        return None
    return float(value)


def _validate_vision_tracking(settings: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    tracking = _expect_mapping(settings, issues, "vision_tracking")
    if tracking is None:
        return

    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "enabled",
        expected=True,
        message="Vision tracking must be explicitly enabled for dry-run command validation.",
    )

    status_path = _get(settings, "vision_tracking", "status_path")
    if not isinstance(status_path, str) or not status_path.strip():
        _add_issue(
            issues,
            severity="error",
            path=("vision_tracking", "status_path"),
            message="Tracking status path must be a non-empty string.",
        )

    policy = _expect_mapping(settings, issues, "vision_tracking", "policy")
    if policy is not None:
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "policy",
            "enabled",
            expected=True,
            message="Tracking policy must be enabled for dry-run validation.",
        )
        for key in (
            "dead_zone_x",
            "dead_zone_y",
            "pan_gain_degrees",
            "tilt_gain_degrees",
            "max_step_degrees",
            "limit_margin_degrees",
            "base_yaw_assist_edge_threshold",
        ):
            _expect_number(
                settings,
                issues,
                "vision_tracking",
                "policy",
                key,
                message="Tracking policy field is required.",
            )

    executor = _expect_mapping(settings, issues, "vision_tracking", "motion_executor")
    if executor is not None:
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "motion_executor",
            "dry_run",
            expected=True,
            message="Tracking motion executor must remain dry-run.",
        )
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "motion_executor",
            "movement_execution_enabled",
            expected=False,
            message="Global tracking movement execution must remain blocked.",
        )
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "motion_executor",
            "pan_tilt_movement_execution_enabled",
            expected=False,
            message="Pan-tilt execution must remain blocked.",
        )
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "motion_executor",
            "base_yaw_assist_execution_enabled",
            expected=False,
            message="Mobile-base yaw assist execution must remain blocked.",
        )
        _expect_bool(
            settings,
            issues,
            "vision_tracking",
            "motion_executor",
            "base_forward_backward_movement_enabled",
            expected=False,
            message="Forward/backward base movement must remain disabled for camera tracking assist.",
        )


def _validate_pan_tilt_adapter(settings: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    adapter = _expect_mapping(settings, issues, "vision_tracking", "pan_tilt_adapter")
    if adapter is None:
        return

    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "dry_run",
        expected=True,
        message="Pan-tilt adapter must remain dry-run.",
    )
    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "backend_command_execution_enabled",
        expected=False,
        message="Pan-tilt backend command execution must remain blocked.",
    )
    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "runtime_hardware_execution_enabled",
        expected=False,
        message="Runtime pan-tilt hardware execution must remain disabled.",
    )
    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "physical_movement_confirmed",
        expected=False,
        message="Physical movement confirmation must remain false in default settings.",
    )
    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "require_calibrated_limits",
        expected=True,
        message="Pan-tilt adapter must require calibrated limits.",
    )
    _expect_bool(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "require_no_motion_startup_policy",
        expected=True,
        message="Pan-tilt adapter must require no-motion startup policy.",
    )

    max_pan = _expect_number(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "max_allowed_pan_delta_degrees",
        message="Pan-tilt adapter max pan delta is required.",
    )
    max_tilt = _expect_number(
        settings,
        issues,
        "vision_tracking",
        "pan_tilt_adapter",
        "max_allowed_tilt_delta_degrees",
        message="Pan-tilt adapter max tilt delta is required.",
    )

    if max_pan is not None and not (0.0 < max_pan <= 2.0):
        _add_issue(
            issues,
            severity="error",
            path=("vision_tracking", "pan_tilt_adapter", "max_allowed_pan_delta_degrees"),
            message="Pan-tilt adapter max pan delta must be > 0 and <= 2.0 degrees.",
        )

    if max_tilt is not None and not (0.0 < max_tilt <= 2.0):
        _add_issue(
            issues,
            severity="error",
            path=("vision_tracking", "pan_tilt_adapter", "max_allowed_tilt_delta_degrees"),
            message="Pan-tilt adapter max tilt delta must be > 0 and <= 2.0 degrees.",
        )


def _validate_pan_tilt(settings: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    pan_tilt = _expect_mapping(settings, issues, "pan_tilt")
    if pan_tilt is None:
        return

    _expect_bool(
        settings,
        issues,
        "pan_tilt",
        "dry_run",
        expected=True,
        message="Pan-tilt must remain dry-run before hardware smoke validation.",
    )
    _expect_bool(
        settings,
        issues,
        "pan_tilt",
        "hardware_enabled",
        expected=False,
        message="Pan-tilt hardware must remain disabled before hardware smoke validation.",
    )
    _expect_bool(
        settings,
        issues,
        "pan_tilt",
        "motion_enabled",
        expected=False,
        message="Pan-tilt motion must remain disabled before hardware smoke validation.",
    )
    _expect_bool(
        settings,
        issues,
        "pan_tilt",
        "calibration_required",
        expected=True,
        message="Pan-tilt calibration must be required.",
    )
    _expect_bool(
        settings,
        issues,
        "pan_tilt",
        "allow_uncalibrated_motion",
        expected=False,
        message="Uncalibrated pan-tilt movement must not be allowed.",
    )

    startup_policy = _get(settings, "pan_tilt", "startup_policy")
    if startup_policy != "no_motion":
        _add_issue(
            issues,
            severity="error",
            path=("pan_tilt", "startup_policy"),
            message=f"Pan-tilt startup policy must be 'no_motion', got {startup_policy!r}.",
        )

    limits = _expect_mapping(settings, issues, "pan_tilt", "safe_limits")
    if limits is None:
        return

    pan_min = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "pan_min_degrees",
        message="Pan minimum safe limit is required.",
    )
    pan_center = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "pan_center_degrees",
        message="Pan center safe limit is required.",
    )
    pan_max = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "pan_max_degrees",
        message="Pan maximum safe limit is required.",
    )
    tilt_min = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "tilt_min_degrees",
        message="Tilt minimum safe limit is required.",
    )
    tilt_center = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "tilt_center_degrees",
        message="Tilt center safe limit is required.",
    )
    tilt_max = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "safe_limits",
        "tilt_max_degrees",
        message="Tilt maximum safe limit is required.",
    )

    if None not in (pan_min, pan_center, pan_max) and not (pan_min <= pan_center <= pan_max):
        _add_issue(
            issues,
            severity="error",
            path=("pan_tilt", "safe_limits"),
            message="Pan safe limits must satisfy min <= center <= max.",
        )

    if None not in (tilt_min, tilt_center, tilt_max) and not (tilt_min <= tilt_center <= tilt_max):
        _add_issue(
            issues,
            severity="error",
            path=("pan_tilt", "safe_limits"),
            message="Tilt safe limits must satisfy min <= center <= max.",
        )

    max_step = _expect_number(
        settings,
        issues,
        "pan_tilt",
        "max_step_degrees",
        message="Pan-tilt max step is required.",
    )
    if max_step is not None and max_step <= 0.0:
        _add_issue(
            issues,
            severity="error",
            path=("pan_tilt", "max_step_degrees"),
            message="Pan-tilt max step must be greater than zero.",
        )


def _validate_mobility(settings: Mapping[str, Any], issues: list[ValidationIssue]) -> None:
    mobility = _mapping(settings.get("mobility"))
    if mobility is None:
        _add_issue(
            issues,
            severity="warning",
            path=("mobility",),
            message="Mobility config is missing. Base yaw assist execution must remain blocked.",
        )
        return

    safety_stop = mobility.get("safety_stop_enabled")
    if safety_stop is not True:
        _add_issue(
            issues,
            severity="error",
            path=("mobility", "safety_stop_enabled"),
            message="Mobility safety stop must be enabled before any future base yaw assist sprint.",
        )


def validate_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    issues: list[ValidationIssue] = []

    _validate_vision_tracking(settings, issues)
    _validate_pan_tilt_adapter(settings, issues)
    _validate_pan_tilt(settings, issues)
    _validate_mobility(settings, issues)

    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]

    return {
        "ok": not errors,
        "safe_to_execute_physical_motion": False,
        "movement_execution_allowed": False,
        "pan_tilt_execution_allowed": False,
        "base_yaw_assist_execution_allowed": False,
        "base_forward_backward_movement_allowed": False,
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "issues": len(issues),
        },
        "issues": [asdict(issue) for issue in issues],
    }


def load_settings(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate NEXA Vision Runtime tracking execution readiness. "
            "This validator never enables or executes hardware movement."
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
        help="Print machine-readable JSON output.",
    )
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    result = validate_settings(load_settings(settings_path))

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print("NEXA Vision Runtime tracking execution readiness")
        print(f"settings: {settings_path}")
        print(f"ok: {result['ok']}")
        print("safe_to_execute_physical_motion: false")
        print("movement_execution_allowed: false")
        for issue in result["issues"]:
            print(f"- {issue['severity'].upper()} {issue['path']}: {issue['message']}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
