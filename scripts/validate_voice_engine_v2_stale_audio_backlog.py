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
DEFAULT_OLD_FRAME_AGE_MS = 1000.0
DEFAULT_SLOW_SPEECH_END_TO_OBSERVE_MS = 1000.0
DEFAULT_MAX_STALE_AUDIO_RATIO = 0.2

CATEGORY_POST_CAPTURE_STALE = "post_capture_stale_audio"
CATEGORY_CAPTURE_WINDOW_STALE = "capture_window_stale_audio"
CATEGORY_HIGH_SUBSCRIPTION_BACKLOG = "high_subscription_backlog_frames"
CATEGORY_OLD_LATEST_FRAME = "old_latest_frame_age"
CATEGORY_SLOW_SPEECH_END_TO_OBSERVE = "slow_speech_end_to_observe"
CATEGORY_CALLBACK_ONLY_BACKLOG = "callback_only_backlog"
CATEGORY_CAPTURE_WINDOW_MIXED_BACKLOG = "capture_window_mixed_backlog"
CATEGORY_NEAR_SILENT_STALE = "near_silent_stale_audio"
CATEGORY_UNAVAILABLE_SIGNAL_STALE = "unavailable_signal_stale_audio"

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


def validate_stale_audio_backlog(
    *,
    log_path: Path,
    require_records: bool = False,
    require_stale_audio_records: bool = False,
    high_backlog_frame_threshold: int = DEFAULT_HIGH_BACKLOG_FRAME_THRESHOLD,
    old_frame_age_ms: float = DEFAULT_OLD_FRAME_AGE_MS,
    slow_speech_end_to_observe_ms: float = DEFAULT_SLOW_SPEECH_END_TO_OBSERVE_MS,
    max_stale_audio_ratio: float = DEFAULT_MAX_STALE_AUDIO_RATIO,
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
            stale_audio_records=0,
            capture_window_stale_records=0,
            post_capture_stale_records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            hook_counts=Counter(),
            stale_hook_counts=Counter(),
            stale_reason_counts=Counter(),
            category_counts=Counter(),
            frame_source_counts=Counter(),
            stale_frame_source_counts=Counter(),
            signal_level_counts=Counter(),
            stale_signal_level_counts=Counter(),
            stale_subscription_backlog_frames=[],
            stale_latest_frame_age_ms=[],
            stale_speech_end_to_observe_ms=[],
            stale_audio_window_duration_ms=[],
            stale_audio_bus_frame_count=[],
            stale_record_examples=[],
            safety_field_counts={},
            issues=issues,
            require_records=require_records,
            require_stale_audio_records=require_stale_audio_records,
            high_backlog_frame_threshold=high_backlog_frame_threshold,
            old_frame_age_ms=old_frame_age_ms,
            slow_speech_end_to_observe_ms=slow_speech_end_to_observe_ms,
            max_stale_audio_ratio=max_stale_audio_ratio,
            fail_on_backlog=fail_on_backlog,
        )

    records = 0
    stale_audio_records = 0
    capture_window_stale_records = 0
    post_capture_stale_records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0

    hook_counts: Counter[str] = Counter()
    stale_hook_counts: Counter[str] = Counter()
    stale_reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    frame_source_counts: Counter[str] = Counter()
    stale_frame_source_counts: Counter[str] = Counter()
    signal_level_counts: Counter[str] = Counter()
    stale_signal_level_counts: Counter[str] = Counter()

    stale_subscription_backlog_frames: list[float] = []
    stale_latest_frame_age_ms: list[float] = []
    stale_speech_end_to_observe_ms: list[float] = []
    stale_audio_window_duration_ms: list[float] = []
    stale_audio_bus_frame_count: list[float] = []

    stale_record_examples: list[dict[str, Any]] = []
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
        cadence_reason = str(vad_shadow.get("cadence_diagnostic_reason") or "")
        signal_level = str(vad_shadow.get("pcm_profile_signal_level") or "unknown")
        signal_level_counts[signal_level] += 1

        for source, count in _mapping(vad_shadow.get("frame_source_counts")).items():
            frame_source_counts[str(source)] += _int_value(count)

        if vad_shadow.get("stale_audio_observed") is not True:
            continue

        stale_audio_records += 1
        stale_hook_counts[hook] += 1
        if cadence_reason:
            stale_reason_counts[cadence_reason] += 1
        stale_signal_level_counts[signal_level] += 1

        for source, count in _mapping(vad_shadow.get("frame_source_counts")).items():
            stale_frame_source_counts[str(source)] += _int_value(count)

        if hook == "capture_window_pre_transcription":
            capture_window_stale_records += 1
            category_counts[CATEGORY_CAPTURE_WINDOW_STALE] += 1
        elif hook == "post_capture":
            post_capture_stale_records += 1
            category_counts[CATEGORY_POST_CAPTURE_STALE] += 1

        subscription_backlog_frames = _number_or_none(
            vad_shadow.get("subscription_backlog_frames")
        )
        latest_frame_age_ms = _number_or_none(vad_shadow.get("last_frame_age_ms"))
        speech_end_to_observe_ms = _number_or_none(
            vad_shadow.get("latest_speech_end_to_observe_ms")
        )
        audio_window_duration_ms = _number_or_none(
            vad_shadow.get("audio_window_duration_ms")
        )
        audio_bus_frame_count = _number_or_none(vad_shadow.get("audio_bus_frame_count"))

        _append_if_present(stale_subscription_backlog_frames, subscription_backlog_frames)
        _append_if_present(stale_latest_frame_age_ms, latest_frame_age_ms)
        _append_if_present(stale_speech_end_to_observe_ms, speech_end_to_observe_ms)
        _append_if_present(stale_audio_window_duration_ms, audio_window_duration_ms)
        _append_if_present(stale_audio_bus_frame_count, audio_bus_frame_count)

        if (
            subscription_backlog_frames is not None
            and subscription_backlog_frames >= high_backlog_frame_threshold
        ):
            category_counts[CATEGORY_HIGH_SUBSCRIPTION_BACKLOG] += 1

        if latest_frame_age_ms is not None and latest_frame_age_ms >= old_frame_age_ms:
            category_counts[CATEGORY_OLD_LATEST_FRAME] += 1

        if (
            speech_end_to_observe_ms is not None
            and speech_end_to_observe_ms >= slow_speech_end_to_observe_ms
        ):
            category_counts[CATEGORY_SLOW_SPEECH_END_TO_OBSERVE] += 1

        source_counts = _mapping(vad_shadow.get("frame_source_counts"))
        callback_count = _int_value(source_counts.get("faster_whisper_callback_shadow_tap"))
        capture_window_count = _int_value(
            source_counts.get("faster_whisper_capture_window_shadow_tap")
        )
        if callback_count > 0 and capture_window_count <= 0:
            category_counts[CATEGORY_CALLBACK_ONLY_BACKLOG] += 1
        elif callback_count > 0 and capture_window_count > 0:
            category_counts[CATEGORY_CAPTURE_WINDOW_MIXED_BACKLOG] += 1

        if signal_level == "near_silent":
            category_counts[CATEGORY_NEAR_SILENT_STALE] += 1
        elif signal_level == "unavailable":
            category_counts[CATEGORY_UNAVAILABLE_SIGNAL_STALE] += 1

        if len(stale_record_examples) < 5:
            stale_record_examples.append(
                {
                    "line": line_number,
                    "hook": hook,
                    "turn_id": str(record.get("turn_id") or ""),
                    "phase": str(record.get("phase") or ""),
                    "capture_mode": str(record.get("capture_mode") or ""),
                    "cadence_diagnostic_reason": cadence_reason,
                    "subscription_backlog_frames": subscription_backlog_frames,
                    "last_frame_age_ms": latest_frame_age_ms,
                    "latest_speech_end_to_observe_ms": speech_end_to_observe_ms,
                    "audio_window_duration_ms": audio_window_duration_ms,
                    "audio_bus_frame_count": audio_bus_frame_count,
                    "pcm_profile_signal_level": signal_level,
                    "frame_source_counts": dict(source_counts),
                }
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if require_stale_audio_records and stale_audio_records <= 0:
        issues.append("stale_audio_records_missing")

    if any(count > 0 for count in safety_field_counts.values()):
        issues.append("unsafe_observe_only_fields_present")

    stale_audio_ratio = stale_audio_records / records if records else 0.0
    if fail_on_backlog and stale_audio_ratio > max_stale_audio_ratio:
        issues.append("stale_audio_ratio_above_threshold")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        stale_audio_records=stale_audio_records,
        capture_window_stale_records=capture_window_stale_records,
        post_capture_stale_records=post_capture_stale_records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        hook_counts=hook_counts,
        stale_hook_counts=stale_hook_counts,
        stale_reason_counts=stale_reason_counts,
        category_counts=category_counts,
        frame_source_counts=frame_source_counts,
        stale_frame_source_counts=stale_frame_source_counts,
        signal_level_counts=signal_level_counts,
        stale_signal_level_counts=stale_signal_level_counts,
        stale_subscription_backlog_frames=stale_subscription_backlog_frames,
        stale_latest_frame_age_ms=stale_latest_frame_age_ms,
        stale_speech_end_to_observe_ms=stale_speech_end_to_observe_ms,
        stale_audio_window_duration_ms=stale_audio_window_duration_ms,
        stale_audio_bus_frame_count=stale_audio_bus_frame_count,
        stale_record_examples=stale_record_examples,
        safety_field_counts=safety_field_counts,
        issues=issues,
        require_records=require_records,
        require_stale_audio_records=require_stale_audio_records,
        high_backlog_frame_threshold=high_backlog_frame_threshold,
        old_frame_age_ms=old_frame_age_ms,
        slow_speech_end_to_observe_ms=slow_speech_end_to_observe_ms,
        max_stale_audio_ratio=max_stale_audio_ratio,
        fail_on_backlog=fail_on_backlog,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    stale_audio_records: int,
    capture_window_stale_records: int,
    post_capture_stale_records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    hook_counts: Counter[str],
    stale_hook_counts: Counter[str],
    stale_reason_counts: Counter[str],
    category_counts: Counter[str],
    frame_source_counts: Counter[str],
    stale_frame_source_counts: Counter[str],
    signal_level_counts: Counter[str],
    stale_signal_level_counts: Counter[str],
    stale_subscription_backlog_frames: list[float],
    stale_latest_frame_age_ms: list[float],
    stale_speech_end_to_observe_ms: list[float],
    stale_audio_window_duration_ms: list[float],
    stale_audio_bus_frame_count: list[float],
    stale_record_examples: list[dict[str, Any]],
    safety_field_counts: dict[str, int],
    issues: list[str],
    require_records: bool,
    require_stale_audio_records: bool,
    high_backlog_frame_threshold: int,
    old_frame_age_ms: float,
    slow_speech_end_to_observe_ms: float,
    max_stale_audio_ratio: float,
    fail_on_backlog: bool,
) -> dict[str, Any]:
    stale_audio_ratio = stale_audio_records / records if records else 0.0

    return {
        "accepted": accepted,
        "validator": "stale_audio_backlog",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "stale_audio_records": stale_audio_records,
        "stale_audio_ratio": round(stale_audio_ratio, 6),
        "capture_window_stale_records": capture_window_stale_records,
        "post_capture_stale_records": post_capture_stale_records,
        "hook_counts": dict(hook_counts),
        "stale_hook_counts": dict(stale_hook_counts),
        "stale_reason_counts": dict(stale_reason_counts),
        "category_counts": dict(category_counts),
        "frame_source_counts": dict(frame_source_counts),
        "stale_frame_source_counts": dict(stale_frame_source_counts),
        "signal_level_counts": dict(signal_level_counts),
        "stale_signal_level_counts": dict(stale_signal_level_counts),
        "stale_metrics": {
            "subscription_backlog_frames": _summary(
                stale_subscription_backlog_frames
            ),
            "latest_frame_age_ms": _summary(stale_latest_frame_age_ms),
            "latest_speech_end_to_observe_ms": _summary(
                stale_speech_end_to_observe_ms
            ),
            "audio_window_duration_ms": _summary(stale_audio_window_duration_ms),
            "audio_bus_frame_count": _summary(stale_audio_bus_frame_count),
        },
        "examples": stale_record_examples,
        "decision": _decision(
            stale_audio_records=stale_audio_records,
            category_counts=category_counts,
            stale_audio_ratio=stale_audio_ratio,
            max_stale_audio_ratio=max_stale_audio_ratio,
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
            "old_frame_age_ms": old_frame_age_ms,
            "slow_speech_end_to_observe_ms": slow_speech_end_to_observe_ms,
            "max_stale_audio_ratio": max_stale_audio_ratio,
        },
        "required_records": require_records,
        "required_stale_audio_records": require_stale_audio_records,
        "fail_on_backlog": fail_on_backlog,
        "issues": issues,
    }


def _decision(
    *,
    stale_audio_records: int,
    category_counts: Counter[str],
    stale_audio_ratio: float,
    max_stale_audio_ratio: float,
) -> str:
    if stale_audio_records <= 0:
        return "no_stale_audio_backlog_observed"

    if stale_audio_ratio > max_stale_audio_ratio:
        if category_counts.get(CATEGORY_HIGH_SUBSCRIPTION_BACKLOG, 0) > 0:
            return "investigate_audio_bus_subscription_backlog"
        if category_counts.get(CATEGORY_OLD_LATEST_FRAME, 0) > 0:
            return "investigate_stale_audio_frame_age"
        if category_counts.get(CATEGORY_SLOW_SPEECH_END_TO_OBSERVE, 0) > 0:
            return "investigate_speech_end_observation_lag"
        if category_counts.get(CATEGORY_CALLBACK_ONLY_BACKLOG, 0) > 0:
            return "investigate_callback_shadow_tap_backlog"
        return "investigate_stale_audio_backlog"

    return "stale_audio_present_but_within_gate"


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
            "Diagnose stale audio backlog symptoms in Voice Engine v2 VAD "
            "timing bridge JSONL logs."
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
        "--require-stale-audio-records",
        action="store_true",
        help="Require at least one stale_audio_observed record.",
    )
    parser.add_argument(
        "--high-backlog-frame-threshold",
        type=int,
        default=DEFAULT_HIGH_BACKLOG_FRAME_THRESHOLD,
        help="Frame count threshold used to classify high subscription backlog.",
    )
    parser.add_argument(
        "--old-frame-age-ms",
        type=float,
        default=DEFAULT_OLD_FRAME_AGE_MS,
        help="Frame age threshold used to classify stale latest frames.",
    )
    parser.add_argument(
        "--slow-speech-end-to-observe-ms",
        type=float,
        default=DEFAULT_SLOW_SPEECH_END_TO_OBSERVE_MS,
        help="Speech-end-to-observe threshold used to classify slow observation.",
    )
    parser.add_argument(
        "--max-stale-audio-ratio",
        type=float,
        default=DEFAULT_MAX_STALE_AUDIO_RATIO,
        help="Maximum acceptable stale_audio_observed ratio.",
    )
    parser.add_argument(
        "--fail-on-backlog",
        action="store_true",
        help="Return non-zero when stale audio ratio is above the configured gate.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_stale_audio_backlog(
        log_path=args.log_path,
        require_records=args.require_records,
        require_stale_audio_records=args.require_stale_audio_records,
        high_backlog_frame_threshold=args.high_backlog_frame_threshold,
        old_frame_age_ms=args.old_frame_age_ms,
        slow_speech_end_to_observe_ms=args.slow_speech_end_to_observe_ms,
        max_stale_audio_ratio=args.max_stale_audio_ratio,
        fail_on_backlog=args.fail_on_backlog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
