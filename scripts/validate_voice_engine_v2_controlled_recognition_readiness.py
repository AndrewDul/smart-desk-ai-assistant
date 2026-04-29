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
)
from scripts.validate_voice_engine_v2_recognition_permission_contract import (  # noqa: E402
    validate_recognition_permission_contract,
)


READINESS_HOOK = "capture_window_pre_transcription"
COMMAND_PHASE = "command"
WAKE_COMMAND_CAPTURE_MODE = "wake_command"
INVOCATION_ATTEMPT_KEY = "vosk_shadow_invocation_attempt"
RECOGNITION_PREFLIGHT_KEY = "vosk_shadow_recognition_preflight"
CAPTURE_WINDOW_SOURCE = "faster_whisper_capture_window_shadow_tap"
READY_BLOCKED_REASON = "recognition_invocation_blocked_by_stage_policy"

UNSAFE_FIELDS: tuple[str, ...] = (
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


def validate_controlled_recognition_readiness(
    *,
    log_path: Path,
    require_records: bool = False,
    require_command_candidates: bool = False,
    min_command_candidates: int = 1,
) -> dict[str, Any]:
    permission = validate_recognition_permission_contract(
        log_path=log_path,
        require_records=require_records,
        require_permission_contracts=require_command_candidates,
        min_permission_contracts=min_command_candidates,
        fail_on_permission_grant=True,
    )

    issues: list[str] = []
    if not bool(permission.get("accepted", False)):
        issues.append("recognition_permission_contract_not_accepted")
        for issue in _string_list(permission.get("issues")):
            issues.append(f"permission:{issue}")

    if not log_path.exists():
        if require_records and "log_file_missing" not in issues:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=0,
            command_candidate_records=0,
            follow_up_candidate_records=0,
            other_candidate_records=0,
            safe_command_candidate_records=0,
            rejected_command_candidate_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            phase_counts=Counter(),
            capture_mode_counts=Counter(),
            signal_level_counts=Counter(),
            reason_counts=Counter(),
            rejection_reason_counts=Counter(),
            unsafe_field_counts=Counter(),
            examples=[],
            permission=permission,
            issues=issues,
            require_records=require_records,
            require_command_candidates=require_command_candidates,
            min_command_candidates=min_command_candidates,
        )

    records = 0
    command_candidate_records = 0
    follow_up_candidate_records = 0
    other_candidate_records = 0
    safe_command_candidate_records = 0
    rejected_command_candidate_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    phase_counts: Counter[str] = Counter()
    capture_mode_counts: Counter[str] = Counter()
    signal_level_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
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
        vad_shadow = _mapping(record.get("vad_shadow"))
        preflight = _mapping(metadata.get(RECOGNITION_PREFLIGHT_KEY))
        attempt = _mapping(metadata.get(INVOCATION_ATTEMPT_KEY))

        if not preflight or not attempt:
            continue

        phase = str(record.get("phase") or "unknown")
        capture_mode = str(record.get("capture_mode") or "unknown")
        signal_level = str(vad_shadow.get("pcm_profile_signal_level") or "unknown")
        reason = str(attempt.get("reason") or preflight.get("reason") or "")

        phase_counts[phase] += 1
        capture_mode_counts[capture_mode] += 1
        signal_level_counts[signal_level] += 1
        if reason:
            reason_counts[reason] += 1

        if phase == COMMAND_PHASE and capture_mode == WAKE_COMMAND_CAPTURE_MODE:
            command_candidate_records += 1
        elif phase == "follow_up":
            follow_up_candidate_records += 1
            continue
        else:
            other_candidate_records += 1
            continue

        rejection_reasons = _command_candidate_rejection_reasons(
            vad_shadow=vad_shadow,
            preflight=preflight,
            attempt=attempt,
            reason=reason,
        )

        for field_name in _unsafe_true_fields(preflight, attempt):
            unsafe_field_counts[field_name] += 1

        if rejection_reasons:
            rejected_command_candidate_records += 1
            for rejection_reason in rejection_reasons:
                rejection_reason_counts[rejection_reason] += 1
        else:
            safe_command_candidate_records += 1

        if len(examples) < 8:
            frame_source_counts = _mapping(vad_shadow.get("frame_source_counts"))
            examples.append(
                {
                    "line": line_number,
                    "turn_id": str(record.get("turn_id") or ""),
                    "hook": str(record.get("hook") or ""),
                    "phase": phase,
                    "capture_mode": capture_mode,
                    "signal_level": signal_level,
                    "reason": reason,
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
                    "result_present": _field_value(
                        preflight,
                        attempt,
                        "result_present",
                    ),
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
                    "stale_audio_observed": vad_shadow.get("stale_audio_observed"),
                    "capture_window_source_frames": _int_value(
                        frame_source_counts.get(CAPTURE_WINDOW_SOURCE)
                    ),
                    "safe_command_candidate": not rejection_reasons,
                    "rejection_reasons": rejection_reasons,
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if (
        require_command_candidates
        and safe_command_candidate_records < min_command_candidates
    ):
        issues.append("safe_command_recognition_candidates_missing")

    if rejected_command_candidate_records > 0:
        issues.append("rejected_command_recognition_candidates_present")

    if any(count > 0 for count in unsafe_field_counts.values()):
        issues.append("unsafe_controlled_recognition_candidate_fields_present")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        command_candidate_records=command_candidate_records,
        follow_up_candidate_records=follow_up_candidate_records,
        other_candidate_records=other_candidate_records,
        safe_command_candidate_records=safe_command_candidate_records,
        rejected_command_candidate_records=rejected_command_candidate_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        phase_counts=phase_counts,
        capture_mode_counts=capture_mode_counts,
        signal_level_counts=signal_level_counts,
        reason_counts=reason_counts,
        rejection_reason_counts=rejection_reason_counts,
        unsafe_field_counts=unsafe_field_counts,
        examples=examples,
        permission=permission,
        issues=issues,
        require_records=require_records,
        require_command_candidates=require_command_candidates,
        min_command_candidates=min_command_candidates,
    )


def _command_candidate_rejection_reasons(
    *,
    vad_shadow: Mapping[str, Any],
    preflight: Mapping[str, Any],
    attempt: Mapping[str, Any],
    reason: str,
) -> list[str]:
    reasons: list[str] = []

    if preflight.get("preflight_ready") is not True:
        reasons.append("preflight_ready_must_be_true")

    if attempt.get("attempt_ready") is not True:
        reasons.append("attempt_ready_must_be_true")

    if attempt.get("invocation_blocked") is not True:
        reasons.append("invocation_blocked_must_be_true")

    if reason != READY_BLOCKED_REASON:
        reasons.append("blocked_reason_must_match_stage_policy")

    frame_source_counts = _mapping(vad_shadow.get("frame_source_counts"))
    if _int_value(frame_source_counts.get(CAPTURE_WINDOW_SOURCE)) <= 0:
        reasons.append("capture_window_source_frames_missing")

    if vad_shadow.get("stale_audio_observed") is True:
        reasons.append("stale_audio_observed_must_be_false")

    for field_name in UNSAFE_FIELDS:
        if _field_value(preflight, attempt, field_name) is not False:
            reasons.append(f"{field_name}_must_be_false")

    return reasons


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    command_candidate_records: int,
    follow_up_candidate_records: int,
    other_candidate_records: int,
    safe_command_candidate_records: int,
    rejected_command_candidate_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    phase_counts: Counter[str],
    capture_mode_counts: Counter[str],
    signal_level_counts: Counter[str],
    reason_counts: Counter[str],
    rejection_reason_counts: Counter[str],
    unsafe_field_counts: Counter[str],
    examples: list[dict[str, Any]],
    permission: Mapping[str, Any],
    issues: list[str],
    require_records: bool,
    require_command_candidates: bool,
    min_command_candidates: int,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "controlled_recognition_readiness",
        "log_path": str(log_path),
        "records": records,
        "command_candidate_records": command_candidate_records,
        "follow_up_candidate_records": follow_up_candidate_records,
        "other_candidate_records": other_candidate_records,
        "safe_command_candidate_records": safe_command_candidate_records,
        "rejected_command_candidate_records": rejected_command_candidate_records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "phase_counts": dict(phase_counts),
        "capture_mode_counts": dict(capture_mode_counts),
        "signal_level_counts": dict(signal_level_counts),
        "reason_counts": dict(reason_counts),
        "rejection_reason_counts": dict(rejection_reason_counts),
        "unsafe_field_counts": dict(unsafe_field_counts),
        "examples": examples,
        "decision": _decision(
            safe_command_candidate_records=safe_command_candidate_records,
            rejected_command_candidate_records=rejected_command_candidate_records,
            permission_accepted=bool(permission.get("accepted", False)),
        ),
        "policy": {
            "current_stage_recognition_invocation_allowed": False,
            "current_stage_recognition_attempt_allowed": False,
            "current_stage_command_execution_allowed": False,
            "current_stage_runtime_takeover_allowed": False,
            "future_controlled_observe_only_candidate": True,
            "candidate_hook": READINESS_HOOK,
            "candidate_phase": COMMAND_PHASE,
            "candidate_capture_mode": WAKE_COMMAND_CAPTURE_MODE,
            "follow_up_is_not_command_first_candidate": True,
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": dict(unsafe_field_counts),
        },
        "permission": permission,
        "required_records": require_records,
        "required_command_candidates": require_command_candidates,
        "min_command_candidates": min_command_candidates,
        "issues": issues,
    }


def _decision(
    *,
    safe_command_candidate_records: int,
    rejected_command_candidate_records: int,
    permission_accepted: bool,
) -> str:
    if not permission_accepted:
        return "fix_permission_contract_before_controlled_recognition"
    if rejected_command_candidate_records > 0:
        return "fix_rejected_command_candidates_before_controlled_recognition"
    if safe_command_candidate_records <= 0:
        return "command_candidates_missing_before_controlled_recognition"
    return "future_controlled_recognition_preconditions_ready_but_current_stage_blocked"


def _unsafe_true_fields(
    preflight: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> list[str]:
    fields: list[str] = []
    for field_name in UNSAFE_FIELDS:
        if _field_value(preflight, attempt, field_name) is True:
            fields.append(field_name)
    return fields


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


def _int_value(raw_value: Any) -> int:
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item) for item in raw_value]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate command-only capture-window candidates for a future "
            "controlled observe-only Vosk recognition stage while keeping the "
            "current stage blocked."
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
        "--require-command-candidates",
        action="store_true",
        help="Require safe command/wake_command capture-window candidates.",
    )
    parser.add_argument(
        "--min-command-candidates",
        type=int,
        default=1,
        help="Minimum safe command candidates required.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_controlled_recognition_readiness(
        log_path=args.log_path,
        require_records=args.require_records,
        require_command_candidates=args.require_command_candidates,
        min_command_candidates=args.min_command_candidates,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
