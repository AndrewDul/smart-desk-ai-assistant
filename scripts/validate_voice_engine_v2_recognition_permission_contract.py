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

from scripts.validate_voice_engine_v2_capture_window_readiness import (  # noqa: E402
    DEFAULT_LOG_PATH,
    validate_capture_window_readiness,
)


READINESS_HOOK = "capture_window_pre_transcription"
INVOCATION_ATTEMPT_KEY = "vosk_shadow_invocation_attempt"
RECOGNITION_PREFLIGHT_KEY = "vosk_shadow_recognition_preflight"

READY_BLOCKED_REASON = "recognition_invocation_blocked_by_stage_policy"

UNSAFE_PERMISSION_FIELDS: tuple[str, ...] = (
    "recognition_allowed",
    "recognition_invocation_allowed",
    "recognition_invocation_performed",
    "recognition_attempted",
    "result_present",
    "recognized",
    "command_matched",
    "raw_pcm_included",
    "pcm_retrieval_performed",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
)


def validate_recognition_permission_contract(
    *,
    log_path: Path,
    require_records: bool = False,
    require_permission_contracts: bool = False,
    min_permission_contracts: int = 1,
    fail_on_permission_grant: bool = True,
) -> dict[str, Any]:
    readiness = validate_capture_window_readiness(
        log_path=log_path,
        require_records=require_records,
        require_readiness_records=require_permission_contracts,
        min_readiness_records=min_permission_contracts,
    )

    issues: list[str] = []
    if not bool(readiness.get("accepted", False)):
        issues.append("capture_window_readiness_not_accepted")
        for issue in _string_list(readiness.get("issues")):
            issues.append(f"readiness:{issue}")

    if not log_path.exists():
        if require_records and "log_file_missing" not in issues:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=0,
            permission_contract_records=0,
            blocked_permission_records=0,
            permission_grant_records=0,
            unsafe_permission_records=0,
            missing_preflight_records=0,
            missing_attempt_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            reason_counts=Counter(),
            phase_counts=Counter(),
            capture_mode_counts=Counter(),
            unsafe_field_counts=Counter(),
            examples=[],
            readiness=readiness,
            issues=issues,
            require_records=require_records,
            require_permission_contracts=require_permission_contracts,
            min_permission_contracts=min_permission_contracts,
            fail_on_permission_grant=fail_on_permission_grant,
        )

    records = 0
    permission_contract_records = 0
    blocked_permission_records = 0
    permission_grant_records = 0
    unsafe_permission_records = 0
    missing_preflight_records = 0
    missing_attempt_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    reason_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    capture_mode_counts: Counter[str] = Counter()
    unsafe_field_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

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

        records += 1

        if str(record.get("hook") or "") != READINESS_HOOK:
            continue

        metadata = _mapping(record.get("metadata"))
        preflight = _mapping(metadata.get(RECOGNITION_PREFLIGHT_KEY))
        attempt = _mapping(metadata.get(INVOCATION_ATTEMPT_KEY))

        if not attempt:
            missing_attempt_records += 1
            continue

        if not _attempt_ready_but_blocked(attempt):
            continue

        permission_contract_records += 1
        phase_counts[str(record.get("phase") or "unknown")] += 1
        capture_mode_counts[str(record.get("capture_mode") or "unknown")] += 1

        if not preflight:
            missing_preflight_records += 1

        reason = str(attempt.get("reason") or preflight.get("reason") or "")
        if reason:
            reason_counts[reason] += 1

        unsafe_fields = _unsafe_fields(preflight, attempt)
        if unsafe_fields:
            unsafe_permission_records += 1
            for field_name in unsafe_fields:
                unsafe_field_counts[field_name] += 1

        permission_granted = _permission_granted(preflight, attempt)
        if permission_granted:
            permission_grant_records += 1
        else:
            blocked_permission_records += 1

        if len(examples) < 8:
            examples.append(
                {
                    "line": line_number,
                    "turn_id": str(record.get("turn_id") or ""),
                    "phase": str(record.get("phase") or ""),
                    "capture_mode": str(record.get("capture_mode") or ""),
                    "hook": str(record.get("hook") or ""),
                    "preflight_present": bool(preflight),
                    "attempt_present": bool(attempt),
                    "preflight_ready": preflight.get("preflight_ready"),
                    "attempt_ready": attempt.get("attempt_ready"),
                    "recognition_allowed": _field_value(
                        preflight,
                        attempt,
                        "recognition_allowed",
                    ),
                    "recognition_invocation_allowed": _field_value(
                        preflight,
                        attempt,
                        "recognition_invocation_allowed",
                    ),
                    "recognition_invocation_performed": _field_value(
                        preflight,
                        attempt,
                        "recognition_invocation_performed",
                    ),
                    "recognition_attempted": _field_value(
                        preflight,
                        attempt,
                        "recognition_attempted",
                    ),
                    "result_present": _field_value(preflight, attempt, "result_present"),
                    "action_executed": _field_value(
                        preflight,
                        attempt,
                        "action_executed",
                    ),
                    "runtime_takeover": _field_value(
                        preflight,
                        attempt,
                        "runtime_takeover",
                    ),
                    "reason": reason,
                    "permission_granted": permission_granted,
                    "unsafe_fields": unsafe_fields,
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if (
        require_permission_contracts
        and blocked_permission_records < min_permission_contracts
    ):
        issues.append("blocked_recognition_permission_contracts_missing")

    if missing_preflight_records > 0:
        issues.append("recognition_preflight_missing_for_permission_contract")

    if unsafe_permission_records > 0:
        issues.append("unsafe_recognition_permission_records_present")

    if fail_on_permission_grant and permission_grant_records > 0:
        issues.append("recognition_permission_granted")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        permission_contract_records=permission_contract_records,
        blocked_permission_records=blocked_permission_records,
        permission_grant_records=permission_grant_records,
        unsafe_permission_records=unsafe_permission_records,
        missing_preflight_records=missing_preflight_records,
        missing_attempt_records=missing_attempt_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        reason_counts=reason_counts,
        phase_counts=phase_counts,
        capture_mode_counts=capture_mode_counts,
        unsafe_field_counts=unsafe_field_counts,
        examples=examples,
        readiness=readiness,
        issues=issues,
        require_records=require_records,
        require_permission_contracts=require_permission_contracts,
        min_permission_contracts=min_permission_contracts,
        fail_on_permission_grant=fail_on_permission_grant,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    permission_contract_records: int,
    blocked_permission_records: int,
    permission_grant_records: int,
    unsafe_permission_records: int,
    missing_preflight_records: int,
    missing_attempt_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    reason_counts: Counter[str],
    phase_counts: Counter[str],
    capture_mode_counts: Counter[str],
    unsafe_field_counts: Counter[str],
    examples: list[dict[str, Any]],
    readiness: Mapping[str, Any],
    issues: list[str],
    require_records: bool,
    require_permission_contracts: bool,
    min_permission_contracts: int,
    fail_on_permission_grant: bool,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "recognition_permission_contract",
        "log_path": str(log_path),
        "records": records,
        "permission_contract_records": permission_contract_records,
        "blocked_permission_records": blocked_permission_records,
        "permission_grant_records": permission_grant_records,
        "unsafe_permission_records": unsafe_permission_records,
        "missing_preflight_records": missing_preflight_records,
        "missing_attempt_records": missing_attempt_records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "reason_counts": dict(reason_counts),
        "phase_counts": dict(phase_counts),
        "capture_mode_counts": dict(capture_mode_counts),
        "unsafe_field_counts": dict(unsafe_field_counts),
        "examples": examples,
        "decision": _decision(
            blocked_permission_records=blocked_permission_records,
            permission_grant_records=permission_grant_records,
            unsafe_permission_records=unsafe_permission_records,
            missing_preflight_records=missing_preflight_records,
        ),
        "policy": {
            "recognition_permission_allowed": False,
            "recognition_invocation_allowed": False,
            "recognition_invocation_performed_allowed": False,
            "recognition_attempted_allowed": False,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "raw_pcm_logging_allowed": False,
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": dict(unsafe_field_counts),
        },
        "readiness": readiness,
        "required_records": require_records,
        "required_permission_contracts": require_permission_contracts,
        "min_permission_contracts": min_permission_contracts,
        "fail_on_permission_grant": fail_on_permission_grant,
        "issues": issues,
    }


def _decision(
    *,
    blocked_permission_records: int,
    permission_grant_records: int,
    unsafe_permission_records: int,
    missing_preflight_records: int,
) -> str:
    if permission_grant_records > 0:
        return "reject_recognition_permission_grant_before_runtime_changes"
    if unsafe_permission_records > 0:
        return "fix_unsafe_permission_records_before_runtime_changes"
    if missing_preflight_records > 0:
        return "fix_missing_preflight_before_permission_contract"
    if blocked_permission_records <= 0:
        return "blocked_permission_contract_missing"
    return "recognition_permission_contract_blocked_and_ready"


def _attempt_ready_but_blocked(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt.get("attempt_ready") is True
        and attempt.get("invocation_blocked") is True
        and attempt.get("invocation_allowed") is False
        and attempt.get("recognition_invocation_performed") is False
        and attempt.get("recognition_attempted") is False
        and attempt.get("action_executed") is False
        and attempt.get("runtime_takeover") is False
    )


def _permission_granted(
    preflight: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> bool:
    grant_fields = (
        "recognition_allowed",
        "recognition_invocation_allowed",
        "recognition_invocation_performed",
        "recognition_attempted",
        "result_present",
    )
    return any(_field_value(preflight, attempt, field_name) is True for field_name in grant_fields)


def _unsafe_fields(
    preflight: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> list[str]:
    unsafe_fields: list[str] = []
    for field_name in UNSAFE_PERMISSION_FIELDS:
        if _field_value(preflight, attempt, field_name) is not False:
            unsafe_fields.append(field_name)
    return unsafe_fields


def _field_value(
    preflight: Mapping[str, Any],
    attempt: Mapping[str, Any],
    field_name: str,
) -> Any:
    if field_name in attempt:
        return attempt.get(field_name)
    return preflight.get(field_name)


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item) for item in raw_value]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that capture-window readiness records still keep Vosk "
            "recognition permission blocked before any real recognition invocation."
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
        help="Require at least one JSONL telemetry record.",
    )
    parser.add_argument(
        "--require-permission-contracts",
        action="store_true",
        help="Require blocked recognition permission contracts.",
    )
    parser.add_argument(
        "--min-permission-contracts",
        type=int,
        default=1,
        help="Minimum blocked permission contracts required.",
    )
    parser.add_argument(
        "--allow-permission-grant",
        action="store_true",
        help="Allow recognition permission grant records.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_recognition_permission_contract(
        log_path=args.log_path,
        require_records=args.require_records,
        require_permission_contracts=args.require_permission_contracts,
        min_permission_contracts=args.min_permission_contracts,
        fail_on_permission_grant=not args.allow_permission_grant,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
