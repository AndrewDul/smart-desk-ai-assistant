#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (  # noqa: E402
    DEFAULT_INVOCATION_PLAN_METADATA_KEY,
    EXPECTED_HOOK,
    VOSK_SHADOW_INVOCATION_PLAN_VERSION,
    validate_vosk_shadow_invocation_plan,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")

UNSAFE_PLAN_FIELDS: tuple[str, ...] = (
    "recognition_invocation_performed",
    "recognition_attempted",
    "recognized",
    "command_matched",
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
)


def validate_vosk_shadow_invocation_plan_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_plan_attached: bool = False,
    require_enabled: bool = False,
    require_ready: bool = False,
    require_capture_window_hook: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []
    record_count = 0
    invalid_json_lines = 0
    invalid_record_lines = 0
    plan_records = 0
    enabled_plan_records = 0
    ready_plan_records = 0
    capture_window_hook_records = 0
    non_capture_window_hook_records = 0
    expected_version_records = 0
    unsafe_plan_records = 0

    unsafe_field_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    version_counts: Counter[str] = Counter()

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=record_count,
            invalid_json_lines=invalid_json_lines,
            invalid_record_lines=invalid_record_lines,
            plan_records=plan_records,
            enabled_plan_records=enabled_plan_records,
            ready_plan_records=ready_plan_records,
            capture_window_hook_records=capture_window_hook_records,
            non_capture_window_hook_records=non_capture_window_hook_records,
            expected_version_records=expected_version_records,
            unsafe_plan_records=unsafe_plan_records,
            reason_counts=reason_counts,
            version_counts=version_counts,
            unsafe_field_counts=unsafe_field_counts,
            issues=issues,
            require_records=require_records,
            require_plan_attached=require_plan_attached,
            require_enabled=require_enabled,
            require_ready=require_ready,
            require_capture_window_hook=require_capture_window_hook,
        )

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid_json_lines += 1
            issues.append(f"line_{line_number}:invalid_json")
            continue

        if not isinstance(record, Mapping):
            invalid_record_lines += 1
            issues.append(f"line_{line_number}:record_must_be_object")
            continue

        record_count += 1

        metadata = _mapping(record.get("metadata"))
        plan = _mapping(metadata.get(DEFAULT_INVOCATION_PLAN_METADATA_KEY))
        if not plan:
            continue

        plan_records += 1

        reason = str(plan.get("reason") or "")
        version = str(plan.get("plan_version") or "")
        if reason:
            reason_counts[reason] += 1
        if version:
            version_counts[version] += 1

        if version == VOSK_SHADOW_INVOCATION_PLAN_VERSION:
            expected_version_records += 1

        if plan.get("enabled") is True:
            enabled_plan_records += 1

        if plan.get("plan_ready") is True:
            ready_plan_records += 1

        record_hook = str(record.get("hook") or "")
        plan_hook = str(plan.get("hook") or "")
        if record_hook == EXPECTED_HOOK and plan_hook == EXPECTED_HOOK:
            capture_window_hook_records += 1
        else:
            non_capture_window_hook_records += 1
            if require_capture_window_hook:
                issues.append(f"line_{line_number}:non_capture_window_hook")

        plan_validation = validate_vosk_shadow_invocation_plan(plan)
        for validation_issue in plan_validation.get("issues", []):
            issues.append(f"line_{line_number}:{validation_issue}")

        unsafe_fields = [
            field_name
            for field_name in UNSAFE_PLAN_FIELDS
            if plan.get(field_name) is not False
        ]
        if unsafe_fields:
            unsafe_plan_records += 1
            for field_name in unsafe_fields:
                unsafe_field_counts[field_name] += 1

    if require_records and record_count <= 0:
        issues.append("records_missing")
    if require_plan_attached and plan_records <= 0:
        issues.append("vosk_shadow_invocation_plan_records_missing")
    if require_enabled and enabled_plan_records <= 0:
        issues.append("enabled_vosk_shadow_invocation_plan_records_missing")
    if require_ready and ready_plan_records <= 0:
        issues.append("ready_vosk_shadow_invocation_plan_records_missing")
    if plan_records > 0 and expected_version_records != plan_records:
        issues.append("unexpected_vosk_shadow_invocation_plan_version")
    if unsafe_plan_records > 0:
        issues.append("unsafe_vosk_shadow_invocation_plan_records_present")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=record_count,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        plan_records=plan_records,
        enabled_plan_records=enabled_plan_records,
        ready_plan_records=ready_plan_records,
        capture_window_hook_records=capture_window_hook_records,
        non_capture_window_hook_records=non_capture_window_hook_records,
        expected_version_records=expected_version_records,
        unsafe_plan_records=unsafe_plan_records,
        reason_counts=reason_counts,
        version_counts=version_counts,
        unsafe_field_counts=unsafe_field_counts,
        issues=issues,
        require_records=require_records,
        require_plan_attached=require_plan_attached,
        require_enabled=require_enabled,
        require_ready=require_ready,
        require_capture_window_hook=require_capture_window_hook,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    plan_records: int,
    enabled_plan_records: int,
    ready_plan_records: int,
    capture_window_hook_records: int,
    non_capture_window_hook_records: int,
    expected_version_records: int,
    unsafe_plan_records: int,
    reason_counts: Counter[str],
    version_counts: Counter[str],
    unsafe_field_counts: Counter[str],
    issues: list[str],
    require_records: bool,
    require_plan_attached: bool,
    require_enabled: bool,
    require_ready: bool,
    require_capture_window_hook: bool,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "vosk_shadow_invocation_plan",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "plan_records": plan_records,
        "enabled_plan_records": enabled_plan_records,
        "ready_plan_records": ready_plan_records,
        "capture_window_hook_records": capture_window_hook_records,
        "non_capture_window_hook_records": non_capture_window_hook_records,
        "expected_version_records": expected_version_records,
        "unsafe_plan_records": unsafe_plan_records,
        "reason_counts": dict(reason_counts),
        "version_counts": dict(version_counts),
        "unsafe_field_counts": dict(unsafe_field_counts),
        "issues": issues,
        "required_records": require_records,
        "required_plan_attached": require_plan_attached,
        "required_enabled": require_enabled,
        "required_ready": require_ready,
        "required_capture_window_hook": require_capture_window_hook,
        "runtime_integration_allowed": False,
        "command_execution_allowed": False,
        "faster_whisper_bypass_allowed": False,
        "independent_microphone_stream_allowed": False,
        "live_command_recognition_allowed": False,
    }


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate observe-only Voice Engine v2 Vosk shadow invocation plan "
            "telemetry from the VAD timing bridge JSONL log."
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
        help="Require at least one telemetry record.",
    )
    parser.add_argument(
        "--require-plan-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_invocation_plan record.",
    )
    parser.add_argument(
        "--require-enabled",
        action="store_true",
        help="Require at least one enabled invocation plan record.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Require at least one plan_ready=true record.",
    )
    parser.add_argument(
        "--allow-non-capture-window-hook",
        action="store_true",
        help="Allow invocation plan records outside capture_window_pre_transcription.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        result = validate_vosk_shadow_invocation_plan_log(
            log_path=args.log_path,
            require_records=args.require_records,
            require_plan_attached=args.require_plan_attached,
            require_enabled=args.require_enabled,
            require_ready=args.require_ready,
            require_capture_window_hook=not args.allow_non_capture_window_hook,
        )
    except OSError as error:
        result = {
            "accepted": False,
            "validator": "vosk_shadow_invocation_plan",
            "error": str(error),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())