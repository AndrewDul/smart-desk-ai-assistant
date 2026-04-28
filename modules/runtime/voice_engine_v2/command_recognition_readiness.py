from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


EXPECTED_HOOK = "capture_window_pre_transcription"
EXPECTED_SOURCE = "faster_whisper_capture_window_shadow_tap"
EXPECTED_PUBLISH_STAGE = "before_transcription"

DEFAULT_MIN_SPEECH_SCORE = 0.5
DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS = 750.0
DEFAULT_MIN_FRAMES_PROCESSED = 1


@dataclass(frozen=True, slots=True)
class VoiceEngineV2CommandRecognitionReadiness:
    ready: bool
    reason: str
    hook: str
    source: str
    publish_stage: str
    candidate_present: bool
    endpoint_detected: bool
    frames_processed: int
    speech_score_max: float | None
    capture_finished_to_vad_observed_ms: float | None
    capture_window_publish_to_vad_observed_ms: float | None
    candidate_reason: str
    pre_transcription_hook: bool
    capture_window_source: bool
    before_transcription_stage: bool
    score_ready: bool
    latency_ready: bool
    frames_ready: bool
    safety_ready: bool
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Readiness gate must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Readiness gate must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Readiness gate must never take over runtime")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "reason": self.reason,
            "hook": self.hook,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "candidate_present": self.candidate_present,
            "endpoint_detected": self.endpoint_detected,
            "frames_processed": self.frames_processed,
            "speech_score_max": self.speech_score_max,
            "capture_finished_to_vad_observed_ms": (
                self.capture_finished_to_vad_observed_ms
            ),
            "capture_window_publish_to_vad_observed_ms": (
                self.capture_window_publish_to_vad_observed_ms
            ),
            "candidate_reason": self.candidate_reason,
            "pre_transcription_hook": self.pre_transcription_hook,
            "capture_window_source": self.capture_window_source,
            "before_transcription_stage": self.before_transcription_stage,
            "score_ready": self.score_ready,
            "latency_ready": self.latency_ready,
            "frames_ready": self.frames_ready,
            "safety_ready": self.safety_ready,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_command_recognition_readiness(
    *,
    record: Mapping[str, Any],
    min_speech_score: float = DEFAULT_MIN_SPEECH_SCORE,
    max_capture_finished_to_vad_observed_ms: (
        float | None
    ) = DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS,
    min_frames_processed: int = DEFAULT_MIN_FRAMES_PROCESSED,
) -> VoiceEngineV2CommandRecognitionReadiness:
    payload = dict(record or {})
    metadata = _mapping(payload.get("metadata"))
    candidate = _mapping(metadata.get("endpointing_candidate"))

    hook = str(payload.get("hook") or candidate.get("hook") or "")
    source = str(candidate.get("source") or "")
    publish_stage = str(candidate.get("publish_stage") or "")
    candidate_reason = str(candidate.get("reason") or "")

    candidate_present = bool(candidate.get("candidate_present", False))
    endpoint_detected = bool(candidate.get("endpoint_detected", False))
    frames_processed = _positive_int(candidate.get("frames_processed"))
    speech_score_max = _optional_float(candidate.get("speech_score_max"))
    capture_finished_to_vad_observed_ms = _optional_float(
        candidate.get("capture_finished_to_vad_observed_ms")
    )
    capture_window_publish_to_vad_observed_ms = _optional_float(
        candidate.get("capture_window_publish_to_vad_observed_ms")
    )

    top_level_action_executed = bool(payload.get("action_executed", False))
    top_level_full_stt_prevented = bool(payload.get("full_stt_prevented", False))
    top_level_runtime_takeover = bool(payload.get("runtime_takeover", False))

    candidate_action_executed = bool(candidate.get("action_executed", False))
    candidate_full_stt_prevented = bool(candidate.get("full_stt_prevented", False))
    candidate_runtime_takeover = bool(candidate.get("runtime_takeover", False))

    action_executed = top_level_action_executed or candidate_action_executed
    full_stt_prevented = top_level_full_stt_prevented or candidate_full_stt_prevented
    runtime_takeover = top_level_runtime_takeover or candidate_runtime_takeover

    pre_transcription_hook = hook == EXPECTED_HOOK
    capture_window_source = source == EXPECTED_SOURCE
    before_transcription_stage = publish_stage == EXPECTED_PUBLISH_STAGE

    score_ready = (
        speech_score_max is not None and speech_score_max >= float(min_speech_score)
    )
    frames_ready = frames_processed >= int(min_frames_processed)

    if max_capture_finished_to_vad_observed_ms is None:
        latency_ready = capture_finished_to_vad_observed_ms is not None
    else:
        latency_ready = (
            capture_finished_to_vad_observed_ms is not None
            and capture_finished_to_vad_observed_ms
            <= float(max_capture_finished_to_vad_observed_ms)
        )

    safety_ready = not action_executed and not full_stt_prevented and not runtime_takeover

    checks = {
        "candidate_present": candidate_present,
        "endpoint_detected": endpoint_detected,
        "pre_transcription_hook": pre_transcription_hook,
        "capture_window_source": capture_window_source,
        "before_transcription_stage": before_transcription_stage,
        "score_ready": score_ready,
        "latency_ready": latency_ready,
        "frames_ready": frames_ready,
        "safety_ready": safety_ready,
    }

    ready = all(checks.values())
    reason = "ready_for_command_recognition" if ready else _first_failed_reason(checks)

    return VoiceEngineV2CommandRecognitionReadiness(
        ready=ready,
        reason=reason,
        hook=hook,
        source=source,
        publish_stage=publish_stage,
        candidate_present=candidate_present,
        endpoint_detected=endpoint_detected,
        frames_processed=frames_processed,
        speech_score_max=speech_score_max,
        capture_finished_to_vad_observed_ms=capture_finished_to_vad_observed_ms,
        capture_window_publish_to_vad_observed_ms=(
            capture_window_publish_to_vad_observed_ms
        ),
        candidate_reason=candidate_reason,
        pre_transcription_hook=pre_transcription_hook,
        capture_window_source=capture_window_source,
        before_transcription_stage=before_transcription_stage,
        score_ready=score_ready,
        latency_ready=latency_ready,
        frames_ready=frames_ready,
        safety_ready=safety_ready,
        action_executed=action_executed,
        full_stt_prevented=full_stt_prevented,
        runtime_takeover=runtime_takeover,
    )


def _first_failed_reason(checks: Mapping[str, bool]) -> str:
    for name, passed in checks.items():
        if not passed:
            return f"not_ready:{name}"
    return "not_ready:unknown"


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


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


__all__ = [
    "DEFAULT_MAX_CAPTURE_FINISHED_TO_VAD_OBSERVED_MS",
    "DEFAULT_MIN_FRAMES_PROCESSED",
    "DEFAULT_MIN_SPEECH_SCORE",
    "EXPECTED_HOOK",
    "EXPECTED_PUBLISH_STAGE",
    "EXPECTED_SOURCE",
    "VoiceEngineV2CommandRecognitionReadiness",
    "build_command_recognition_readiness",
]