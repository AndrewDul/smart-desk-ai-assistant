from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from modules.runtime.voice_engine_v2.command_recognition_readiness import (
    VoiceEngineV2CommandRecognitionReadiness,
    build_command_recognition_readiness,
)


PCM_ENCODING = "pcm_s16le"
EXPECTED_SOURCE = "faster_whisper_capture_window_shadow_tap"
EXPECTED_PUBLISH_STAGE = "before_transcription"


@dataclass(frozen=True, slots=True)
class VoiceEngineV2CommandAudioSegment:
    segment_present: bool
    reason: str
    turn_id: str
    hook: str
    source: str
    publish_stage: str
    pcm_encoding: str
    raw_pcm_included: bool
    sample_rate: int | None
    channels: int | None
    sample_width_bytes: int | None
    audio_sample_count: int
    audio_duration_ms: float | None
    published_frame_count: int
    published_byte_count: int
    endpoint_detected: bool
    readiness_ready: bool
    readiness_reason: str
    frames_processed: int
    speech_score_max: float | None
    capture_finished_to_publish_start_ms: float | None
    capture_finished_to_vad_observed_ms: float | None
    capture_window_publish_to_vad_observed_ms: float | None
    candidate_reason: str
    metadata_keys: tuple[str, ...] = field(default_factory=tuple)
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Command audio segment must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Command audio segment must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Command audio segment must never take over runtime")
        if self.raw_pcm_included:
            raise ValueError("Stage 24Q command audio segment must not include raw PCM")
        object.__setattr__(self, "metadata_keys", tuple(self.metadata_keys))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "segment_present": self.segment_present,
            "reason": self.reason,
            "turn_id": self.turn_id,
            "hook": self.hook,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "pcm_encoding": self.pcm_encoding,
            "raw_pcm_included": self.raw_pcm_included,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "audio_sample_count": self.audio_sample_count,
            "audio_duration_ms": self.audio_duration_ms,
            "published_frame_count": self.published_frame_count,
            "published_byte_count": self.published_byte_count,
            "endpoint_detected": self.endpoint_detected,
            "readiness_ready": self.readiness_ready,
            "readiness_reason": self.readiness_reason,
            "frames_processed": self.frames_processed,
            "speech_score_max": self.speech_score_max,
            "capture_finished_to_publish_start_ms": (
                self.capture_finished_to_publish_start_ms
            ),
            "capture_finished_to_vad_observed_ms": (
                self.capture_finished_to_vad_observed_ms
            ),
            "capture_window_publish_to_vad_observed_ms": (
                self.capture_window_publish_to_vad_observed_ms
            ),
            "candidate_reason": self.candidate_reason,
            "metadata_keys": list(self.metadata_keys),
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_command_audio_segment(
    *,
    record: Mapping[str, Any],
    min_speech_score: float = 0.5,
    max_capture_finished_to_vad_observed_ms: float | None = 750.0,
    min_frames_processed: int = 1,
) -> VoiceEngineV2CommandAudioSegment:
    payload = dict(record or {})
    metadata = _mapping(payload.get("metadata"))
    candidate = _mapping(metadata.get("endpointing_candidate"))
    capture_window = _mapping(metadata.get("capture_window_shadow_tap"))

    readiness = build_command_recognition_readiness(
        record=payload,
        min_speech_score=min_speech_score,
        max_capture_finished_to_vad_observed_ms=(
            max_capture_finished_to_vad_observed_ms
        ),
        min_frames_processed=min_frames_processed,
    )

    readiness_payload = readiness.to_json_dict()

    source = str(
        capture_window.get("source")
        or readiness_payload.get("source")
        or candidate.get("source")
        or ""
    )
    publish_stage = str(
        capture_window.get("publish_stage")
        or readiness_payload.get("publish_stage")
        or candidate.get("publish_stage")
        or ""
    )

    sample_rate = _optional_int(capture_window.get("sample_rate"))
    channels = _optional_int(capture_window.get("channels"), fallback=1)
    audio_sample_count = _positive_int(capture_window.get("audio_sample_count"))
    published_frame_count = _positive_int(capture_window.get("published_frame_count"))
    published_byte_count = _positive_int(capture_window.get("published_byte_count"))

    sample_width_bytes = _optional_int(capture_window.get("sample_width_bytes"))
    if sample_width_bytes is None:
        sample_width_bytes = _derive_sample_width_bytes(
            published_byte_count=published_byte_count,
            audio_sample_count=audio_sample_count,
            channels=channels,
        )

    audio_duration_ms = _duration_ms_from_capture_window(
        capture_window=capture_window,
        sample_rate=sample_rate,
        audio_sample_count=audio_sample_count,
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

    readiness_ready = bool(readiness_payload.get("ready", False))
    endpoint_detected = bool(candidate.get("endpoint_detected", False))

    segment_present = bool(
        readiness_ready
        and endpoint_detected
        and source == EXPECTED_SOURCE
        and publish_stage == EXPECTED_PUBLISH_STAGE
        and audio_sample_count > 0
        and published_byte_count > 0
        and not action_executed
        and not full_stt_prevented
        and not runtime_takeover
    )

    reason = _segment_reason(
        segment_present=segment_present,
        readiness=readiness,
        source=source,
        publish_stage=publish_stage,
        audio_sample_count=audio_sample_count,
        published_byte_count=published_byte_count,
    )

    return VoiceEngineV2CommandAudioSegment(
        segment_present=segment_present,
        reason=reason,
        turn_id=str(payload.get("turn_id") or ""),
        hook=str(payload.get("hook") or readiness_payload.get("hook") or ""),
        source=source,
        publish_stage=publish_stage,
        pcm_encoding=PCM_ENCODING,
        raw_pcm_included=False,
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width_bytes,
        audio_sample_count=audio_sample_count,
        audio_duration_ms=audio_duration_ms,
        published_frame_count=published_frame_count,
        published_byte_count=published_byte_count,
        endpoint_detected=endpoint_detected,
        readiness_ready=readiness_ready,
        readiness_reason=str(readiness_payload.get("reason") or ""),
        frames_processed=_positive_int(readiness_payload.get("frames_processed")),
        speech_score_max=_optional_float(readiness_payload.get("speech_score_max")),
        capture_finished_to_publish_start_ms=_optional_float(
            capture_window.get("capture_finished_to_publish_start_ms")
        ),
        capture_finished_to_vad_observed_ms=_optional_float(
            readiness_payload.get("capture_finished_to_vad_observed_ms")
        ),
        capture_window_publish_to_vad_observed_ms=_optional_float(
            readiness_payload.get("capture_window_publish_to_vad_observed_ms")
        ),
        candidate_reason=str(candidate.get("reason") or ""),
        metadata_keys=tuple(sorted(str(key) for key in metadata.keys())),
        action_executed=action_executed,
        full_stt_prevented=full_stt_prevented,
        runtime_takeover=runtime_takeover,
    )


def _segment_reason(
    *,
    segment_present: bool,
    readiness: VoiceEngineV2CommandRecognitionReadiness,
    source: str,
    publish_stage: str,
    audio_sample_count: int,
    published_byte_count: int,
) -> str:
    if segment_present:
        return "segment_ready_for_command_recognizer"
    if not readiness.ready:
        return f"not_ready:{readiness.reason}"
    if source != EXPECTED_SOURCE:
        return "not_ready:unexpected_source"
    if publish_stage != EXPECTED_PUBLISH_STAGE:
        return "not_ready:unexpected_publish_stage"
    if audio_sample_count <= 0:
        return "not_ready:audio_sample_count_missing"
    if published_byte_count <= 0:
        return "not_ready:published_byte_count_missing"
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


def _optional_int(raw_value: Any, *, fallback: int | None = None) -> int | None:
    if raw_value is None:
        return fallback
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return fallback


def _positive_int(raw_value: Any) -> int:
    value = _optional_int(raw_value, fallback=0)
    return value if value is not None and value > 0 else 0


def _derive_sample_width_bytes(
    *,
    published_byte_count: int,
    audio_sample_count: int,
    channels: int | None,
) -> int | None:
    channel_count = channels if channels and channels > 0 else 1
    denominator = audio_sample_count * channel_count
    if published_byte_count <= 0 or denominator <= 0:
        return None
    if published_byte_count % denominator != 0:
        return None
    return published_byte_count // denominator


def _duration_ms_from_capture_window(
    *,
    capture_window: Mapping[str, Any],
    sample_rate: int | None,
    audio_sample_count: int,
) -> float | None:
    duration_seconds = _optional_float(capture_window.get("audio_duration_seconds"))
    if duration_seconds is not None:
        return round(duration_seconds * 1000.0, 3)

    if sample_rate is None or sample_rate <= 0 or audio_sample_count <= 0:
        return None

    return round((audio_sample_count / float(sample_rate)) * 1000.0, 3)


__all__ = [
    "EXPECTED_PUBLISH_STAGE",
    "EXPECTED_SOURCE",
    "PCM_ENCODING",
    "VoiceEngineV2CommandAudioSegment",
    "build_command_audio_segment",
]