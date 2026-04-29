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


DEFAULT_HIGH_BACKLOG_FRAME_THRESHOLD = 32
DEFAULT_HIGH_CURSOR_GAP_THRESHOLD = 32
DEFAULT_MAX_BACKLOG_RATIO = 0.2

CATEGORY_HIGH_SUBSCRIPTION_BACKLOG = "high_subscription_backlog_frames"
CATEGORY_HIGH_CURSOR_GAP = "high_subscription_cursor_gap"
CATEGORY_POST_CAPTURE_CURSOR_BACKLOG = "post_capture_cursor_backlog"
CATEGORY_CAPTURE_WINDOW_CURSOR_BACKLOG = "capture_window_cursor_backlog"
CATEGORY_CALLBACK_ONLY_CURSOR_BACKLOG = "callback_only_cursor_backlog"
CATEGORY_CAPTURE_WINDOW_MIXED_CURSOR_BACKLOG = "capture_window_mixed_cursor_backlog"
CATEGORY_NEAR_SILENT_CURSOR_BACKLOG = "near_silent_cursor_backlog"
CATEGORY_CURSOR_NOT_CAUGHT_UP = "subscription_cursor_not_caught_up"
CATEGORY_CURSOR_NO_ADVANCE = "subscription_cursor_no_advance"

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


def validate_audio_bus_subscription_backlog(
    *,
    log_path: Path,
    require_records: bool = False,
    require_backlog_records: bool = False,
    high_backlog_frame_threshold: int = DEFAULT_HIGH_BACKLOG_FRAME_THRESHOLD,
    high_cursor_gap_threshold: int = DEFAULT_HIGH_CURSOR_GAP_THRESHOLD,
    max_backlog_ratio: float = DEFAULT_MAX_BACKLOG_RATIO,
    fail_on_backlog: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=0,
            backlog_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            hook_counts=Counter(),
            backlog_hook_counts=Counter(),
            category_counts=Counter(),
            frame_source_counts=Counter(),
            backlog_frame_source_counts=Counter(),
            signal_level_counts=Counter(),
            backlog_signal_level_counts=Counter(),
            subscription_backlog_frames=[],
            cursor_gap_before_frames=[],
            cursor_advanced_frames=[],
            cursor_remaining_after_frames=[],
            latest_frame_age_ms=[],
            speech_end_to_observe_ms=[],
            examples=[],
            safety_field_counts={},
            issues=issues,
            require_records=require_records,
            require_backlog_records=require_backlog_records,
            high_backlog_frame_threshold=high_backlog_frame_threshold,
            high_cursor_gap_threshold=high_cursor_gap_threshold,
            max_backlog_ratio=max_backlog_ratio,
            fail_on_backlog=fail_on_backlog,
        )

    records = 0
    backlog_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    hook_counts: Counter[str] = Counter()
    backlog_hook_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    frame_source_counts: Counter[str] = Counter()
    backlog_frame_source_counts: Counter[str] = Counter()
    signal_level_counts: Counter[str] = Counter()
    backlog_signal_level_counts: Counter[str] = Counter()

    subscription_backlog_frames: list[float] = []
    cursor_gap_before_frames: list[float] = []
    cursor_advanced_frames: list[float] = []
    cursor_remaining_after_frames: list[float] = []
    latest_frame_age_ms: list[float] = []
    speech_end_to_observe_ms: list[float] = []

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

        vad_shadow = _mapping(record.get("vad_shadow"))
        signal_level = str(vad_shadow.get("pcm_profile_signal_level") or "unknown")
        signal_level_counts[signal_level] += 1

        source_counts = _mapping(vad_shadow.get("frame_source_counts"))
        for source, count in source_counts.items():
            frame_source_counts[str(source)] += _int_value(count)

        latest_sequence = _int_or_none(vad_shadow.get("audio_bus_latest_sequence"))
        next_before = _int_or_none(vad_shadow.get("subscription_next_sequence_before"))
        next_after = _int_or_none(vad_shadow.get("subscription_next_sequence_after"))
        reported_backlog = _number_or_none(
            vad_shadow.get("subscription_backlog_frames")
        )

        cursor_gap_before = _cursor_gap_before(
            latest_sequence=latest_sequence,
            next_before=next_before,
        )
        cursor_advanced = _cursor_advanced(
            next_before=next_before,
            next_after=next_after,
        )
        cursor_remaining_after = _cursor_remaining_after(
            latest_sequence=latest_sequence,
            next_after=next_after,
        )

        high_reported_backlog = (
            reported_backlog is not None
            and reported_backlog >= high_backlog_frame_threshold
        )
        high_cursor_gap = (
            cursor_gap_before is not None
            and cursor_gap_before >= high_cursor_gap_threshold
        )

        has_backlog = high_reported_backlog or high_cursor_gap
        if not has_backlog:
            continue

        backlog_records += 1
        backlog_hook_counts[hook] += 1
        backlog_signal_level_counts[signal_level] += 1

        for source, count in source_counts.items():
            backlog_frame_source_counts[str(source)] += _int_value(count)

        _append_if_present(subscription_backlog_frames, reported_backlog)
        _append_if_present(cursor_gap_before_frames, cursor_gap_before)
        _append_if_present(cursor_advanced_frames, cursor_advanced)
        _append_if_present(cursor_remaining_after_frames, cursor_remaining_after)
        _append_if_present(latest_frame_age_ms, _number_or_none(vad_shadow.get("last_frame_age_ms")))
        _append_if_present(
            speech_end_to_observe_ms,
            _number_or_none(vad_shadow.get("latest_speech_end_to_observe_ms")),
        )

        if high_reported_backlog:
            category_counts[CATEGORY_HIGH_SUBSCRIPTION_BACKLOG] += 1
        if high_cursor_gap:
            category_counts[CATEGORY_HIGH_CURSOR_GAP] += 1

        if hook == "post_capture":
            category_counts[CATEGORY_POST_CAPTURE_CURSOR_BACKLOG] += 1
        elif hook == "capture_window_pre_transcription":
            category_counts[CATEGORY_CAPTURE_WINDOW_CURSOR_BACKLOG] += 1

        callback_count = _int_value(source_counts.get("faster_whisper_callback_shadow_tap"))
        capture_window_count = _int_value(
            source_counts.get("faster_whisper_capture_window_shadow_tap")
        )

        if callback_count > 0 and capture_window_count <= 0:
            category_counts[CATEGORY_CALLBACK_ONLY_CURSOR_BACKLOG] += 1
        elif callback_count > 0 and capture_window_count > 0:
            category_counts[CATEGORY_CAPTURE_WINDOW_MIXED_CURSOR_BACKLOG] += 1

        if signal_level == "near_silent":
            category_counts[CATEGORY_NEAR_SILENT_CURSOR_BACKLOG] += 1

        if cursor_remaining_after is not None and cursor_remaining_after > 0:
            category_counts[CATEGORY_CURSOR_NOT_CAUGHT_UP] += 1

        if cursor_advanced is not None and cursor_advanced <= 0:
            category_counts[CATEGORY_CURSOR_NO_ADVANCE] += 1

        if len(examples) < 5:
            examples.append(
                {
                    "line": line_number,
                    "hook": hook,
                    "turn_id": str(record.get("turn_id") or ""),
                    "phase": str(record.get("phase") or ""),
                    "capture_mode": str(record.get("capture_mode") or ""),
                    "audio_bus_latest_sequence": latest_sequence,
                    "subscription_next_sequence_before": next_before,
                    "subscription_next_sequence_after": next_after,
                    "subscription_backlog_frames": reported_backlog,
                    "cursor_gap_before_frames": cursor_gap_before,
                    "cursor_advanced_frames": cursor_advanced,
                    "cursor_remaining_after_frames": cursor_remaining_after,
                    "last_frame_age_ms": _number_or_none(
                        vad_shadow.get("last_frame_age_ms")
                    ),
                    "latest_speech_end_to_observe_ms": _number_or_none(
                        vad_shadow.get("latest_speech_end_to_observe_ms")
                    ),
                    "pcm_profile_signal_level": signal_level,
                    "frame_source_counts": dict(source_counts),
                    "stale_audio_observed": bool(
                        vad_shadow.get("stale_audio_observed", False)
                    ),
                    "cadence_diagnostic_reason": str(
                        vad_shadow.get("cadence_diagnostic_reason") or ""
                    ),
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if require_backlog_records and backlog_records <= 0:
        issues.append("audio_bus_subscription_backlog_records_missing")

    if any(count > 0 for count in safety_field_counts.values()):
        issues.append("unsafe_observe_only_fields_present")

    backlog_ratio = backlog_records / records if records else 0.0
    if fail_on_backlog and backlog_ratio > max_backlog_ratio:
        issues.append("audio_bus_subscription_backlog_ratio_above_threshold")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        backlog_records=backlog_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        hook_counts=hook_counts,
        backlog_hook_counts=backlog_hook_counts,
        category_counts=category_counts,
        frame_source_counts=frame_source_counts,
        backlog_frame_source_counts=backlog_frame_source_counts,
        signal_level_counts=signal_level_counts,
        backlog_signal_level_counts=backlog_signal_level_counts,
        subscription_backlog_frames=subscription_backlog_frames,
        cursor_gap_before_frames=cursor_gap_before_frames,
        cursor_advanced_frames=cursor_advanced_frames,
        cursor_remaining_after_frames=cursor_remaining_after_frames,
        latest_frame_age_ms=latest_frame_age_ms,
        speech_end_to_observe_ms=speech_end_to_observe_ms,
        examples=examples,
        safety_field_counts=safety_field_counts,
        issues=issues,
        require_records=require_records,
        require_backlog_records=require_backlog_records,
        high_backlog_frame_threshold=high_backlog_frame_threshold,
        high_cursor_gap_threshold=high_cursor_gap_threshold,
        max_backlog_ratio=max_backlog_ratio,
        fail_on_backlog=fail_on_backlog,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    backlog_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    hook_counts: Counter[str],
    backlog_hook_counts: Counter[str],
    category_counts: Counter[str],
    frame_source_counts: Counter[str],
    backlog_frame_source_counts: Counter[str],
    signal_level_counts: Counter[str],
    backlog_signal_level_counts: Counter[str],
    subscription_backlog_frames: list[float],
    cursor_gap_before_frames: list[float],
    cursor_advanced_frames: list[float],
    cursor_remaining_after_frames: list[float],
    latest_frame_age_ms: list[float],
    speech_end_to_observe_ms: list[float],
    examples: list[dict[str, Any]],
    safety_field_counts: dict[str, int],
    issues: list[str],
    require_records: bool,
    require_backlog_records: bool,
    high_backlog_frame_threshold: int,
    high_cursor_gap_threshold: int,
    max_backlog_ratio: float,
    fail_on_backlog: bool,
) -> dict[str, Any]:
    backlog_ratio = backlog_records / records if records else 0.0

    return {
        "accepted": accepted,
        "validator": "audio_bus_subscription_backlog",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "backlog_records": backlog_records,
        "backlog_ratio": round(backlog_ratio, 6),
        "hook_counts": dict(hook_counts),
        "backlog_hook_counts": dict(backlog_hook_counts),
        "category_counts": dict(category_counts),
        "frame_source_counts": dict(frame_source_counts),
        "backlog_frame_source_counts": dict(backlog_frame_source_counts),
        "signal_level_counts": dict(signal_level_counts),
        "backlog_signal_level_counts": dict(backlog_signal_level_counts),
        "metrics": {
            "subscription_backlog_frames": _summary(subscription_backlog_frames),
            "cursor_gap_before_frames": _summary(cursor_gap_before_frames),
            "cursor_advanced_frames": _summary(cursor_advanced_frames),
            "cursor_remaining_after_frames": _summary(cursor_remaining_after_frames),
            "latest_frame_age_ms": _summary(latest_frame_age_ms),
            "latest_speech_end_to_observe_ms": _summary(speech_end_to_observe_ms),
        },
        "examples": examples,
        "decision": _decision(
            backlog_records=backlog_records,
            backlog_ratio=backlog_ratio,
            max_backlog_ratio=max_backlog_ratio,
            category_counts=category_counts,
        ),
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": safety_field_counts,
        },
        "thresholds": {
            "high_backlog_frame_threshold": high_backlog_frame_threshold,
            "high_cursor_gap_threshold": high_cursor_gap_threshold,
            "max_backlog_ratio": max_backlog_ratio,
        },
        "required_records": require_records,
        "required_backlog_records": require_backlog_records,
        "fail_on_backlog": fail_on_backlog,
        "issues": issues,
    }


def _decision(
    *,
    backlog_records: int,
    backlog_ratio: float,
    max_backlog_ratio: float,
    category_counts: Counter[str],
) -> str:
    if backlog_records <= 0:
        return "no_audio_bus_subscription_backlog_observed"

    if backlog_ratio <= max_backlog_ratio:
        return "audio_bus_subscription_backlog_within_gate"

    if (
        category_counts.get(CATEGORY_POST_CAPTURE_CURSOR_BACKLOG, 0) > 0
        and category_counts.get(CATEGORY_CALLBACK_ONLY_CURSOR_BACKLOG, 0) > 0
    ):
        return "investigate_post_capture_callback_subscription_cursor"

    if category_counts.get(CATEGORY_CURSOR_NOT_CAUGHT_UP, 0) > 0:
        return "investigate_subscription_cursor_not_caught_up"

    if category_counts.get(CATEGORY_CURSOR_NO_ADVANCE, 0) > 0:
        return "investigate_subscription_cursor_no_advance"

    if category_counts.get(CATEGORY_HIGH_CURSOR_GAP, 0) > 0:
        return "investigate_subscription_cursor_gap"

    return "investigate_audio_bus_subscription_backlog"


def _cursor_gap_before(
    *,
    latest_sequence: int | None,
    next_before: int | None,
) -> float | None:
    if latest_sequence is None or next_before is None:
        return None
    return float(max(0, latest_sequence - next_before + 1))


def _cursor_advanced(
    *,
    next_before: int | None,
    next_after: int | None,
) -> float | None:
    if next_before is None or next_after is None:
        return None
    return float(max(0, next_after - next_before))


def _cursor_remaining_after(
    *,
    latest_sequence: int | None,
    next_after: int | None,
) -> float | None:
    if latest_sequence is None or next_after is None:
        return None
    return float(max(0, latest_sequence - next_after + 1))


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


def _number_or_none(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0.0 else None


def _int_or_none(raw_value: Any) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _int_value(raw_value: Any) -> int:
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


def _append_if_present(values: list[float], value: float | None) -> None:
    if value is not None:
        values.append(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose AudioBus subscription cursor backlog in Voice Engine v2 "
            "VAD timing bridge JSONL logs."
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
        "--require-backlog-records",
        action="store_true",
        help="Require at least one audio bus subscription backlog record.",
    )
    parser.add_argument(
        "--high-backlog-frame-threshold",
        type=int,
        default=DEFAULT_HIGH_BACKLOG_FRAME_THRESHOLD,
        help="Frame threshold used to classify high subscription backlog.",
    )
    parser.add_argument(
        "--high-cursor-gap-threshold",
        type=int,
        default=DEFAULT_HIGH_CURSOR_GAP_THRESHOLD,
        help="Frame threshold used to classify high cursor gap.",
    )
    parser.add_argument(
        "--max-backlog-ratio",
        type=float,
        default=DEFAULT_MAX_BACKLOG_RATIO,
        help="Maximum acceptable backlog record ratio.",
    )
    parser.add_argument(
        "--fail-on-backlog",
        action="store_true",
        help="Return non-zero when backlog ratio is above the configured gate.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_audio_bus_subscription_backlog(
        log_path=args.log_path,
        require_records=args.require_records,
        require_backlog_records=args.require_backlog_records,
        high_backlog_frame_threshold=args.high_backlog_frame_threshold,
        high_cursor_gap_threshold=args.high_cursor_gap_threshold,
        max_backlog_ratio=args.max_backlog_ratio,
        fail_on_backlog=args.fail_on_backlog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
