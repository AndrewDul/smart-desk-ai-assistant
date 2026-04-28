from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class VoiceEngineV2VadEndpointingCandidate:
    hook: str
    candidate_present: bool
    endpoint_detected: bool
    reason: str
    source: str
    publish_stage: str
    frames_processed: int
    speech_started: bool
    speech_ended: bool
    speech_started_count: int
    speech_ended_count: int
    speech_frame_count: int
    silence_frame_count: int
    speech_score_max: float | None
    speech_score_avg: float | None
    speech_score_over_threshold_count: int
    latest_event_type: str
    pcm_profile_signal_level: str
    pcm_profile_rms: float | None
    pcm_profile_peak_abs: float | None
    frame_source_counts: dict[str, int] = field(default_factory=dict)
    capture_finished_to_publish_start_ms: float | None = None
    capture_window_publish_to_vad_observed_ms: float | None = None
    capture_finished_to_vad_observed_ms: float | None = None
    latest_speech_end_to_observe_ms: float | None = None
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Endpointing candidate must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Endpointing candidate must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Endpointing candidate must never take over runtime")
        object.__setattr__(self, "frame_source_counts", dict(self.frame_source_counts))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "candidate_present": self.candidate_present,
            "endpoint_detected": self.endpoint_detected,
            "reason": self.reason,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "frames_processed": self.frames_processed,
            "speech_started": self.speech_started,
            "speech_ended": self.speech_ended,
            "speech_started_count": self.speech_started_count,
            "speech_ended_count": self.speech_ended_count,
            "speech_frame_count": self.speech_frame_count,
            "silence_frame_count": self.silence_frame_count,
            "speech_score_max": self.speech_score_max,
            "speech_score_avg": self.speech_score_avg,
            "speech_score_over_threshold_count": (
                self.speech_score_over_threshold_count
            ),
            "latest_event_type": self.latest_event_type,
            "pcm_profile_signal_level": self.pcm_profile_signal_level,
            "pcm_profile_rms": self.pcm_profile_rms,
            "pcm_profile_peak_abs": self.pcm_profile_peak_abs,
            "frame_source_counts": dict(self.frame_source_counts),
            "capture_finished_to_publish_start_ms": (
                self.capture_finished_to_publish_start_ms
            ),
            "capture_window_publish_to_vad_observed_ms": (
                self.capture_window_publish_to_vad_observed_ms
            ),
            "capture_finished_to_vad_observed_ms": (
                self.capture_finished_to_vad_observed_ms
            ),
            "latest_speech_end_to_observe_ms": (
                self.latest_speech_end_to_observe_ms
            ),
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_vad_endpointing_candidate(
    *,
    hook: str,
    vad_shadow: Mapping[str, Any] | None,
    capture_window_metadata: Mapping[str, Any] | None,
    observed_at_monotonic: float | None = None,
) -> VoiceEngineV2VadEndpointingCandidate:
    shadow = dict(vad_shadow or {})
    capture_window = dict(capture_window_metadata or {})

    frames_processed = _positive_int(shadow.get("frames_processed"))
    speech_started_count = _positive_int(shadow.get("speech_started_count"))
    speech_ended_count = _positive_int(shadow.get("speech_ended_count"))
    speech_frame_count = _positive_int(shadow.get("speech_frame_count"))
    silence_frame_count = _positive_int(shadow.get("silence_frame_count"))
    speech_score_over_threshold_count = _positive_int(
        shadow.get("speech_score_over_threshold_count")
    )

    speech_started = speech_started_count > 0
    speech_ended = speech_ended_count > 0
    endpoint_detected = bool(speech_started and speech_ended)

    source = str(capture_window.get("source") or "")
    publish_stage = str(capture_window.get("publish_stage") or "")

    reason = _candidate_reason(
        vad_shadow=shadow,
        frames_processed=frames_processed,
        speech_started=speech_started,
        speech_ended=speech_ended,
        source=source,
        publish_stage=publish_stage,
    )

    observed_at = _optional_float(
        shadow.get("observation_completed_monotonic"),
        fallback=observed_at_monotonic,
    )
    capture_finished_at = _optional_float(
        capture_window.get("capture_finished_at_monotonic")
    )
    publish_started_at = _optional_float(
        capture_window.get("publish_started_at_monotonic")
    )

    return VoiceEngineV2VadEndpointingCandidate(
        hook=str(hook or "").strip() or "unknown",
        candidate_present=frames_processed > 0 and speech_started,
        endpoint_detected=endpoint_detected,
        reason=reason,
        source=source,
        publish_stage=publish_stage,
        frames_processed=frames_processed,
        speech_started=speech_started,
        speech_ended=speech_ended,
        speech_started_count=speech_started_count,
        speech_ended_count=speech_ended_count,
        speech_frame_count=speech_frame_count,
        silence_frame_count=silence_frame_count,
        speech_score_max=_optional_float(shadow.get("speech_score_max")),
        speech_score_avg=_optional_float(shadow.get("speech_score_avg")),
        speech_score_over_threshold_count=speech_score_over_threshold_count,
        latest_event_type=str(shadow.get("latest_event_type") or ""),
        pcm_profile_signal_level=str(shadow.get("pcm_profile_signal_level") or ""),
        pcm_profile_rms=_optional_float(shadow.get("pcm_profile_rms")),
        pcm_profile_peak_abs=_optional_float(shadow.get("pcm_profile_peak_abs")),
        frame_source_counts=_int_dict(shadow.get("frame_source_counts")),
        capture_finished_to_publish_start_ms=_optional_float(
            capture_window.get("capture_finished_to_publish_start_ms")
        ),
        capture_window_publish_to_vad_observed_ms=_elapsed_ms(
            start=publish_started_at,
            end=observed_at,
        ),
        capture_finished_to_vad_observed_ms=_elapsed_ms(
            start=capture_finished_at,
            end=observed_at,
        ),
        latest_speech_end_to_observe_ms=_optional_float(
            shadow.get("latest_speech_end_to_observe_ms")
        ),
        action_executed=False,
        full_stt_prevented=False,
        runtime_takeover=False,
    )


def _candidate_reason(
    *,
    vad_shadow: Mapping[str, Any],
    frames_processed: int,
    speech_started: bool,
    speech_ended: bool,
    source: str,
    publish_stage: str,
) -> str:
    if not vad_shadow:
        return "vad_shadow_missing"
    if not bool(vad_shadow.get("observed", False)):
        return "vad_shadow_not_observed"
    if frames_processed <= 0:
        return "no_frames_processed"
    if not source:
        return "capture_window_source_missing"
    if publish_stage != "before_transcription":
        return "capture_window_not_before_transcription"
    if not speech_started:
        return "speech_not_started"
    if not speech_ended:
        return "speech_not_ended_yet"
    return "endpoint_detected"


def _optional_float(
    raw_value: Any,
    *,
    fallback: float | None = None,
) -> float | None:
    if raw_value is None:
        return fallback
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback


def _positive_int(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _elapsed_ms(
    *,
    start: float | None,
    end: float | None,
) -> float | None:
    if start is None or end is None:
        return None
    return round(max(0.0, (end - start) * 1000.0), 3)


def _int_dict(raw_value: Any) -> dict[str, int]:
    if not isinstance(raw_value, Mapping):
        return {}

    result: dict[str, int] = {}
    for key, value in raw_value.items():
        result[str(key)] = _positive_int(value)
    return result


__all__ = [
    "VoiceEngineV2VadEndpointingCandidate",
    "build_vad_endpointing_candidate",
]