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
INVOCATION_ATTEMPT_KEY = "vosk_shadow_invocation_attempt"
CAPTURE_WINDOW_SOURCE = "faster_whisper_capture_window_shadow_tap"
CALLBACK_SOURCE = "faster_whisper_callback_shadow_tap"

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


def validate_capture_window_readiness(
    *,
    log_path: Path,
    require_records: bool = False,
    require_readiness_records: bool = False,
    min_readiness_records: int = 1,
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
            readiness_records=0,
            safe_readiness_records=0,
            rejected_readiness_records=0,
            stale_readiness_records=0,
            missing_capture_source_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            phase_counts=Counter(),
            capture_mode_counts=Counter(),
            signal_level_counts=Counter(),
            reason_counts=Counter(),
            rejection_reason_counts=Counter(),
            capture_window_source_frames=[],
            callback_source_frames=[],
            examples=[],
            safety_field_counts={},
            issues=issues,
            require_records=require_records,
            require_readiness_records=require_readiness_records,
            min_readiness_records=min_readiness_records,
        )

    records = 0
    capture_window_records = 0
    readiness_records = 0
    safe_readiness_records = 0
    rejected_readiness_records = 0
    stale_readiness_records = 0
    missing_capture_source_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    phase_counts: Counter[str] = Counter()
    capture_mode_counts: Counter[str] = Counter()
    signal_level_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    rejection_reason_counts: Counter[str] = Counter()

    capture_window_source_frames: list[float] = []
    callback_source_frames: list[float] = []

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

        hook = str(record.get("hook") or "")
        if hook != READINESS_HOOK:
            continue

        capture_window_records += 1

        metadata = _mapping(record.get("metadata"))
        vad_shadow = _mapping(record.get("vad_shadow"))
        attempt = _mapping(metadata.get(INVOCATION_ATTEMPT_KEY))
        if not attempt:
            continue

        readiness_records += 1

        phase = str(record.get("phase") or "unknown")
        capture_mode = str(record.get("capture_mode") or "unknown")
        signal_level = str(vad_shadow.get("pcm_profile_signal_level") or "unknown")
        reason = str(attempt.get("reason") or "")

        phase_counts[phase] += 1
        capture_mode_counts[capture_mode] += 1
        signal_level_counts[signal_level] += 1
        if reason:
            reason_counts[reason] += 1

        frame_source_counts = _mapping(vad_shadow.get("frame_source_counts"))
        capture_source_count = _int_value(frame_source_counts.get(CAPTURE_WINDOW_SOURCE))
        callback_source_count = _int_value(frame_source_counts.get(CALLBACK_SOURCE))

        capture_window_source_frames.append(float(capture_source_count))
        callback_source_frames.append(float(callback_source_count))

        stale_audio_observed = vad_shadow.get("stale_audio_observed") is True
        if stale_audio_observed:
            stale_readiness_records += 1

        if capture_source_count <= 0:
            missing_capture_source_records += 1

        rejection_reasons = _readiness_rejection_reasons(
            attempt=attempt,
            stale_audio_observed=stale_audio_observed,
            capture_source_count=capture_source_count,
        )

        if rejection_reasons:
            rejected_readiness_records += 1
            for rejection_reason in rejection_reasons:
                rejection_reason_counts[rejection_reason] += 1
        else:
            safe_readiness_records += 1

        if len(examples) < 8:
            examples.append(
                {
                    "line": line_number,
                    "turn_id": str(record.get("turn_id") or ""),
                    "phase": phase,
                    "capture_mode": capture_mode,
                    "hook": hook,
                    "attempt_ready": attempt.get("attempt_ready"),
                    "invocation_blocked": attempt.get("invocation_blocked"),
                    "invocation_allowed": attempt.get("invocation_allowed"),
                    "recognition_invocation_performed": (
                        attempt.get("recognition_invocation_performed")
                    ),
                    "recognition_attempted": attempt.get("recognition_attempted"),
                    "action_executed": attempt.get("action_executed"),
                    "runtime_takeover": attempt.get("runtime_takeover"),
                    "reason": reason,
                    "stale_audio_observed": stale_audio_observed,
                    "signal_level": signal_level,
                    "capture_window_source_frames": capture_source_count,
                    "callback_source_frames": callback_source_count,
                    "safe_readiness": not rejection_reasons,
                    "rejection_reasons": rejection_reasons,
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if require_readiness_records and safe_readiness_records < min_readiness_records:
        issues.append("safe_capture_window_readiness_records_missing")

    if rejected_readiness_records > 0:
        issues.append("rejected_capture_window_readiness_records_present")

    if any(count > 0 for count in safety_field_counts.values()):
        issues.append("unsafe_observe_only_fields_present")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        capture_window_records=capture_window_records,
        readiness_records=readiness_records,
        safe_readiness_records=safe_readiness_records,
        rejected_readiness_records=rejected_readiness_records,
        stale_readiness_records=stale_readiness_records,
        missing_capture_source_records=missing_capture_source_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        phase_counts=phase_counts,
        capture_mode_counts=capture_mode_counts,
        signal_level_counts=signal_level_counts,
        reason_counts=reason_counts,
        rejection_reason_counts=rejection_reason_counts,
        capture_window_source_frames=capture_window_source_frames,
        callback_source_frames=callback_source_frames,
        examples=examples,
        safety_field_counts=safety_field_counts,
        issues=issues,
        require_records=require_records,
        require_readiness_records=require_readiness_records,
        min_readiness_records=min_readiness_records,
    )


def _readiness_rejection_reasons(
    *,
    attempt: Mapping[str, Any],
    stale_audio_observed: bool,
    capture_source_count: int,
) -> list[str]:
    reasons: list[str] = []

    required_false_fields = (
        "invocation_allowed",
        "recognition_invocation_performed",
        "recognition_attempted",
        "result_present",
        "raw_pcm_included",
        "action_executed",
        "runtime_takeover",
        "faster_whisper_bypass_enabled",
        "independent_microphone_stream_started",
        "live_command_recognition_enabled",
    )

    if attempt.get("attempt_ready") is not True:
        reasons.append("attempt_ready_must_be_true")

    if attempt.get("invocation_blocked") is not True:
        reasons.append("invocation_blocked_must_be_true")

    for field_name in required_false_fields:
        if attempt.get(field_name) is not False:
            reasons.append(f"{field_name}_must_be_false")

    if stale_audio_observed:
        reasons.append("stale_audio_observed_must_be_false")

    if capture_source_count <= 0:
        reasons.append("capture_window_source_frames_missing")

    return reasons


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    capture_window_records: int,
    readiness_records: int,
    safe_readiness_records: int,
    rejected_readiness_records: int,
    stale_readiness_records: int,
    missing_capture_source_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    phase_counts: Counter[str],
    capture_mode_counts: Counter[str],
    signal_level_counts: Counter[str],
    reason_counts: Counter[str],
    rejection_reason_counts: Counter[str],
    capture_window_source_frames: list[float],
    callback_source_frames: list[float],
    examples: list[dict[str, Any]],
    safety_field_counts: dict[str, int],
    issues: list[str],
    require_records: bool,
    require_readiness_records: bool,
    min_readiness_records: int,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "capture_window_readiness",
        "log_path": str(log_path),
        "records": records,
        "capture_window_records": capture_window_records,
        "readiness_records": readiness_records,
        "safe_readiness_records": safe_readiness_records,
        "rejected_readiness_records": rejected_readiness_records,
        "stale_readiness_records": stale_readiness_records,
        "missing_capture_source_records": missing_capture_source_records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "phase_counts": dict(phase_counts),
        "capture_mode_counts": dict(capture_mode_counts),
        "signal_level_counts": dict(signal_level_counts),
        "reason_counts": dict(reason_counts),
        "rejection_reason_counts": dict(rejection_reason_counts),
        "metrics": {
            "capture_window_source_frames": _summary(capture_window_source_frames),
            "callback_source_frames": _summary(callback_source_frames),
        },
        "examples": examples,
        "decision": _decision(
            safe_readiness_records=safe_readiness_records,
            rejected_readiness_records=rejected_readiness_records,
            stale_readiness_records=stale_readiness_records,
            missing_capture_source_records=missing_capture_source_records,
        ),
        "policy": {
            "readiness_hook": READINESS_HOOK,
            "capture_window_source_required": True,
            "stale_audio_allowed": False,
            "recognition_invocation_allowed": False,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
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
        "required_readiness_records": require_readiness_records,
        "min_readiness_records": min_readiness_records,
        "issues": issues,
    }


def _decision(
    *,
    safe_readiness_records: int,
    rejected_readiness_records: int,
    stale_readiness_records: int,
    missing_capture_source_records: int,
) -> str:
    if rejected_readiness_records > 0:
        return "fix_rejected_capture_window_readiness_before_recognition"
    if stale_readiness_records > 0:
        return "fix_stale_capture_window_readiness_before_recognition"
    if missing_capture_source_records > 0:
        return "fix_missing_capture_window_source_before_recognition"
    if safe_readiness_records <= 0:
        return "capture_window_readiness_missing"
    return "capture_window_readiness_summary_ready"


def _summary(values: list[float]) -> dict[str, Any]:
    clean_values = sorted(value for value in values if value >= 0.0)
    if not clean_values:
        return {
            "count": 0,
            "min": None,
            "avg": None,
            "p50": None,
            "p95": None,
            "max": None,
        }

    return {
        "count": len(clean_values),
        "min": round(clean_values[0], 3),
        "avg": round(sum(clean_values) / len(clean_values), 3),
        "p50": round(_percentile(clean_values, 50), 3),
        "p95": round(_percentile(clean_values, 95), 3),
        "max": round(clean_values[-1], 3),
    }


def _percentile(sorted_values: list[float], percentile: int) -> float:
    if not sorted_values:
        return 0.0
    index = round((percentile / 100.0) * (len(sorted_values) - 1))
    return sorted_values[min(max(index, 0), len(sorted_values) - 1)]


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
            "Summarize capture-window readiness records for the observe-only "
            "Voice Engine v2 Vosk shadow chain."
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
        "--require-readiness-records",
        action="store_true",
        help="Require at least one safe capture-window readiness record.",
    )
    parser.add_argument(
        "--min-readiness-records",
        type=int,
        default=1,
        help="Minimum safe capture-window readiness records required.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_capture_window_readiness(
        log_path=args.log_path,
        require_records=args.require_records,
        require_readiness_records=args.require_readiness_records,
        min_readiness_records=args.min_readiness_records,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
