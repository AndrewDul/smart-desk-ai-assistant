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


from modules.runtime.voice_engine_v2.command_recognition_readiness import (
    DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS,
    DEFAULT_MIN_FRAMES_PROCESSED,
    DEFAULT_MIN_SPEECH_SCORE,
    build_command_recognition_readiness,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")


def validate_command_readiness_log(
    *,
    log_path: Path,
    require_readiness_records: bool = False,
    require_ready: bool = False,
    require_no_not_ready: bool = False,
    min_speech_score: float = DEFAULT_MIN_SPEECH_SCORE,
    max_capture_finished_to_vad_observed_ms: (
        float | None
    ) = DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS,
    min_frames_processed: int = DEFAULT_MIN_FRAMES_PROCESSED,
) -> dict[str, Any]:
    issues: list[str] = []

    total_lines = 0
    valid_json_records = 0
    invalid_json_records = 0

    readiness_records = 0
    ready_records = 0
    not_ready_records = 0

    readiness_reason_counts: Counter[str] = Counter()
    hook_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    publish_stage_counts: Counter[str] = Counter()
    candidate_reason_counts: Counter[str] = Counter()

    max_speech_score: float | None = None
    max_frames_processed: int | None = None
    max_capture_finished_to_vad_observed_ms_seen: float | None = None
    max_capture_window_publish_to_vad_observed_ms_seen: float | None = None

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
            readiness = build_command_recognition_readiness(
                record=record,
                min_speech_score=min_speech_score,
                max_capture_finished_to_vad_observed_ms=(
                    max_capture_finished_to_vad_observed_ms
                ),
                min_frames_processed=min_frames_processed,
            )
        except ValueError as error:
            issues.append(f"line_{line_number}:unsafe_readiness:{error}")
            continue

        payload = readiness.to_json_dict()
        readiness_records += 1

        reason = str(payload.get("reason") or "")
        hook = str(payload.get("hook") or "")
        source = str(payload.get("source") or "")
        publish_stage = str(payload.get("publish_stage") or "")
        candidate_reason = str(payload.get("candidate_reason") or "")

        if reason:
            readiness_reason_counts[reason] += 1
        if hook:
            hook_counts[hook] += 1
        if source:
            source_counts[source] += 1
        if publish_stage:
            publish_stage_counts[publish_stage] += 1
        if candidate_reason:
            candidate_reason_counts[candidate_reason] += 1

        if bool(payload.get("ready", False)):
            ready_records += 1
        else:
            not_ready_records += 1

        score = _optional_float(payload.get("speech_score_max"))
        if score is not None:
            max_speech_score = (
                score if max_speech_score is None else max(max_speech_score, score)
            )

        frames_processed = _positive_int(payload.get("frames_processed"))
        if frames_processed > 0:
            max_frames_processed = (
                frames_processed
                if max_frames_processed is None
                else max(max_frames_processed, frames_processed)
            )

        capture_latency = _optional_float(
            payload.get("capture_finished_to_vad_observed_ms")
        )
        if capture_latency is not None:
            max_capture_finished_to_vad_observed_ms_seen = (
                capture_latency
                if max_capture_finished_to_vad_observed_ms_seen is None
                else max(
                    max_capture_finished_to_vad_observed_ms_seen,
                    capture_latency,
                )
            )

        publish_latency = _optional_float(
            payload.get("capture_window_publish_to_vad_observed_ms")
        )
        if publish_latency is not None:
            max_capture_window_publish_to_vad_observed_ms_seen = (
                publish_latency
                if max_capture_window_publish_to_vad_observed_ms_seen is None
                else max(
                    max_capture_window_publish_to_vad_observed_ms_seen,
                    publish_latency,
                )
            )

        if bool(payload.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:readiness_action_executed")
        if bool(payload.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:readiness_full_stt_prevented")
        if bool(payload.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:readiness_runtime_takeover")

    if invalid_json_records > 0:
        issues.append("invalid_json_records_present")

    if require_readiness_records and readiness_records <= 0:
        issues.append("command_readiness_records_missing")

    if require_ready and ready_records <= 0:
        issues.append("command_readiness_ready_records_missing")

    if require_no_not_ready and not_ready_records > 0:
        issues.append("command_readiness_not_ready_records_present")

    return {
        "accepted": not issues,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "invalid_json_records": invalid_json_records,
        "readiness_records": readiness_records,
        "ready_records": ready_records,
        "not_ready_records": not_ready_records,
        "readiness_reason_counts": dict(readiness_reason_counts),
        "hook_counts": dict(hook_counts),
        "source_counts": dict(source_counts),
        "publish_stage_counts": dict(publish_stage_counts),
        "candidate_reason_counts": dict(candidate_reason_counts),
        "max_speech_score": max_speech_score,
        "max_frames_processed": max_frames_processed,
        "max_capture_finished_to_vad_observed_ms": (
            max_capture_finished_to_vad_observed_ms_seen
        ),
        "max_capture_window_publish_to_vad_observed_ms": (
            max_capture_window_publish_to_vad_observed_ms_seen
        ),
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "required_readiness_records": require_readiness_records,
        "required_ready": require_ready,
        "required_no_not_ready": require_no_not_ready,
        "min_speech_score": min_speech_score,
        "max_capture_finished_to_vad_observed_ms_threshold": (
            max_capture_finished_to_vad_observed_ms
        ),
        "min_frames_processed": min_frames_processed,
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
            "Validate whether Voice Engine v2 endpointing candidates are ready "
            "for a future command recognizer input path."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-readiness-records", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--require-no-not-ready", action="store_true")
    parser.add_argument(
        "--min-speech-score",
        type=float,
        default=DEFAULT_MIN_SPEECH_SCORE,
    )
    parser.add_argument(
        "--max-capture-finished-to-vad-observed-ms",
        type=float,
        default=DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS,
    )
    parser.add_argument(
        "--min-frames-processed",
        type=int,
        default=DEFAULT_MIN_FRAMES_PROCESSED,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_command_readiness_log(
        log_path=args.log_path,
        require_readiness_records=args.require_readiness_records,
        require_ready=args.require_ready,
        require_no_not_ready=args.require_no_not_ready,
        min_speech_score=args.min_speech_score,
        max_capture_finished_to_vad_observed_ms=(
            args.max_capture_finished_to_vad_observed_ms
        ),
        min_frames_processed=args.min_frames_processed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())