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

from scripts.validate_voice_engine_v2_vad_timing_latency_profile import (  # noqa: E402
    DEFAULT_LOG_PATH,
)


READINESS_HOOK = "capture_window_pre_transcription"
DIAGNOSTIC_ONLY_HOOK = "post_capture"
INVOCATION_ATTEMPT_KEY = "vosk_shadow_invocation_attempt"
CAPTURE_WINDOW_SOURCE = "faster_whisper_capture_window_shadow_tap"
CALLBACK_SOURCE = "faster_whisper_callback_shadow_tap"

CATEGORY_CAPTURE_WINDOW_READINESS_CANDIDATE = (
    "capture_window_readiness_candidate"
)
CATEGORY_POST_CAPTURE_DIAGNOSTIC_ONLY = "post_capture_diagnostic_only"
CATEGORY_POST_CAPTURE_CALLBACK_ONLY_BACKLOG = "post_capture_callback_only_backlog"
CATEGORY_CAPTURE_WINDOW_MIXED_SOURCE_READINESS = (
    "capture_window_mixed_source_readiness"
)
CATEGORY_CAPTURE_WINDOW_CAPTURE_SOURCE_PRESENT = (
    "capture_window_capture_source_present"
)
CATEGORY_CAPTURE_WINDOW_STALE_READINESS_REJECTED = (
    "capture_window_stale_readiness_rejected"
)
CATEGORY_NON_CAPTURE_WINDOW_READINESS_REJECTED = (
    "non_capture_window_readiness_rejected"
)

UNSAFE_BOOLEAN_FIELDS: tuple[str, ...] = (
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
    "recognition_invocation_performed",
    "recognition_attempted",
    "result_present",
    "raw_pcm_included",
    "pcm_retrieval_performed",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
)


def validate_vad_timing_cursor_policy(
    *,
    log_path: Path,
    require_records: bool = False,
    require_readiness_candidates: bool = False,
    reject_post_capture_readiness: bool = True,
    reject_stale_readiness: bool = True,
    require_capture_window_source_for_readiness: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=0,
            capture_window_records=0,
            post_capture_records=0,
            readiness_candidate_records=0,
            accepted_readiness_records=0,
            rejected_readiness_records=0,
            post_capture_diagnostic_records=0,
            post_capture_callback_only_backlog_records=0,
            capture_window_stale_readiness_records=0,
            non_capture_window_readiness_records=0,
            capture_window_missing_source_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            hook_counts=Counter(),
            category_counts=Counter(),
            readiness_reason_counts=Counter(),
            rejection_reason_counts=Counter(),
            readiness_signal_level_counts=Counter(),
            diagnostic_signal_level_counts=Counter(),
            readiness_frame_source_counts=Counter(),
            diagnostic_frame_source_counts=Counter(),
            examples=[],
            safety_field_counts={},
            issues=issues,
            require_records=require_records,
            require_readiness_candidates=require_readiness_candidates,
            reject_post_capture_readiness=reject_post_capture_readiness,
            reject_stale_readiness=reject_stale_readiness,
            require_capture_window_source_for_readiness=(
                require_capture_window_source_for_readiness
            ),
        )

    records = 0
    capture_window_records = 0
    post_capture_records = 0
    readiness_candidate_records = 0
    accepted_readiness_records = 0
    rejected_readiness_records = 0
    post_capture_diagnostic_records = 0
    post_capture_callback_only_backlog_records = 0
    capture_window_stale_readiness_records = 0
    non_capture_window_readiness_records = 0
    capture_window_missing_source_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    hook_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    readiness_reason_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()
    readiness_signal_level_counts: Counter[str] = Counter()
    diagnostic_signal_level_counts: Counter[str] = Counter()
    readiness_frame_source_counts: Counter[str] = Counter()
    diagnostic_frame_source_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    safety_field_counts: dict[str, int] = {}

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

        for field_name, count in _unsafe_field_counts(record).items():
            safety_field_counts[field_name] = (
                safety_field_counts.get(field_name, 0) + count
            )

        hook = str(record.get("hook") or "unknown")
        hook_counts[hook] += 1

        if hook == READINESS_HOOK:
            capture_window_records += 1
        elif hook == DIAGNOSTIC_ONLY_HOOK:
            post_capture_records += 1

        vad_shadow = _mapping(record.get("vad_shadow"))
        metadata = _mapping(record.get("metadata"))
        attempt = _mapping(metadata.get(INVOCATION_ATTEMPT_KEY))
        frame_source_counts = _mapping(vad_shadow.get("frame_source_counts"))
        signal_level = str(vad_shadow.get("pcm_profile_signal_level") or "unknown")
        stale_audio_observed = vad_shadow.get("stale_audio_observed") is True

        callback_count = _int_value(frame_source_counts.get(CALLBACK_SOURCE))
        capture_window_count = _int_value(frame_source_counts.get(CAPTURE_WINDOW_SOURCE))

        if hook == DIAGNOSTIC_ONLY_HOOK:
            post_capture_diagnostic_records += 1
            category_counts[CATEGORY_POST_CAPTURE_DIAGNOSTIC_ONLY] += 1
            diagnostic_signal_level_counts[signal_level] += 1
            for source, count in frame_source_counts.items():
                diagnostic_frame_source_counts[str(source)] += _int_value(count)

            if callback_count > 0 and capture_window_count <= 0:
                post_capture_callback_only_backlog_records += 1
                category_counts[CATEGORY_POST_CAPTURE_CALLBACK_ONLY_BACKLOG] += 1

        if not _is_ready_attempt(attempt):
            continue

        readiness_candidate_records += 1
        readiness_signal_level_counts[signal_level] += 1
        readiness_reason_counts[str(attempt.get("reason") or "")] += 1
        for source, count in frame_source_counts.items():
            readiness_frame_source_counts[str(source)] += _int_value(count)

        rejection_reasons: list[str] = []

        if hook != READINESS_HOOK:
            non_capture_window_readiness_records += 1
            category_counts[CATEGORY_NON_CAPTURE_WINDOW_READINESS_REJECTED] += 1
            rejection_reasons.append("readiness_hook_must_be_capture_window")

        if hook == READINESS_HOOK and stale_audio_observed:
            capture_window_stale_readiness_records += 1
            category_counts[CATEGORY_CAPTURE_WINDOW_STALE_READINESS_REJECTED] += 1
            rejection_reasons.append("capture_window_readiness_must_not_be_stale")

        if hook == READINESS_HOOK and capture_window_count <= 0:
            capture_window_missing_source_records += 1
            rejection_reasons.append("capture_window_source_missing_for_readiness")

        if hook == READINESS_HOOK and capture_window_count > 0:
            category_counts[CATEGORY_CAPTURE_WINDOW_CAPTURE_SOURCE_PRESENT] += 1

        if hook == READINESS_HOOK and callback_count > 0 and capture_window_count > 0:
            category_counts[CATEGORY_CAPTURE_WINDOW_MIXED_SOURCE_READINESS] += 1

        if hook == READINESS_HOOK:
            category_counts[CATEGORY_CAPTURE_WINDOW_READINESS_CANDIDATE] += 1

        if rejection_reasons:
            rejected_readiness_records += 1
            for reason in rejection_reasons:
                rejection_reason_counts[reason] += 1
        else:
            accepted_readiness_records += 1

        if len(examples) < 8:
            examples.append(
                {
                    "line": line_number,
                    "hook": hook,
                    "turn_id": str(record.get("turn_id") or ""),
                    "phase": str(record.get("phase") or ""),
                    "capture_mode": str(record.get("capture_mode") or ""),
                    "attempt_ready": attempt.get("attempt_ready"),
                    "invocation_blocked": attempt.get("invocation_blocked"),
                    "invocation_allowed": attempt.get("invocation_allowed"),
                    "reason": str(attempt.get("reason") or ""),
                    "stale_audio_observed": stale_audio_observed,
                    "cadence_diagnostic_reason": str(
                        vad_shadow.get("cadence_diagnostic_reason") or ""
                    ),
                    "pcm_profile_signal_level": signal_level,
                    "frame_source_counts": dict(frame_source_counts),
                    "capture_window_source_count": capture_window_count,
                    "callback_source_count": callback_count,
                    "accepted_as_readiness_candidate": not rejection_reasons,
                    "rejection_reasons": rejection_reasons,
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if require_readiness_candidates and accepted_readiness_records <= 0:
        issues.append("accepted_readiness_candidates_missing")

    if reject_post_capture_readiness and non_capture_window_readiness_records > 0:
        issues.append("non_capture_window_readiness_records_present")

    if reject_stale_readiness and capture_window_stale_readiness_records > 0:
        issues.append("stale_capture_window_readiness_records_present")

    if (
        require_capture_window_source_for_readiness
        and capture_window_missing_source_records > 0
    ):
        issues.append("capture_window_readiness_source_missing")

    if any(count > 0 for count in safety_field_counts.values()):
        issues.append("unsafe_observe_only_fields_present")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        capture_window_records=capture_window_records,
        post_capture_records=post_capture_records,
        readiness_candidate_records=readiness_candidate_records,
        accepted_readiness_records=accepted_readiness_records,
        rejected_readiness_records=rejected_readiness_records,
        post_capture_diagnostic_records=post_capture_diagnostic_records,
        post_capture_callback_only_backlog_records=(
            post_capture_callback_only_backlog_records
        ),
        capture_window_stale_readiness_records=capture_window_stale_readiness_records,
        non_capture_window_readiness_records=non_capture_window_readiness_records,
        capture_window_missing_source_records=capture_window_missing_source_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        hook_counts=hook_counts,
        category_counts=category_counts,
        readiness_reason_counts=readiness_reason_counts,
        rejection_reason_counts=rejection_reason_counts,
        readiness_signal_level_counts=readiness_signal_level_counts,
        diagnostic_signal_level_counts=diagnostic_signal_level_counts,
        readiness_frame_source_counts=readiness_frame_source_counts,
        diagnostic_frame_source_counts=diagnostic_frame_source_counts,
        examples=examples,
        safety_field_counts=safety_field_counts,
        issues=issues,
        require_records=require_records,
        require_readiness_candidates=require_readiness_candidates,
        reject_post_capture_readiness=reject_post_capture_readiness,
        reject_stale_readiness=reject_stale_readiness,
        require_capture_window_source_for_readiness=(
            require_capture_window_source_for_readiness
        ),
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    capture_window_records: int,
    post_capture_records: int,
    readiness_candidate_records: int,
    accepted_readiness_records: int,
    rejected_readiness_records: int,
    post_capture_diagnostic_records: int,
    post_capture_callback_only_backlog_records: int,
    capture_window_stale_readiness_records: int,
    non_capture_window_readiness_records: int,
    capture_window_missing_source_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    hook_counts: Counter[str],
    category_counts: Counter[str],
    readiness_reason_counts: Counter[str],
    rejection_reason_counts: Counter[str],
    readiness_signal_level_counts: Counter[str],
    diagnostic_signal_level_counts: Counter[str],
    readiness_frame_source_counts: Counter[str],
    diagnostic_frame_source_counts: Counter[str],
    examples: list[dict[str, Any]],
    safety_field_counts: dict[str, int],
    issues: list[str],
    require_records: bool,
    require_readiness_candidates: bool,
    reject_post_capture_readiness: bool,
    reject_stale_readiness: bool,
    require_capture_window_source_for_readiness: bool,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "vad_timing_cursor_policy",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "capture_window_records": capture_window_records,
        "post_capture_records": post_capture_records,
        "readiness_candidate_records": readiness_candidate_records,
        "accepted_readiness_records": accepted_readiness_records,
        "rejected_readiness_records": rejected_readiness_records,
        "post_capture_diagnostic_records": post_capture_diagnostic_records,
        "post_capture_callback_only_backlog_records": (
            post_capture_callback_only_backlog_records
        ),
        "capture_window_stale_readiness_records": (
            capture_window_stale_readiness_records
        ),
        "non_capture_window_readiness_records": non_capture_window_readiness_records,
        "capture_window_missing_source_records": (
            capture_window_missing_source_records
        ),
        "hook_counts": dict(hook_counts),
        "category_counts": dict(category_counts),
        "readiness_reason_counts": dict(readiness_reason_counts),
        "rejection_reason_counts": dict(rejection_reason_counts),
        "readiness_signal_level_counts": dict(readiness_signal_level_counts),
        "diagnostic_signal_level_counts": dict(diagnostic_signal_level_counts),
        "readiness_frame_source_counts": dict(readiness_frame_source_counts),
        "diagnostic_frame_source_counts": dict(diagnostic_frame_source_counts),
        "examples": examples,
        "decision": _decision(
            accepted_readiness_records=accepted_readiness_records,
            post_capture_callback_only_backlog_records=(
                post_capture_callback_only_backlog_records
            ),
            non_capture_window_readiness_records=non_capture_window_readiness_records,
            capture_window_stale_readiness_records=(
                capture_window_stale_readiness_records
            ),
        ),
        "policy": {
            "readiness_hook": READINESS_HOOK,
            "diagnostic_only_hook": DIAGNOSTIC_ONLY_HOOK,
            "post_capture_is_readiness_proof": False,
            "stale_capture_window_is_readiness_proof": False,
            "capture_window_source_required_for_readiness": True,
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": safety_field_counts,
        },
        "required_records": require_records,
        "required_readiness_candidates": require_readiness_candidates,
        "reject_post_capture_readiness": reject_post_capture_readiness,
        "reject_stale_readiness": reject_stale_readiness,
        "require_capture_window_source_for_readiness": (
            require_capture_window_source_for_readiness
        ),
        "issues": issues,
    }


def _decision(
    *,
    accepted_readiness_records: int,
    post_capture_callback_only_backlog_records: int,
    non_capture_window_readiness_records: int,
    capture_window_stale_readiness_records: int,
) -> str:
    if non_capture_window_readiness_records > 0:
        return "reject_post_capture_readiness_before_runtime_changes"

    if capture_window_stale_readiness_records > 0:
        return "reject_stale_capture_window_readiness_before_runtime_changes"

    if accepted_readiness_records <= 0:
        return "capture_window_readiness_candidates_missing"

    if post_capture_callback_only_backlog_records > 0:
        return "use_capture_window_readiness_and_keep_post_capture_diagnostic_only"

    return "capture_window_readiness_policy_satisfied"


def _is_ready_attempt(attempt: Mapping[str, Any]) -> bool:
    return (
        attempt.get("attempt_ready") is True
        and attempt.get("invocation_blocked") is True
        and attempt.get("invocation_allowed") is False
        and attempt.get("recognition_invocation_performed") is False
        and attempt.get("recognition_attempted") is False
        and attempt.get("action_executed") is False
        and attempt.get("runtime_takeover") is False
    )


def _unsafe_field_counts(value: Any) -> dict[str, int]:
    counts: dict[str, int] = {}

    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if key in UNSAFE_BOOLEAN_FIELDS and child is True:
                    counts[key] = counts.get(key, 0) + 1
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return counts


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _int_value(raw_value: Any) -> int:
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Voice Engine v2 VAD timing cursor policy: capture-window "
            "records may be readiness candidates, while post-capture callback "
            "backlog remains diagnostic-only."
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
        "--require-readiness-candidates",
        action="store_true",
        help="Require at least one accepted capture-window readiness candidate.",
    )
    parser.add_argument(
        "--allow-post-capture-readiness",
        action="store_true",
        help="Allow readiness candidates outside capture_window_pre_transcription.",
    )
    parser.add_argument(
        "--allow-stale-readiness",
        action="store_true",
        help="Allow stale capture-window readiness candidates.",
    )
    parser.add_argument(
        "--allow-missing-capture-window-source",
        action="store_true",
        help="Allow capture-window readiness candidates without capture-window source frames.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_vad_timing_cursor_policy(
        log_path=args.log_path,
        require_records=args.require_records,
        require_readiness_candidates=args.require_readiness_candidates,
        reject_post_capture_readiness=not args.allow_post_capture_readiness,
        reject_stale_readiness=not args.allow_stale_readiness,
        require_capture_window_source_for_readiness=(
            not args.allow_missing_capture_window_source
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
