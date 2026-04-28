from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from modules.runtime.voice_engine_v2.command_audio_segment import (
    VoiceEngineV2CommandAudioSegment,
    build_command_audio_segment,
)


COMMAND_ASR_CONTRACT_STAGE = "disabled_command_asr_contract"
CONTRACT_VERSION = "stage_24r_v1"
DISABLED_COMMAND_ASR_REASON = "command_asr_disabled"
DISABLED_COMMAND_ASR_RECOGNIZER_NAME = "disabled_command_asr"


@dataclass(frozen=True, slots=True)
class CommandAsrResult:
    recognizer_name: str
    recognizer_enabled: bool
    recognition_attempted: bool
    recognized: bool
    reason: str
    transcript: str = ""
    normalized_text: str = ""
    language: str | None = None
    confidence: float | None = None
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Command ASR result must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Command ASR result must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Command ASR result must never take over runtime")
        if self.recognized and not self.recognition_attempted:
            raise ValueError("Command ASR result cannot be recognized without attempt")
        if self.recognized and not self.transcript.strip():
            raise ValueError("Command ASR result cannot be recognized without transcript")
        if not self.recognizer_enabled and self.recognition_attempted:
            raise ValueError("Disabled command ASR result cannot attempt recognition")
        object.__setattr__(self, "alternatives", tuple(self.alternatives))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "recognizer_name": self.recognizer_name,
            "recognizer_enabled": self.recognizer_enabled,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "reason": self.reason,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


class CommandAsrRecognizer(Protocol):
    recognizer_name: str
    recognizer_enabled: bool

    def recognize(
        self,
        *,
        segment: VoiceEngineV2CommandAudioSegment,
    ) -> CommandAsrResult:
        """Return a command ASR result for an already validated audio segment."""


class DisabledCommandAsrRecognizer:
    recognizer_name = DISABLED_COMMAND_ASR_RECOGNIZER_NAME
    recognizer_enabled = False

    def recognize(
        self,
        *,
        segment: VoiceEngineV2CommandAudioSegment,
    ) -> CommandAsrResult:
        if segment.action_executed:
            raise ValueError("Command ASR recognizer must never receive action execution")
        if segment.full_stt_prevented:
            raise ValueError("Command ASR recognizer must never receive full STT prevention")
        if segment.runtime_takeover:
            raise ValueError("Command ASR recognizer must never receive runtime takeover")

        return CommandAsrResult(
            recognizer_name=self.recognizer_name,
            recognizer_enabled=False,
            recognition_attempted=False,
            recognized=False,
            reason=DISABLED_COMMAND_ASR_REASON,
            transcript="",
            normalized_text="",
            language=None,
            confidence=None,
            alternatives=(),
            action_executed=False,
            full_stt_prevented=False,
            runtime_takeover=False,
        )


NullCommandAsrRecognizer = DisabledCommandAsrRecognizer


@dataclass(frozen=True, slots=True)
class CommandAsrCandidate:
    contract_stage: str
    contract_version: str
    contract_present: bool
    candidate_present: bool
    reason: str
    turn_id: str
    hook: str
    source: str
    publish_stage: str
    segment_present: bool
    segment_reason: str
    segment_audio_duration_ms: float | None
    segment_audio_sample_count: int
    segment_published_byte_count: int
    segment_sample_rate: int | None
    segment_pcm_encoding: str
    recognizer_name: str
    recognizer_enabled: bool
    recognition_attempted: bool
    recognized: bool
    asr_reason: str
    transcript: str
    normalized_text: str
    language: str | None
    confidence: float | None
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    raw_pcm_included: bool = False
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Command ASR candidate must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Command ASR candidate must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Command ASR candidate must never take over runtime")
        if self.raw_pcm_included:
            raise ValueError("Command ASR candidate telemetry must not include raw PCM")
        if self.candidate_present and not self.recognized:
            raise ValueError("Command ASR candidate cannot be present without recognition")
        if self.recognized and not self.recognition_attempted:
            raise ValueError("Command ASR candidate cannot be recognized without attempt")
        object.__setattr__(self, "alternatives", tuple(self.alternatives))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "contract_stage": self.contract_stage,
            "contract_version": self.contract_version,
            "contract_present": self.contract_present,
            "candidate_present": self.candidate_present,
            "reason": self.reason,
            "turn_id": self.turn_id,
            "hook": self.hook,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "segment_present": self.segment_present,
            "segment_reason": self.segment_reason,
            "segment_audio_duration_ms": self.segment_audio_duration_ms,
            "segment_audio_sample_count": self.segment_audio_sample_count,
            "segment_published_byte_count": self.segment_published_byte_count,
            "segment_sample_rate": self.segment_sample_rate,
            "segment_pcm_encoding": self.segment_pcm_encoding,
            "recognizer_name": self.recognizer_name,
            "recognizer_enabled": self.recognizer_enabled,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "asr_reason": self.asr_reason,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
            "raw_pcm_included": self.raw_pcm_included,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_command_asr_candidate(
    *,
    record: Mapping[str, Any],
    recognizer: CommandAsrRecognizer | None = None,
    min_speech_score: float = 0.5,
    max_capture_finished_to_vad_observed_ms: float | None = 750.0,
    min_frames_processed: int = 1,
) -> CommandAsrCandidate:
    command_asr = recognizer or DisabledCommandAsrRecognizer()
    segment = build_command_audio_segment(
        record=record,
        min_speech_score=min_speech_score,
        max_capture_finished_to_vad_observed_ms=(
            max_capture_finished_to_vad_observed_ms
        ),
        min_frames_processed=min_frames_processed,
    )

    result = command_asr.recognize(segment=segment)
    result_payload = result.to_json_dict()

    candidate_present = bool(
        segment.segment_present
        and result.recognizer_enabled
        and result.recognition_attempted
        and result.recognized
    )

    reason = _candidate_reason(
        segment=segment,
        result=result,
        candidate_present=candidate_present,
    )

    return CommandAsrCandidate(
        contract_stage=COMMAND_ASR_CONTRACT_STAGE,
        contract_version=CONTRACT_VERSION,
        contract_present=True,
        candidate_present=candidate_present,
        reason=reason,
        turn_id=segment.turn_id,
        hook=segment.hook,
        source=segment.source,
        publish_stage=segment.publish_stage,
        segment_present=segment.segment_present,
        segment_reason=segment.reason,
        segment_audio_duration_ms=segment.audio_duration_ms,
        segment_audio_sample_count=segment.audio_sample_count,
        segment_published_byte_count=segment.published_byte_count,
        segment_sample_rate=segment.sample_rate,
        segment_pcm_encoding=segment.pcm_encoding,
        recognizer_name=str(result_payload.get("recognizer_name") or ""),
        recognizer_enabled=bool(result_payload.get("recognizer_enabled", False)),
        recognition_attempted=bool(result_payload.get("recognition_attempted", False)),
        recognized=bool(result_payload.get("recognized", False)),
        asr_reason=str(result_payload.get("reason") or ""),
        transcript=str(result_payload.get("transcript") or ""),
        normalized_text=str(result_payload.get("normalized_text") or ""),
        language=_optional_str(result_payload.get("language")),
        confidence=_optional_float(result_payload.get("confidence")),
        alternatives=tuple(
            str(item) for item in result_payload.get("alternatives", [])
        ),
        raw_pcm_included=False,
        action_executed=bool(result_payload.get("action_executed", False)),
        full_stt_prevented=bool(result_payload.get("full_stt_prevented", False)),
        runtime_takeover=bool(result_payload.get("runtime_takeover", False)),
    )


def build_disabled_command_asr_candidate(
    *,
    record: Mapping[str, Any],
    recognizer: CommandAsrRecognizer | None = None,
    min_speech_score: float = 0.5,
    max_capture_finished_to_vad_observed_ms: float | None = 750.0,
    min_frames_processed: int = 1,
) -> CommandAsrCandidate:
    return build_command_asr_candidate(
        record=record,
        recognizer=recognizer,
        min_speech_score=min_speech_score,
        max_capture_finished_to_vad_observed_ms=(
            max_capture_finished_to_vad_observed_ms
        ),
        min_frames_processed=min_frames_processed,
    )


def _candidate_reason(
    *,
    segment: VoiceEngineV2CommandAudioSegment,
    result: CommandAsrResult,
    candidate_present: bool,
) -> str:
    if candidate_present:
        return "command_asr_candidate_present"
    if not segment.segment_present:
        return segment.reason
    if not result.recognizer_enabled:
        return DISABLED_COMMAND_ASR_REASON
    if not result.recognition_attempted:
        return "command_asr_not_attempted"
    if not result.recognized:
        return f"not_recognized:{result.reason}"
    return "command_asr_candidate_absent"


def _optional_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _optional_str(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


__all__ = [
    "COMMAND_ASR_CONTRACT_STAGE",
    "CONTRACT_VERSION",
    "DISABLED_COMMAND_ASR_REASON",
    "DISABLED_COMMAND_ASR_RECOGNIZER_NAME",
    "CommandAsrCandidate",
    "CommandAsrRecognizer",
    "CommandAsrResult",
    "DisabledCommandAsrRecognizer",
    "NullCommandAsrRecognizer",
    "build_command_asr_candidate",
    "build_disabled_command_asr_candidate",
]