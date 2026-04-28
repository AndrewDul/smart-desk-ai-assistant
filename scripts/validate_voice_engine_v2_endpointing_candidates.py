from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")
EXPECTED_PRE_TRANSCRIPTION_HOOK = "capture_window_pre_transcription"
EXPECTED_CAPTURE_WINDOW_SOURCE = "faster_whisper_capture_window_shadow_tap"
EXPECTED_PUBLISH_STAGE = "before_transcription"


def validate_endpointing_candidate_log(
    *,
    log_path: Path,
    require_candidates: bool = False,
    require_candidate_present: bool = False,
    require_endpoint_detected: bool = False,
    require_pre_transcription_hook: bool = False,
    require_capture_window_source: bool = False,
    require_before_transcription_stage: bool = False,
    require_latency_metrics: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []

    total_lines = 0
    valid_json_records = 0
    invalid_json_records = 0

    hook_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    candidate_records = 0
    candidate_present_records = 0
    endpoint_detected_records = 0
    pre_transcription_candidate_records = 0

    candidate_reason_counts: Counter[str] = Counter()
    candidate_source_counts: Counter[str] = Counter()
    candidate_publish_stage_counts: Counter[str] = Counter()
    candidate_signal_level_counts: Counter[str] = Counter()

    max_speech_score: float | None = None
    max_frames_processed: int | None = None
    max_capture_finished_to_vad_observed_ms: float | None = None
    max_capture_window_publish_to_vad_observed_ms: float | None = None

    latency_metric_records = 0

    unsafe_action_records = 0
    unsafe_full_stt_records = 0
    unsafe_takeover_records = 0
    unsafe_candidate_action_records = 0
    unsafe_candidate_full_stt_records = 0
    unsafe_candidate_takeover_records = 0

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

        hook = str(record.get("hook") or "")
        reason = str(record.get("reason") or "")

        if hook:
            hook_counts[hook] += 1
        if reason:
            reason_counts[reason] += 1

        if bool(record.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:top_level_action_executed")
        if bool(record.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:top_level_full_stt_prevented")
        if bool(record.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:top_level_runtime_takeover")

        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue

        candidate = metadata.get("endpointing_candidate")
        if candidate is None:
            continue

        if not isinstance(candidate, dict):
            issues.append(f"line_{line_number}:endpointing_candidate_not_object")
            continue

        candidate_records += 1

        if hook == EXPECTED_PRE_TRANSCRIPTION_HOOK:
            pre_transcription_candidate_records += 1

        candidate_present = bool(candidate.get("candidate_present", False))
        endpoint_detected = bool(candidate.get("endpoint_detected", False))
        candidate_reason = str(candidate.get("reason") or "")
        candidate_source = str(candidate.get("source") or "")
        candidate_publish_stage = str(candidate.get("publish_stage") or "")
        candidate_signal_level = str(candidate.get("pcm_profile_signal_level") or "")

        if candidate_present:
            candidate_present_records += 1
        if endpoint_detected:
            endpoint_detected_records += 1

        if candidate_reason:
            candidate_reason_counts[candidate_reason] += 1
        if candidate_source:
            candidate_source_counts[candidate_source] += 1
        if candidate_publish_stage:
            candidate_publish_stage_counts[candidate_publish_stage] += 1
        if candidate_signal_level:
            candidate_signal_level_counts[candidate_signal_level] += 1

        score = _optional_float(candidate.get("speech_score_max"))
        if score is not None:
            max_speech_score = (
                score if max_speech_score is None else max(max_speech_score, score)
            )

        frames_processed = _positive_int(candidate.get("frames_processed"))
        if frames_processed > 0:
            max_frames_processed = (
                frames_processed
                if max_frames_processed is None
                else max(max_frames_processed, frames_processed)
            )

        capture_finished_to_vad_observed_ms = _optional_float(
            candidate.get("capture_finished_to_vad_observed_ms")
        )
        capture_window_publish_to_vad_observed_ms = _optional_float(
            candidate.get("capture_window_publish_to_vad_observed_ms")
        )

        if (
            capture_finished_to_vad_observed_ms is not None
            or capture_window_publish_to_vad_observed_ms is not None
        ):
            latency_metric_records += 1

        if capture_finished_to_vad_observed_ms is not None:
            max_capture_finished_to_vad_observed_ms = (
                capture_finished_to_vad_observed_ms
                if max_capture_finished_to_vad_observed_ms is None
                else max(
                    max_capture_finished_to_vad_observed_ms,
                    capture_finished_to_vad_observed_ms,
                )
            )

        if capture_window_publish_to_vad_observed_ms is not None:
            max_capture_window_publish_to_vad_observed_ms = (
                capture_window_publish_to_vad_observed_ms
                if max_capture_window_publish_to_vad_observed_ms is None
                else max(
                    max_capture_window_publish_to_vad_observed_ms,
                    capture_window_publish_to_vad_observed_ms,
                )
            )

        if bool(candidate.get("action_executed", False)):
            unsafe_candidate_action_records += 1
            issues.append(f"line_{line_number}:candidate_action_executed")
        if bool(candidate.get("full_stt_prevented", False)):
            unsafe_candidate_full_stt_records += 1
            issues.append(f"line_{line_number}:candidate_full_stt_prevented")
        if bool(candidate.get("runtime_takeover", False)):
            unsafe_candidate_takeover_records += 1
            issues.append(f"line_{line_number}:candidate_runtime_takeover")

    if invalid_json_records > 0:
        issues.append("invalid_json_records_present")

    if require_candidates and candidate_records <= 0:
        issues.append("endpointing_candidate_records_missing")

    if require_candidate_present and candidate_present_records <= 0:
        issues.append("endpointing_candidate_present_records_missing")

    if require_endpoint_detected and endpoint_detected_records <= 0:
        issues.append("endpointing_endpoint_detected_records_missing")

    if (
        require_pre_transcription_hook
        and pre_transcription_candidate_records <= 0
    ):
        issues.append("endpointing_pre_transcription_candidate_records_missing")

    if (
        require_capture_window_source
        and candidate_source_counts.get(EXPECTED_CAPTURE_WINDOW_SOURCE, 0) <= 0
    ):
        issues.append("endpointing_capture_window_source_records_missing")

    if (
        require_before_transcription_stage
        and candidate_publish_stage_counts.get(EXPECTED_PUBLISH_STAGE, 0) <= 0
    ):
        issues.append("endpointing_before_transcription_stage_records_missing")

    if require_latency_metrics and latency_metric_records <= 0:
        issues.append("endpointing_latency_metric_records_missing")

    return {
        "accepted": not issues,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "invalid_json_records": invalid_json_records,
        "hook_counts": dict(hook_counts),
        "reason_counts": dict(reason_counts),
        "candidate_records": candidate_records,
        "candidate_present_records": candidate_present_records,
        "endpoint_detected_records": endpoint_detected_records,
        "pre_transcription_candidate_records": pre_transcription_candidate_records,
        "candidate_reason_counts": dict(candidate_reason_counts),
        "candidate_source_counts": dict(candidate_source_counts),
        "candidate_publish_stage_counts": dict(candidate_publish_stage_counts),
        "candidate_signal_level_counts": dict(candidate_signal_level_counts),
        "max_speech_score": max_speech_score,
        "max_frames_processed": max_frames_processed,
        "latency_metric_records": latency_metric_records,
        "max_capture_finished_to_vad_observed_ms": (
            max_capture_finished_to_vad_observed_ms
        ),
        "max_capture_window_publish_to_vad_observed_ms": (
            max_capture_window_publish_to_vad_observed_ms
        ),
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "unsafe_candidate_action_records": unsafe_candidate_action_records,
        "unsafe_candidate_full_stt_records": unsafe_candidate_full_stt_records,
        "unsafe_candidate_takeover_records": unsafe_candidate_takeover_records,
        "required_candidates": require_candidates,
        "required_candidate_present": require_candidate_present,
        "required_endpoint_detected": require_endpoint_detected,
        "required_pre_transcription_hook": require_pre_transcription_hook,
        "required_capture_window_source": require_capture_window_source,
        "required_before_transcription_stage": require_before_transcription_stage,
        "required_latency_metrics": require_latency_metrics,
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
            "Validate Voice Engine v2 pre-transcription VAD endpointing "
            "candidate telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-candidates", action="store_true")
    parser.add_argument("--require-candidate-present", action="store_true")
    parser.add_argument("--require-endpoint-detected", action="store_true")
    parser.add_argument("--require-pre-transcription-hook", action="store_true")
    parser.add_argument("--require-capture-window-source", action="store_true")
    parser.add_argument("--require-before-transcription-stage", action="store_true")
    parser.add_argument("--require-latency-metrics", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_endpointing_candidate_log(
        log_path=args.log_path,
        require_candidates=args.require_candidates,
        require_candidate_present=args.require_candidate_present,
        require_endpoint_detected=args.require_endpoint_detected,
        require_pre_transcription_hook=args.require_pre_transcription_hook,
        require_capture_window_source=args.require_capture_window_source,
        require_before_transcription_stage=args.require_before_transcription_stage,
        require_latency_metrics=args.require_latency_metrics,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())