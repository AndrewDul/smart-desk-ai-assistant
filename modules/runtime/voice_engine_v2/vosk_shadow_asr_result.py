from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from modules.runtime.voice_engine_v2.command_asr import CommandAsrCandidate


VOSK_SHADOW_ASR_RESULT_STAGE = "vosk_shadow_asr_result"
VOSK_SHADOW_ASR_RESULT_VERSION = "vosk_shadow_asr_result_v1"

DEFAULT_ASR_RESULT_METADATA_KEY = "vosk_shadow_asr_result"

ASR_RESULT_DISABLED_REASON = "vosk_shadow_asr_result_disabled"
ASR_RESULT_NOT_ATTEMPTED_REASON = "vosk_shadow_asr_not_attempted"
ASR_RESULT_RECOGNIZED_REASON = "vosk_shadow_asr_recognized"
ASR_RESULT_NOT_RECOGNIZED_REASON = "vosk_shadow_asr_not_recognized"
ASR_RESULT_UNSAFE_CANDIDATE_REASON = "unsafe_command_asr_candidate"

EXPECTED_RECOGNIZER_NAME = "vosk_command_asr"


@dataclass(frozen=True, slots=True)
class VoskShadowAsrResultSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_ASR_RESULT_METADATA_KEY

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowAsrResult:
    result_stage: str
    result_version: str
    enabled: bool
    result_present: bool
    reason: str
    metadata_key: str
    recognizer_name: str
    recognizer_enabled: bool
    recognition_invocation_performed: bool
    recognition_attempted: bool
    recognized: bool
    command_matched: bool
    transcript: str
    normalized_text: str
    language: str | None
    confidence: float | None
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    turn_id: str = ""
    hook: str = ""
    source: str = ""
    publish_stage: str = ""
    segment_present: bool = False
    segment_reason: str = ""
    segment_audio_duration_ms: float | None = None
    segment_audio_sample_count: int = 0
    segment_published_byte_count: int = 0
    segment_sample_rate: int | None = None
    segment_pcm_encoding: str = ""
    pcm_retrieval_performed: bool = False
    raw_pcm_included: bool = False
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False
    runtime_integration: bool = False
    command_execution_enabled: bool = False
    faster_whisper_bypass_enabled: bool = False
    microphone_stream_started: bool = False
    independent_microphone_stream_started: bool = False
    live_command_recognition_enabled: bool = False

    def __post_init__(self) -> None:
        if self.raw_pcm_included:
            raise ValueError("Vosk shadow ASR result must not include raw PCM")
        if self.action_executed:
            raise ValueError("Vosk shadow ASR result must not execute actions")
        if self.full_stt_prevented:
            raise ValueError("Vosk shadow ASR result must not prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Vosk shadow ASR result must not take over runtime")
        if self.runtime_integration:
            raise ValueError("Vosk shadow ASR result must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Vosk shadow ASR result must not enable command execution")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Vosk shadow ASR result must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Vosk shadow ASR result must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError(
                "Vosk shadow ASR result must not start independent microphone stream"
            )
        if self.live_command_recognition_enabled:
            raise ValueError("Vosk shadow ASR result must not enable live recognition")
        if self.recognized and not self.recognition_attempted:
            raise ValueError("Vosk shadow ASR result cannot recognize without attempt")
        if self.command_matched and not self.recognized:
            raise ValueError("Vosk shadow ASR result cannot match without recognition")
        if self.recognition_invocation_performed and not self.recognition_attempted:
            raise ValueError("Invocation performed requires recognition_attempted=true")
        object.__setattr__(self, "alternatives", tuple(self.alternatives))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "result_stage": self.result_stage,
            "result_version": self.result_version,
            "enabled": self.enabled,
            "result_present": self.result_present,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "recognizer_name": self.recognizer_name,
            "recognizer_enabled": self.recognizer_enabled,
            "recognition_invocation_performed": self.recognition_invocation_performed,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "command_matched": self.command_matched,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
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
            "pcm_retrieval_performed": self.pcm_retrieval_performed,
            "raw_pcm_included": self.raw_pcm_included,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
            "runtime_integration": self.runtime_integration,
            "command_execution_enabled": self.command_execution_enabled,
            "faster_whisper_bypass_enabled": self.faster_whisper_bypass_enabled,
            "microphone_stream_started": self.microphone_stream_started,
            "independent_microphone_stream_started": (
                self.independent_microphone_stream_started
            ),
            "live_command_recognition_enabled": self.live_command_recognition_enabled,
        }


def build_vosk_shadow_asr_result(
    *,
    candidate: CommandAsrCandidate | Mapping[str, Any],
    settings: VoskShadowAsrResultSettings | None = None,
) -> VoskShadowAsrResult:
    result_settings = settings or VoskShadowAsrResultSettings()
    payload = _candidate_payload(candidate)

    if not result_settings.enabled:
        return _result(
            settings=result_settings,
            enabled=False,
            result_present=False,
            reason=ASR_RESULT_DISABLED_REASON,
            payload=payload,
        )

    if _candidate_has_unsafe_values(payload):
        return _result(
            settings=result_settings,
            enabled=True,
            result_present=False,
            reason=ASR_RESULT_UNSAFE_CANDIDATE_REASON,
            payload=payload,
        )

    recognition_attempted = bool(payload.get("recognition_attempted", False))
    recognized = bool(payload.get("recognized", False))
    command_matched = bool(payload.get("candidate_present", False))

    if not recognition_attempted:
        return _result(
            settings=result_settings,
            enabled=True,
            result_present=False,
            reason=ASR_RESULT_NOT_ATTEMPTED_REASON,
            payload=payload,
        )

    reason = ASR_RESULT_RECOGNIZED_REASON if recognized else ASR_RESULT_NOT_RECOGNIZED_REASON

    return _result(
        settings=result_settings,
        enabled=True,
        result_present=True,
        reason=reason,
        payload=payload,
        recognition_invocation_performed=True,
        recognition_attempted=recognition_attempted,
        recognized=recognized,
        command_matched=command_matched,
    )


def validate_vosk_shadow_asr_result(
    result: VoskShadowAsrResult | Mapping[str, Any],
) -> dict[str, Any]:
    payload = result.to_json_dict() if hasattr(result, "to_json_dict") else dict(result)
    issues: list[str] = []

    _require_false(payload, issues, "raw_pcm_included")
    _require_false(payload, issues, "action_executed")
    _require_false(payload, issues, "full_stt_prevented")
    _require_false(payload, issues, "runtime_takeover")
    _require_false(payload, issues, "runtime_integration")
    _require_false(payload, issues, "command_execution_enabled")
    _require_false(payload, issues, "faster_whisper_bypass_enabled")
    _require_false(payload, issues, "microphone_stream_started")
    _require_false(payload, issues, "independent_microphone_stream_started")
    _require_false(payload, issues, "live_command_recognition_enabled")

    if payload.get("recognized") is True and payload.get("recognition_attempted") is not True:
        issues.append("recognized_without_attempt")
    if payload.get("command_matched") is True and payload.get("recognized") is not True:
        issues.append("command_matched_without_recognition")
    if (
        payload.get("recognition_invocation_performed") is True
        and payload.get("recognition_attempted") is not True
    ):
        issues.append("invocation_performed_without_attempt")
    if payload.get("result_present") is True and payload.get("enabled") is not True:
        issues.append("result_present_when_disabled")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_asr_result",
        "issues": issues,
    }


def _result(
    *,
    settings: VoskShadowAsrResultSettings,
    enabled: bool,
    result_present: bool,
    reason: str,
    payload: Mapping[str, Any],
    recognition_invocation_performed: bool = False,
    recognition_attempted: bool = False,
    recognized: bool = False,
    command_matched: bool = False,
) -> VoskShadowAsrResult:
    return VoskShadowAsrResult(
        result_stage=VOSK_SHADOW_ASR_RESULT_STAGE,
        result_version=VOSK_SHADOW_ASR_RESULT_VERSION,
        enabled=enabled,
        result_present=result_present,
        reason=reason,
        metadata_key=settings.metadata_key,
        recognizer_name=str(payload.get("recognizer_name") or EXPECTED_RECOGNIZER_NAME),
        recognizer_enabled=bool(payload.get("recognizer_enabled", False)),
        recognition_invocation_performed=recognition_invocation_performed,
        recognition_attempted=recognition_attempted,
        recognized=recognized,
        command_matched=command_matched,
        transcript=str(payload.get("transcript") or ""),
        normalized_text=str(payload.get("normalized_text") or ""),
        language=_optional_str(payload.get("language")),
        confidence=_optional_float(payload.get("confidence")),
        alternatives=tuple(str(item) for item in payload.get("alternatives", [])),
        turn_id=str(payload.get("turn_id") or ""),
        hook=str(payload.get("hook") or ""),
        source=str(payload.get("source") or ""),
        publish_stage=str(payload.get("publish_stage") or ""),
        segment_present=bool(payload.get("segment_present", False)),
        segment_reason=str(payload.get("segment_reason") or ""),
        segment_audio_duration_ms=_optional_float(
            payload.get("segment_audio_duration_ms")
        ),
        segment_audio_sample_count=_positive_int(
            payload.get("segment_audio_sample_count")
        ),
        segment_published_byte_count=_positive_int(
            payload.get("segment_published_byte_count")
        ),
        segment_sample_rate=_optional_int(payload.get("segment_sample_rate")),
        segment_pcm_encoding=str(payload.get("segment_pcm_encoding") or ""),
        pcm_retrieval_performed=bool(recognition_attempted),
        raw_pcm_included=False,
        action_executed=False,
        full_stt_prevented=False,
        runtime_takeover=False,
        runtime_integration=False,
        command_execution_enabled=False,
        faster_whisper_bypass_enabled=False,
        microphone_stream_started=False,
        independent_microphone_stream_started=False,
        live_command_recognition_enabled=False,
    )


def _candidate_payload(candidate: CommandAsrCandidate | Mapping[str, Any]) -> dict[str, Any]:
    to_json_dict = getattr(candidate, "to_json_dict", None)
    if callable(to_json_dict):
        return dict(to_json_dict())
    return dict(candidate or {})


def _candidate_has_unsafe_values(payload: Mapping[str, Any]) -> bool:
    return (
        bool(payload.get("raw_pcm_included", False))
        or bool(payload.get("action_executed", False))
        or bool(payload.get("full_stt_prevented", False))
        or bool(payload.get("runtime_takeover", False))
    )


def _require_false(
    payload: Mapping[str, Any],
    issues: list[str],
    field_name: str,
) -> None:
    if payload.get(field_name) is not False:
        issues.append(f"{field_name}_must_be_false")


def _optional_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _optional_int(raw_value: Any) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _positive_int(raw_value: Any) -> int:
    value = _optional_int(raw_value)
    if value is None or value < 0:
        return 0
    return value


def _optional_str(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


__all__ = [
    "ASR_RESULT_DISABLED_REASON",
    "ASR_RESULT_NOT_ATTEMPTED_REASON",
    "ASR_RESULT_NOT_RECOGNIZED_REASON",
    "ASR_RESULT_RECOGNIZED_REASON",
    "DEFAULT_ASR_RESULT_METADATA_KEY",
    "VOSK_SHADOW_ASR_RESULT_STAGE",
    "VOSK_SHADOW_ASR_RESULT_VERSION",
    "VoskShadowAsrResult",
    "VoskShadowAsrResultSettings",
    "build_vosk_shadow_asr_result",
    "validate_vosk_shadow_asr_result",
]