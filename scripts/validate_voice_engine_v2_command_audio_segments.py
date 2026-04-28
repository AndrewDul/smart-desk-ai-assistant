from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.runtime.voice_engine_v2.command_audio_segment import (  # noqa: E402
    build_command_audio_segment,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")


def validate_command_audio_segments_log(
    *,
    log_path: Path,
    require_segments: bool = False,
    require_ready_segment: bool = False,
    require_no_rejected_segments: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []

    total_lines = 0
    valid_json_records = 0
    invalid_json_records = 0

    segment_records = 0
    segment_present_records = 0
    rejected_segment_records = 0

    segment_reason_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    publish_stage_counts: Counter[str] = Counter()
    readiness_reason_counts: Counter[str] = Counter()

    max_speech_score: float | None = None
    max_audio_duration_ms: float | None = None
    max_audio_sample_count: int | None = None
    max_published_byte_count: int | None = None
    max_capture_finished_to_vad_observed_ms: float | None = None
    max_capture_window_publish_to_vad_observed_ms: float | None = None

    unsafe_action_records = 0
    unsafe_full_stt_records = 0
    unsafe_takeover_records = 0

    if not log_path.exists():
        return {
            "accepted": False,
            "log_path": str(log_path),
            "issues": [f"log_missing:{log_path}"],
        }

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        total_lines += 1

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as error:
            invalid_json_records += 1
            issues.append(f"line_{line_number}:invalid_json:{error.msg}")
            continue

        valid_json_records += 1

        if not isinstance(record, dict):
            issues.append(f"line_{line_number}:record_not_object")
            continue

        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue

        candidate = metadata.get("endpointing_candidate")
        if not isinstance(candidate, dict):
            continue

        try:
            segment = build_command_audio_segment(record=record)
        except ValueError as error:
            issues.append(f"line_{line_number}:unsafe_segment:{error}")
            continue

        payload = segment.to_json_dict()
        segment_records += 1

        reason = str(payload.get("reason") or "")
        source = str(payload.get("source") or "")
        publish_stage = str(payload.get("publish_stage") or "")
        readiness_reason = str(payload.get("readiness_reason") or "")

        if reason:
            segment_reason_counts[reason] += 1
        if source:
            source_counts[source] += 1
        if publish_stage:
            publish_stage_counts[publish_stage] += 1
        if readiness_reason:
            readiness_reason_counts[readiness_reason] += 1

        if bool(payload.get("segment_present", False)):
            segment_present_records += 1
        else:
            rejected_segment_records += 1

        score = _optional_float(payload.get("speech_score_max"))
        if score is not None:
            max_speech_score = (
                score if max_speech_score is None else max(max_speech_score, score)
            )

        duration_ms = _optional_float(payload.get("audio_duration_ms"))
        if duration_ms is not None:
            max_audio_duration_ms = (
                duration_ms
                if max_audio_duration_ms is None
                else max(max_audio_duration_ms, duration_ms)
            )

        sample_count = _positive_int(payload.get("audio_sample_count"))
        if sample_count > 0:
            max_audio_sample_count = (
                sample_count
                if max_audio_sample_count is None
                else max(max_audio_sample_count, sample_count)
            )

        byte_count = _positive_int(payload.get("published_byte_count"))
        if byte_count > 0:
            max_published_byte_count = (
                byte_count
                if max_published_byte_count is None
                else max(max_published_byte_count, byte_count)
            )

        capture_latency = _optional_float(
            payload.get("capture_finished_to_vad_observed_ms")
        )
        if capture_latency is not None:
            max_capture_finished_to_vad_observed_ms = (
                capture_latency
                if max_capture_finished_to_vad_observed_ms is None
                else max(max_capture_finished_to_vad_observed_ms, capture_latency)
            )

        publish_latency = _optional_float(
            payload.get("capture_window_publish_to_vad_observed_ms")
        )
        if publish_latency is not None:
            max_capture_window_publish_to_vad_observed_ms = (
                publish_latency
                if max_capture_window_publish_to_vad_observed_ms is None
                else max(max_capture_window_publish_to_vad_observed_ms, publish_latency)
            )

        if bool(payload.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:segment_action_executed")
        if bool(payload.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:segment_full_stt_prevented")
        if bool(payload.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:segment_runtime_takeover")

    if invalid_json_records > 0:
        issues.append("invalid_json_records_present")

    if require_segments and segment_records <= 0:
        issues.append("command_audio_segment_records_missing")

    if require_ready_segment and segment_present_records <= 0:
        issues.append("command_audio_ready_segment_records_missing")

    if require_no_rejected_segments and rejected_segment_records > 0:
        issues.append("command_audio_rejected_segment_records_present")

    return {
        "accepted": not issues,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "invalid_json_records": invalid_json_records,
        "segment_records": segment_records,
        "segment_present_records": segment_present_records,
        "rejected_segment_records": rejected_segment_records,
        "segment_reason_counts": dict(segment_reason_counts),
        "source_counts": dict(source_counts),
        "publish_stage_counts": dict(publish_stage_counts),
        "readiness_reason_counts": dict(readiness_reason_counts),
        "max_speech_score": max_speech_score,
        "max_audio_duration_ms": max_audio_duration_ms,
        "max_audio_sample_count": max_audio_sample_count,
        "max_published_byte_count": max_published_byte_count,
        "max_capture_finished_to_vad_observed_ms": (
            max_capture_finished_to_vad_observed_ms
        ),
        "max_capture_window_publish_to_vad_observed_ms": (
            max_capture_window_publish_to_vad_observed_ms
        ),
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "required_segments": require_segments,
        "required_ready_segment": require_ready_segment,
        "required_no_rejected_segments": require_no_rejected_segments,
        "issues": issues,
    }


def _optional_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _positive_int(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Voice Engine v2 command audio segment contracts from "
            "VAD timing bridge telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-segments", action="store_true")
    parser.add_argument("--require-ready-segment", action="store_true")
    parser.add_argument("--require-no-rejected-segments", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_command_audio_segments_log(
        log_path=args.log_path,
        require_segments=args.require_segments,
        require_ready_segment=args.require_ready_segment,
        require_no_rejected_segments=args.require_no_rejected_segments,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())