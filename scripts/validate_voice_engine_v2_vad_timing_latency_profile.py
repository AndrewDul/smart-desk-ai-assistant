#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from math import ceil
from pathlib import Path
import sys
from typing import Any


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")

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


def validate_vad_timing_latency_profile(
    *,
    log_path: Path,
    require_records: bool = False,
    require_capture_window_records: bool = False,
    max_p95_capture_window_publish_to_transcription_ms: float | None = None,
    max_p95_speech_end_to_observe_ms: float | None = None,
    max_stale_audio_ratio: float | None = None,
) -> dict[str, Any]:
    issues: list[str] = []

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=0,
            invalid_json_lines=0,
            invalid_record_lines=0,
            capture_window_records=0,
            post_capture_records=0,
            capture_finished_to_publish_start_ms=[],
            capture_window_publish_to_transcription_finished_ms=[],
            capture_finished_to_vad_observed_ms=[],
            capture_window_publish_to_vad_observed_ms=[],
            latest_speech_end_to_observe_ms=[],
            transcription_elapsed_ms=[],
            vad_observation_duration_ms=[],
            stale_audio_records=0,
            safety_field_counts={},
            issues=issues,
            require_records=require_records,
            require_capture_window_records=require_capture_window_records,
            max_p95_capture_window_publish_to_transcription_ms=(
                max_p95_capture_window_publish_to_transcription_ms
            ),
            max_p95_speech_end_to_observe_ms=max_p95_speech_end_to_observe_ms,
            max_stale_audio_ratio=max_stale_audio_ratio,
        )

    records = 0
    invalid_json_lines = 0
    invalid_record_lines = 0
    capture_window_records = 0
    post_capture_records = 0
    stale_audio_records = 0

    capture_finished_to_publish_start_ms: list[float] = []
    capture_window_publish_to_transcription_finished_ms: list[float] = []
    capture_finished_to_vad_observed_ms: list[float] = []
    capture_window_publish_to_vad_observed_ms: list[float] = []
    latest_speech_end_to_observe_ms: list[float] = []
    transcription_elapsed_ms: list[float] = []
    vad_observation_duration_ms: list[float] = []
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

        hook = str(record.get("hook") or "")
        if hook == "capture_window_pre_transcription":
            capture_window_records += 1
        elif hook == "post_capture":
            post_capture_records += 1

        metadata = _mapping(record.get("metadata"))
        vad_shadow = _mapping(record.get("vad_shadow"))

        capture_window_shadow_tap = _mapping(metadata.get("capture_window_shadow_tap"))
        if not capture_window_shadow_tap:
            capture_window_shadow_tap = _mapping(
                metadata.get("realtime_audio_bus_capture_window_shadow_tap")
            )

        transcript_metadata = _mapping(metadata.get("transcript_metadata"))
        transcript_capture_tap = _mapping(
            transcript_metadata.get("realtime_audio_bus_capture_window_shadow_tap")
        )

        endpointing_candidate = _mapping(metadata.get("endpointing_candidate"))

        _append_number(
            capture_finished_to_publish_start_ms,
            capture_window_shadow_tap.get("capture_finished_to_publish_start_ms"),
        )
        _append_number(
            capture_finished_to_publish_start_ms,
            transcript_capture_tap.get("capture_finished_to_publish_start_ms"),
        )
        _append_number(
            capture_window_publish_to_transcription_finished_ms,
            transcript_capture_tap.get("capture_window_publish_to_transcription_finished_ms"),
        )
        _append_number(
            capture_finished_to_vad_observed_ms,
            endpointing_candidate.get("capture_finished_to_vad_observed_ms"),
        )
        _append_number(
            capture_window_publish_to_vad_observed_ms,
            endpointing_candidate.get("capture_window_publish_to_vad_observed_ms"),
        )
        _append_number(
            latest_speech_end_to_observe_ms,
            vad_shadow.get("latest_speech_end_to_observe_ms"),
        )
        _append_number(
            vad_observation_duration_ms,
            vad_shadow.get("observation_duration_ms"),
        )

        transcription_elapsed_seconds = _number_or_none(
            transcript_metadata.get("transcription_elapsed_seconds")
        )
        if transcription_elapsed_seconds is not None:
            transcription_elapsed_ms.append(transcription_elapsed_seconds * 1000.0)

        if vad_shadow.get("stale_audio_observed") is True:
            stale_audio_records += 1

        for field_name, count in _unsafe_field_counts(record).items():
            safety_field_counts[field_name] = (
                safety_field_counts.get(field_name, 0) + count
            )

    if require_records and records <= 0:
        issues.append("records_missing")

    if require_capture_window_records and capture_window_records <= 0:
        issues.append("capture_window_records_missing")

    if any(count > 0 for count in safety_field_counts.values()):
        issues.append("unsafe_observe_only_fields_present")

    stale_audio_ratio = stale_audio_records / records if records else 0.0

    capture_to_transcription_p95 = _summary(
        capture_window_publish_to_transcription_finished_ms
    )["p95"]
    speech_end_to_observe_p95 = _summary(latest_speech_end_to_observe_ms)["p95"]

    if (
        max_p95_capture_window_publish_to_transcription_ms is not None
        and capture_to_transcription_p95 is not None
        and capture_to_transcription_p95
        > max_p95_capture_window_publish_to_transcription_ms
    ):
        issues.append("p95_capture_window_publish_to_transcription_above_threshold")

    if (
        max_p95_speech_end_to_observe_ms is not None
        and speech_end_to_observe_p95 is not None
        and speech_end_to_observe_p95 > max_p95_speech_end_to_observe_ms
    ):
        issues.append("p95_speech_end_to_observe_above_threshold")

    if max_stale_audio_ratio is not None and stale_audio_ratio > max_stale_audio_ratio:
        issues.append("stale_audio_ratio_above_threshold")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=records,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        capture_window_records=capture_window_records,
        post_capture_records=post_capture_records,
        capture_finished_to_publish_start_ms=capture_finished_to_publish_start_ms,
        capture_window_publish_to_transcription_finished_ms=(
            capture_window_publish_to_transcription_finished_ms
        ),
        capture_finished_to_vad_observed_ms=capture_finished_to_vad_observed_ms,
        capture_window_publish_to_vad_observed_ms=(
            capture_window_publish_to_vad_observed_ms
        ),
        latest_speech_end_to_observe_ms=latest_speech_end_to_observe_ms,
        transcription_elapsed_ms=transcription_elapsed_ms,
        vad_observation_duration_ms=vad_observation_duration_ms,
        stale_audio_records=stale_audio_records,
        safety_field_counts=safety_field_counts,
        issues=issues,
        require_records=require_records,
        require_capture_window_records=require_capture_window_records,
        max_p95_capture_window_publish_to_transcription_ms=(
            max_p95_capture_window_publish_to_transcription_ms
        ),
        max_p95_speech_end_to_observe_ms=max_p95_speech_end_to_observe_ms,
        max_stale_audio_ratio=max_stale_audio_ratio,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    capture_window_records: int,
    post_capture_records: int,
    capture_finished_to_publish_start_ms: list[float],
    capture_window_publish_to_transcription_finished_ms: list[float],
    capture_finished_to_vad_observed_ms: list[float],
    capture_window_publish_to_vad_observed_ms: list[float],
    latest_speech_end_to_observe_ms: list[float],
    transcription_elapsed_ms: list[float],
    vad_observation_duration_ms: list[float],
    stale_audio_records: int,
    safety_field_counts: dict[str, int],
    issues: list[str],
    require_records: bool,
    require_capture_window_records: bool,
    max_p95_capture_window_publish_to_transcription_ms: float | None,
    max_p95_speech_end_to_observe_ms: float | None,
    max_stale_audio_ratio: float | None,
) -> dict[str, Any]:
    stale_audio_ratio = stale_audio_records / records if records else 0.0

    return {
        "accepted": accepted,
        "validator": "vad_timing_latency_profile",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "capture_window_records": capture_window_records,
        "post_capture_records": post_capture_records,
        "stale_audio_records": stale_audio_records,
        "stale_audio_ratio": round(stale_audio_ratio, 6),
        "latency_ms": {
            "capture_finished_to_publish_start": _summary(
                capture_finished_to_publish_start_ms
            ),
            "capture_window_publish_to_transcription_finished": _summary(
                capture_window_publish_to_transcription_finished_ms
            ),
            "capture_finished_to_vad_observed": _summary(
                capture_finished_to_vad_observed_ms
            ),
            "capture_window_publish_to_vad_observed": _summary(
                capture_window_publish_to_vad_observed_ms
            ),
            "latest_speech_end_to_observe": _summary(
                latest_speech_end_to_observe_ms
            ),
            "transcription_elapsed": _summary(transcription_elapsed_ms),
            "vad_observation_duration": _summary(vad_observation_duration_ms),
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": safety_field_counts,
        },
        "thresholds": {
            "max_p95_capture_window_publish_to_transcription_ms": (
                max_p95_capture_window_publish_to_transcription_ms
            ),
            "max_p95_speech_end_to_observe_ms": max_p95_speech_end_to_observe_ms,
            "max_stale_audio_ratio": max_stale_audio_ratio,
        },
        "required_records": require_records,
        "required_capture_window_records": require_capture_window_records,
        "issues": issues,
    }


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
    rank = max(1, ceil((percentile / 100.0) * len(sorted_values)))
    return sorted_values[min(rank - 1, len(sorted_values) - 1)]


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _append_number(values: list[float], raw_value: Any) -> None:
    value = _number_or_none(raw_value)
    if value is not None:
        values.append(value)


def _number_or_none(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0.0 else None


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize observe-only Voice Engine v2 VAD timing latency "
            "from the VAD timing bridge JSONL log."
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
        "--require-capture-window-records",
        action="store_true",
        help="Require at least one capture_window_pre_transcription record.",
    )
    parser.add_argument(
        "--max-p95-capture-window-publish-to-transcription-ms",
        type=float,
        default=None,
        help=(
            "Optional threshold for p95 capture-window publish to "
            "transcription-finished latency."
        ),
    )
    parser.add_argument(
        "--max-p95-speech-end-to-observe-ms",
        type=float,
        default=None,
        help="Optional threshold for p95 speech-end to VAD observe latency.",
    )
    parser.add_argument(
        "--max-stale-audio-ratio",
        type=float,
        default=None,
        help="Optional maximum allowed stale_audio_observed record ratio.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_vad_timing_latency_profile(
        log_path=args.log_path,
        require_records=args.require_records,
        require_capture_window_records=args.require_capture_window_records,
        max_p95_capture_window_publish_to_transcription_ms=(
            args.max_p95_capture_window_publish_to_transcription_ms
        ),
        max_p95_speech_end_to_observe_ms=args.max_p95_speech_end_to_observe_ms,
        max_stale_audio_ratio=args.max_stale_audio_ratio,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
