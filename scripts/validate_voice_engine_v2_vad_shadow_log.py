from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_pre_stt_shadow.jsonl")


def validate_vad_shadow_log(
    *,
    log_path: Path,
    require_enabled: bool = False,
    require_observed: bool = False,
    require_audio_bus_present: bool = False,
    require_frames: bool = False,
    require_score_diagnostics: bool = False,
    require_timing_diagnostics: bool = False,
    require_score_profile_diagnostics: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []
    reasons: Counter[str] = Counter()
    event_types: Counter[str] = Counter()

    total_lines = 0
    valid_json_records = 0
    vad_shadow_records = 0
    enabled_records = 0
    observed_records = 0
    audio_bus_present_records = 0
    frames_processed_records = 0
    total_frames_processed = 0
    total_events_emitted = 0
    diagnostics_records = 0
    timing_diagnostics_records = 0
    event_timing_records = 0
    speech_score_records = 0
    speech_frame_records = 0
    silence_frame_records = 0
    max_speech_score: float | None = None
    max_speech_frame_count = 0
    max_silence_frame_count = 0
    max_last_frame_age_ms: float | None = None
    max_speech_end_to_observe_ms: float | None = None
    cadence_diagnostics_records = 0
    stale_audio_records = 0
    max_subscription_backlog_frames: int | None = None
    cadence_diagnostic_reasons: Counter[str] = Counter()
    score_profile_diagnostics_records = 0
    max_score_profile_peak_score: float | None = None
    score_profile_peak_buckets: Counter[str] = Counter()
    score_profile_peak_sources: Counter[str] = Counter()
    event_emission_reasons: Counter[str] = Counter()
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
            issues.append(f"line_{line_number}:invalid_json:{error}")
            continue

        valid_json_records += 1
        vad_shadow = _extract_vad_shadow(record)
        if not isinstance(vad_shadow, dict):
            continue

        vad_shadow_records += 1

        reason = str(vad_shadow.get("reason", ""))
        if reason:
            reasons[reason] += 1

        if bool(vad_shadow.get("enabled", False)):
            enabled_records += 1

        if bool(vad_shadow.get("observed", False)):
            observed_records += 1

        if bool(vad_shadow.get("audio_bus_present", False)):
            audio_bus_present_records += 1

        frames_processed = _safe_int(vad_shadow.get("frames_processed"))
        if frames_processed > 0:
            frames_processed_records += 1
            total_frames_processed += frames_processed

        total_events_emitted += _safe_int(vad_shadow.get("events_emitted"))

        if _has_score_diagnostics(vad_shadow):
            diagnostics_records += 1

        if _has_timing_diagnostics(vad_shadow):
            timing_diagnostics_records += 1

        latest_speech_end_to_observe_ms = _safe_float(
            vad_shadow.get("latest_speech_end_to_observe_ms")
        )
        if latest_speech_end_to_observe_ms is not None:
            event_timing_records += 1
            max_speech_end_to_observe_ms = _max_optional_float(
                max_speech_end_to_observe_ms,
                latest_speech_end_to_observe_ms,
            )

        last_frame_age_ms = _safe_float(vad_shadow.get("last_frame_age_ms"))
        if last_frame_age_ms is not None:
            max_last_frame_age_ms = _max_optional_float(
                max_last_frame_age_ms,
                last_frame_age_ms,
            )

        if _has_cadence_diagnostics(vad_shadow):
            cadence_diagnostics_records += 1

        if bool(vad_shadow.get("stale_audio_observed", False)):
            stale_audio_records += 1

        subscription_backlog_frames = _safe_optional_int(
            vad_shadow.get("subscription_backlog_frames")
        )
        if subscription_backlog_frames is not None:
            max_subscription_backlog_frames = _max_optional_int(
                max_subscription_backlog_frames,
                subscription_backlog_frames,
            )

        cadence_diagnostic_reason = str(
            vad_shadow.get("cadence_diagnostic_reason", "")
        )
        if cadence_diagnostic_reason:
            cadence_diagnostic_reasons[cadence_diagnostic_reason] += 1

        if _has_score_profile_diagnostics(vad_shadow):
            score_profile_diagnostics_records += 1

        score_profile_peak_score = _safe_float(
            vad_shadow.get("score_profile_peak_score")
        )
        if score_profile_peak_score is not None:
            max_score_profile_peak_score = _max_optional_float(
                max_score_profile_peak_score,
                score_profile_peak_score,
            )

        score_profile_peak_bucket = str(
            vad_shadow.get("score_profile_peak_bucket", "")
        )
        if score_profile_peak_bucket:
            score_profile_peak_buckets[score_profile_peak_bucket] += 1

        score_profile_peak_source = str(
            vad_shadow.get("score_profile_peak_frame_source", "")
        )
        if score_profile_peak_source:
            score_profile_peak_sources[score_profile_peak_source] += 1

        speech_score_count = _safe_int(vad_shadow.get("speech_score_count"))
        if speech_score_count > 0:
            speech_score_records += 1

        speech_frame_count = _safe_int(vad_shadow.get("speech_frame_count"))
        silence_frame_count = _safe_int(vad_shadow.get("silence_frame_count"))

        if speech_frame_count > 0:
            speech_frame_records += 1
        if silence_frame_count > 0:
            silence_frame_records += 1

        max_speech_frame_count = max(max_speech_frame_count, speech_frame_count)
        max_silence_frame_count = max(max_silence_frame_count, silence_frame_count)

        raw_score_max = vad_shadow.get("speech_score_max")
        if isinstance(raw_score_max, int | float):
            score_max = float(raw_score_max)
            max_speech_score = (
                score_max
                if max_speech_score is None
                else max(max_speech_score, score_max)
            )

        event_emission_reason = str(vad_shadow.get("event_emission_reason", ""))
        if event_emission_reason:
            event_emission_reasons[event_emission_reason] += 1

        for event in vad_shadow.get("events", []) or []:
            if isinstance(event, dict):
                event_type = str(event.get("event_type", ""))
                if event_type:
                    event_types[event_type] += 1

        if bool(vad_shadow.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:vad_shadow_action_executed")

        if bool(vad_shadow.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:vad_shadow_full_stt_prevented")

        if bool(vad_shadow.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:vad_shadow_runtime_takeover")

    if require_enabled and enabled_records == 0:
        issues.append("vad_shadow_enabled_records_missing")

    if require_observed and observed_records == 0:
        issues.append("vad_shadow_observed_records_missing")

    if require_audio_bus_present and audio_bus_present_records == 0:
        issues.append("vad_shadow_audio_bus_present_records_missing")

    if require_frames and frames_processed_records == 0:
        issues.append("vad_shadow_frames_processed_records_missing")

    if require_score_diagnostics and diagnostics_records == 0:
        issues.append("vad_shadow_score_diagnostics_records_missing")

    if require_timing_diagnostics and timing_diagnostics_records == 0:
        issues.append("vad_shadow_timing_diagnostics_records_missing")

    if require_score_profile_diagnostics and score_profile_diagnostics_records == 0:
        issues.append("vad_shadow_score_profile_diagnostics_records_missing")

    accepted = not issues

    return {
        "accepted": accepted,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "vad_shadow_records": vad_shadow_records,
        "enabled_records": enabled_records,
        "observed_records": observed_records,
        "audio_bus_present_records": audio_bus_present_records,
        "frames_processed_records": frames_processed_records,
        "total_frames_processed": total_frames_processed,
        "total_events_emitted": total_events_emitted,
        "diagnostics_records": diagnostics_records,
        "timing_diagnostics_records": timing_diagnostics_records,
        "event_timing_records": event_timing_records,
        "speech_score_records": speech_score_records,
        "speech_frame_records": speech_frame_records,
        "silence_frame_records": silence_frame_records,
        "max_speech_score": max_speech_score,
        "max_speech_frame_count": max_speech_frame_count,
        "max_silence_frame_count": max_silence_frame_count,
        "max_last_frame_age_ms": max_last_frame_age_ms,
        "max_speech_end_to_observe_ms": max_speech_end_to_observe_ms,
        "cadence_diagnostics_records": cadence_diagnostics_records,
        "stale_audio_records": stale_audio_records,
        "max_subscription_backlog_frames": max_subscription_backlog_frames,
        "cadence_diagnostic_reasons": dict(cadence_diagnostic_reasons),
        "score_profile_diagnostics_records": score_profile_diagnostics_records,
        "max_score_profile_peak_score": max_score_profile_peak_score,
        "score_profile_peak_buckets": dict(score_profile_peak_buckets),
        "score_profile_peak_sources": dict(score_profile_peak_sources),
        "event_emission_reasons": dict(event_emission_reasons),
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "reasons": dict(reasons),
        "event_types": dict(event_types),
        "required_enabled": require_enabled,
        "required_observed": require_observed,
        "required_audio_bus_present": require_audio_bus_present,
        "required_frames": require_frames,
        "required_score_diagnostics": require_score_diagnostics,
        "required_timing_diagnostics": require_timing_diagnostics,
        "required_score_profile_diagnostics": require_score_profile_diagnostics,
        "issues": issues,
    }


def _extract_vad_shadow(record: dict[str, Any]) -> dict[str, Any] | None:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        vad_shadow = metadata.get("vad_shadow")
        if isinstance(vad_shadow, dict):
            return vad_shadow

    vad_shadow = record.get("vad_shadow")
    if isinstance(vad_shadow, dict):
        return vad_shadow

    return None


def _has_score_diagnostics(vad_shadow: dict[str, Any]) -> bool:
    required_keys = {
        "speech_score_count",
        "speech_frame_count",
        "silence_frame_count",
        "speech_score_over_threshold_count",
        "event_emission_reason",
    }
    return required_keys.issubset(vad_shadow.keys())


def _has_timing_diagnostics(vad_shadow: dict[str, Any]) -> bool:
    required_keys = {
        "observation_started_monotonic",
        "observation_completed_monotonic",
        "observation_duration_ms",
        "first_frame_timestamp_monotonic",
        "last_frame_timestamp_monotonic",
        "last_frame_end_timestamp_monotonic",
        "last_frame_age_ms",
        "audio_window_duration_ms",
        "latest_speech_started_lag_ms",
        "latest_speech_ended_lag_ms",
        "latest_speech_end_to_observe_ms",
    }
    return required_keys.issubset(vad_shadow.keys())


def _has_score_profile_diagnostics(vad_shadow: dict[str, Any]) -> bool:
    required_keys = {
        "score_profile_sample_count",
        "score_profile_first_scores",
        "score_profile_middle_scores",
        "score_profile_last_scores",
        "score_profile_peak_score",
        "score_profile_peak_index",
        "score_profile_peak_sequence",
        "score_profile_peak_position_ratio",
        "score_profile_peak_bucket",
        "score_profile_peak_frame_source",
        "score_profile_peak_frame_age_ms",
        "frame_source_counts",
    }
    return required_keys.issubset(vad_shadow.keys())




def _has_cadence_diagnostics(vad_shadow: dict[str, Any]) -> bool:
    required_keys = {
        "audio_bus_latest_sequence",
        "audio_bus_frame_count",
        "audio_bus_duration_seconds",
        "subscription_next_sequence_before",
        "subscription_next_sequence_after",
        "subscription_backlog_frames",
        "stale_audio_threshold_ms",
        "stale_audio_observed",
        "cadence_diagnostic_reason",
    }
    return required_keys.issubset(vad_shadow.keys())



def _safe_int(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _safe_float(raw_value: Any) -> float | None:
    if not isinstance(raw_value, int | float):
        return None
    return float(raw_value)


def _safe_optional_int(raw_value: Any) -> int | None:
    if not isinstance(raw_value, int):
        return None
    return raw_value


def _max_optional_int(
    current_value: int | None,
    candidate_value: int,
) -> int:
    if current_value is None:
        return candidate_value
    return max(current_value, candidate_value)


def _max_optional_float(
    current_value: float | None,
    candidate_value: float,
) -> float:
    if current_value is None:
        return candidate_value
    return max(current_value, candidate_value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Voice Engine v2 VAD shadow telemetry."
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to the pre-STT shadow JSONL log.",
    )
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--require-observed", action="store_true")
    parser.add_argument("--require-audio-bus-present", action="store_true")
    parser.add_argument("--require-frames", action="store_true")
    parser.add_argument("--require-score-diagnostics", action="store_true")
    parser.add_argument("--require-timing-diagnostics", action="store_true")
    parser.add_argument("--require-score-profile-diagnostics", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    result = validate_vad_shadow_log(
        log_path=args.log_path,
        require_enabled=args.require_enabled,
        require_observed=args.require_observed,
        require_audio_bus_present=args.require_audio_bus_present,
        require_frames=args.require_frames,
        require_score_diagnostics=args.require_score_diagnostics,
        require_timing_diagnostics=args.require_timing_diagnostics,
        require_score_profile_diagnostics=args.require_score_profile_diagnostics,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())