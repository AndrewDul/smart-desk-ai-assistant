#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    validate_vad_timing_latency_profile,
)


DEFAULT_MAX_CAPTURE_PUBLISH_P95_MS = 50.0
DEFAULT_MAX_VAD_OBSERVE_P95_MS = 500.0
DEFAULT_MAX_STT_TRANSCRIPTION_P95_MS = 2500.0
DEFAULT_MAX_CAPTURE_TO_TRANSCRIPTION_P95_MS = 2000.0
DEFAULT_MAX_STALE_AUDIO_RATIO = 0.2

BOTTLENECK_CAPTURE_PUBLISH = "capture_publish_slow"
BOTTLENECK_VAD_OBSERVE = "vad_observation_slow"
BOTTLENECK_STT_TRANSCRIPTION = "stt_transcription_slow"
BOTTLENECK_LEGACY_STT_PATH = "legacy_stt_path_slow"
BOTTLENECK_STALE_AUDIO_BACKLOG = "stale_audio_backlog_present"


def validate_latency_acceptance_gate(
    *,
    log_path: Path,
    require_records: bool = True,
    require_capture_window_records: bool = True,
    max_capture_publish_p95_ms: float = DEFAULT_MAX_CAPTURE_PUBLISH_P95_MS,
    max_vad_observe_p95_ms: float = DEFAULT_MAX_VAD_OBSERVE_P95_MS,
    max_stt_transcription_p95_ms: float = DEFAULT_MAX_STT_TRANSCRIPTION_P95_MS,
    max_capture_to_transcription_p95_ms: float = (
        DEFAULT_MAX_CAPTURE_TO_TRANSCRIPTION_P95_MS
    ),
    max_stale_audio_ratio: float = DEFAULT_MAX_STALE_AUDIO_RATIO,
    fail_on_target_miss: bool = False,
) -> dict[str, Any]:
    profile = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=require_records,
        require_capture_window_records=require_capture_window_records,
    )

    issues: list[str] = []
    if not bool(profile.get("accepted", False)):
        issues.append("latency_profile_not_accepted")
        issues.extend(
            f"profile:{issue}" for issue in _string_list(profile.get("issues"))
        )

    latency = _mapping(profile.get("latency_ms"))

    capture_publish_p95 = _summary_value(
        latency,
        "capture_finished_to_publish_start",
        "p95",
    )
    vad_observe_p95 = _summary_value(
        latency,
        "capture_window_publish_to_vad_observed",
        "p95",
    )
    stt_transcription_p95 = _summary_value(
        latency,
        "transcription_elapsed",
        "p95",
    )
    capture_to_transcription_p95 = _summary_value(
        latency,
        "capture_window_publish_to_transcription_finished",
        "p95",
    )

    stale_audio_ratio = _float_value(profile.get("stale_audio_ratio"), default=0.0)

    bottlenecks: list[str] = []

    if _above(capture_publish_p95, max_capture_publish_p95_ms):
        bottlenecks.append(BOTTLENECK_CAPTURE_PUBLISH)

    if _above(vad_observe_p95, max_vad_observe_p95_ms):
        bottlenecks.append(BOTTLENECK_VAD_OBSERVE)

    if _above(stt_transcription_p95, max_stt_transcription_p95_ms):
        bottlenecks.append(BOTTLENECK_STT_TRANSCRIPTION)

    if _above(capture_to_transcription_p95, max_capture_to_transcription_p95_ms):
        bottlenecks.append(BOTTLENECK_LEGACY_STT_PATH)

    if stale_audio_ratio > max_stale_audio_ratio:
        bottlenecks.append(BOTTLENECK_STALE_AUDIO_BACKLOG)

    target_passed = not bottlenecks

    if fail_on_target_miss and not target_passed:
        issues.append("latency_targets_missed")

    accepted = not issues

    return {
        "accepted": accepted,
        "validator": "latency_acceptance_gate",
        "log_path": str(log_path),
        "profile_accepted": bool(profile.get("accepted", False)),
        "target_passed": target_passed,
        "fail_on_target_miss": fail_on_target_miss,
        "bottlenecks": bottlenecks,
        "decision": _decision(
            bottlenecks=bottlenecks,
            profile_accepted=bool(profile.get("accepted", False)),
        ),
        "metrics": {
            "records": int(profile.get("records") or 0),
            "capture_window_records": int(profile.get("capture_window_records") or 0),
            "post_capture_records": int(profile.get("post_capture_records") or 0),
            "stale_audio_records": int(profile.get("stale_audio_records") or 0),
            "stale_audio_ratio": stale_audio_ratio,
            "capture_publish_p95_ms": capture_publish_p95,
            "vad_observe_p95_ms": vad_observe_p95,
            "stt_transcription_p95_ms": stt_transcription_p95,
            "capture_to_transcription_p95_ms": capture_to_transcription_p95,
        },
        "thresholds": {
            "max_capture_publish_p95_ms": max_capture_publish_p95_ms,
            "max_vad_observe_p95_ms": max_vad_observe_p95_ms,
            "max_stt_transcription_p95_ms": max_stt_transcription_p95_ms,
            "max_capture_to_transcription_p95_ms": max_capture_to_transcription_p95_ms,
            "max_stale_audio_ratio": max_stale_audio_ratio,
        },
        "classification": {
            "capture_publish": _status(
                capture_publish_p95,
                max_capture_publish_p95_ms,
            ),
            "vad_observe": _status(vad_observe_p95, max_vad_observe_p95_ms),
            "stt_transcription": _status(
                stt_transcription_p95,
                max_stt_transcription_p95_ms,
            ),
            "capture_to_transcription": _status(
                capture_to_transcription_p95,
                max_capture_to_transcription_p95_ms,
            ),
            "stale_audio": (
                "high" if stale_audio_ratio > max_stale_audio_ratio else "ok"
            ),
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "unsafe_field_counts": _mapping(
                _mapping(profile.get("safety")).get("unsafe_field_counts")
            ),
        },
        "profile": profile,
        "issues": issues,
    }


def _decision(*, bottlenecks: list[str], profile_accepted: bool) -> str:
    if not profile_accepted:
        return "fix_observation_log_before_runtime_changes"

    if not bottlenecks:
        return "latency_profile_within_current_gate"

    if BOTTLENECK_STALE_AUDIO_BACKLOG in bottlenecks:
        return "investigate_stale_audio_backlog_before_recognition_takeover"

    if BOTTLENECK_LEGACY_STT_PATH in bottlenecks:
        return "investigate_legacy_stt_path_before_recognition_takeover"

    if BOTTLENECK_STT_TRANSCRIPTION in bottlenecks:
        return "investigate_faster_whisper_transcription_latency"

    if BOTTLENECK_VAD_OBSERVE in bottlenecks:
        return "investigate_vad_observation_latency"

    if BOTTLENECK_CAPTURE_PUBLISH in bottlenecks:
        return "investigate_capture_publish_latency"

    return "investigate_latency_profile"


def _status(value: float | None, threshold: float) -> str:
    if value is None:
        return "missing"
    return "slow" if value > threshold else "ok"


def _above(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def _summary_value(
    latency: Mapping[str, Any],
    section_name: str,
    field_name: str,
) -> float | None:
    section = _mapping(latency.get(section_name))
    value = section.get(field_name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_value(raw_value: Any, *, default: float) -> float:
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item) for item in raw_value]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Classify Voice Engine v2 VAD timing latency profile and report "
            "whether the current observation log is safe for the next migration step."
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
        default=False,
        help="Require at least one JSONL telemetry record.",
    )
    parser.add_argument(
        "--require-capture-window-records",
        action="store_true",
        default=False,
        help="Require at least one capture_window_pre_transcription record.",
    )
    parser.add_argument(
        "--max-capture-publish-p95-ms",
        type=float,
        default=DEFAULT_MAX_CAPTURE_PUBLISH_P95_MS,
        help="Maximum acceptable p95 capture-finished to publish-start latency.",
    )
    parser.add_argument(
        "--max-vad-observe-p95-ms",
        type=float,
        default=DEFAULT_MAX_VAD_OBSERVE_P95_MS,
        help="Maximum acceptable p95 capture-window publish to VAD observed latency.",
    )
    parser.add_argument(
        "--max-stt-transcription-p95-ms",
        type=float,
        default=DEFAULT_MAX_STT_TRANSCRIPTION_P95_MS,
        help="Maximum acceptable p95 FasterWhisper transcription latency.",
    )
    parser.add_argument(
        "--max-capture-to-transcription-p95-ms",
        type=float,
        default=DEFAULT_MAX_CAPTURE_TO_TRANSCRIPTION_P95_MS,
        help=(
            "Maximum acceptable p95 capture-window publish to transcription-finished "
            "latency for command-first readiness."
        ),
    )
    parser.add_argument(
        "--max-stale-audio-ratio",
        type=float,
        default=DEFAULT_MAX_STALE_AUDIO_RATIO,
        help="Maximum acceptable stale_audio_observed ratio.",
    )
    parser.add_argument(
        "--fail-on-target-miss",
        action="store_true",
        help="Return non-zero when latency targets are missed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_latency_acceptance_gate(
        log_path=args.log_path,
        require_records=args.require_records,
        require_capture_window_records=args.require_capture_window_records,
        max_capture_publish_p95_ms=args.max_capture_publish_p95_ms,
        max_vad_observe_p95_ms=args.max_vad_observe_p95_ms,
        max_stt_transcription_p95_ms=args.max_stt_transcription_p95_ms,
        max_capture_to_transcription_p95_ms=(
            args.max_capture_to_transcription_p95_ms
        ),
        max_stale_audio_ratio=args.max_stale_audio_ratio,
        fail_on_target_miss=args.fail_on_target_miss,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
