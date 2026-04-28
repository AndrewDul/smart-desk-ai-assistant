from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.voice_engine_v2.command_asr import CommandAsrResult


VOSK_LIVE_SHADOW_CONTRACT_STAGE = "vosk_live_shadow_contract"
VOSK_LIVE_SHADOW_CONTRACT_VERSION = "stage_24aj_v1"

DEFAULT_VOSK_LIVE_SHADOW_METADATA_KEY = "vosk_live_shadow"
DEFAULT_VOSK_LIVE_SHADOW_INPUT_SOURCE = "existing_command_audio_segment"
DEFAULT_VOSK_LIVE_SHADOW_RECOGNIZER_NAME = "vosk_command_asr_shadow"

VOSK_LIVE_SHADOW_DISABLED_REASON = "vosk_live_shadow_disabled"
VOSK_LIVE_SHADOW_RESULT_MISSING_REASON = "vosk_live_shadow_result_missing"
VOSK_LIVE_SHADOW_OBSERVED_REASON = "vosk_live_shadow_observed"


@dataclass(frozen=True, slots=True)
class VoskLiveShadowContractSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_VOSK_LIVE_SHADOW_METADATA_KEY
    input_source: str = DEFAULT_VOSK_LIVE_SHADOW_INPUT_SOURCE
    recognizer_name: str = DEFAULT_VOSK_LIVE_SHADOW_RECOGNIZER_NAME

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")
        if not self.input_source.strip():
            raise ValueError("input_source must not be empty")
        if not self.recognizer_name.strip():
            raise ValueError("recognizer_name must not be empty")


@dataclass(frozen=True, slots=True)
class VoskLiveShadowCommandMatch:
    command_matched: bool = False
    command_intent_key: str | None = None
    command_language: str | None = None
    command_matched_phrase: str | None = None
    command_confidence: float | None = None
    command_alternatives: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "command_alternatives",
            tuple(self.command_alternatives),
        )
        if self.command_matched and not self.command_intent_key:
            raise ValueError("command_intent_key is required for a matched command")
        if self.command_matched and not self.command_language:
            raise ValueError("command_language is required for a matched command")
        if self.command_matched and not self.command_matched_phrase:
            raise ValueError("command_matched_phrase is required for a matched command")


@dataclass(frozen=True, slots=True)
class VoskLiveShadowContractResult:
    contract_stage: str
    contract_version: str
    enabled: bool
    observed: bool
    reason: str
    metadata_key: str
    input_source: str
    recognizer_name: str
    recognizer_enabled: bool
    recognition_attempted: bool
    recognized: bool
    transcript: str = ""
    normalized_text: str = ""
    language: str | None = None
    confidence: float | None = None
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    command_matched: bool = False
    command_intent_key: str | None = None
    command_language: str | None = None
    command_matched_phrase: str | None = None
    command_confidence: float | None = None
    command_alternatives: tuple[str, ...] = field(default_factory=tuple)
    runtime_integration: bool = False
    command_execution_enabled: bool = False
    faster_whisper_bypass_enabled: bool = False
    microphone_stream_started: bool = False
    independent_microphone_stream_started: bool = False
    live_command_recognition_enabled: bool = False
    raw_pcm_included: bool = False
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "alternatives", tuple(self.alternatives))
        object.__setattr__(
            self,
            "command_alternatives",
            tuple(self.command_alternatives),
        )

        if self.runtime_integration:
            raise ValueError("Vosk live shadow contract must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Vosk live shadow contract must not enable commands")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Vosk live shadow contract must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Vosk live shadow contract must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError(
                "Vosk live shadow contract must not start an independent microphone stream"
            )
        if self.live_command_recognition_enabled:
            raise ValueError(
                "Vosk live shadow contract must not enable live command recognition"
            )
        if self.raw_pcm_included:
            raise ValueError("Vosk live shadow contract must not include raw PCM")
        if self.action_executed:
            raise ValueError("Vosk live shadow contract must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Vosk live shadow contract must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Vosk live shadow contract must never take over runtime")
        if self.recognized and not self.recognition_attempted:
            raise ValueError("Vosk live shadow cannot recognize without attempt")
        if self.command_matched and not self.recognized:
            raise ValueError("Vosk live shadow cannot match command without recognition")
        if self.command_matched and not self.command_intent_key:
            raise ValueError("command_intent_key is required when command_matched=True")
        if self.command_matched and not self.command_language:
            raise ValueError("command_language is required when command_matched=True")
        if self.command_matched and not self.command_matched_phrase:
            raise ValueError("command_matched_phrase is required when command_matched=True")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "contract_stage": self.contract_stage,
            "contract_version": self.contract_version,
            "enabled": self.enabled,
            "observed": self.observed,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "input_source": self.input_source,
            "recognizer_name": self.recognizer_name,
            "recognizer_enabled": self.recognizer_enabled,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
            "command_matched": self.command_matched,
            "command_intent_key": self.command_intent_key,
            "command_language": self.command_language,
            "command_matched_phrase": self.command_matched_phrase,
            "command_confidence": self.command_confidence,
            "command_alternatives": list(self.command_alternatives),
            "runtime_integration": self.runtime_integration,
            "command_execution_enabled": self.command_execution_enabled,
            "faster_whisper_bypass_enabled": self.faster_whisper_bypass_enabled,
            "microphone_stream_started": self.microphone_stream_started,
            "independent_microphone_stream_started": (
                self.independent_microphone_stream_started
            ),
            "live_command_recognition_enabled": self.live_command_recognition_enabled,
            "raw_pcm_included": self.raw_pcm_included,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_vosk_live_shadow_contract(
    *,
    settings: VoskLiveShadowContractSettings | None = None,
    asr_result: CommandAsrResult | None = None,
    command_match: VoskLiveShadowCommandMatch | None = None,
) -> VoskLiveShadowContractResult:
    shadow_settings = settings or VoskLiveShadowContractSettings()

    if not shadow_settings.enabled:
        if asr_result is not None:
            raise ValueError("disabled Vosk live shadow contract cannot receive ASR result")
        if command_match is not None:
            raise ValueError(
                "disabled Vosk live shadow contract cannot receive command match"
            )
        return _disabled_contract(shadow_settings)

    if asr_result is None:
        return _enabled_waiting_contract(shadow_settings)

    _raise_if_unsafe_asr_result(asr_result)

    match = command_match or VoskLiveShadowCommandMatch()
    return VoskLiveShadowContractResult(
        contract_stage=VOSK_LIVE_SHADOW_CONTRACT_STAGE,
        contract_version=VOSK_LIVE_SHADOW_CONTRACT_VERSION,
        enabled=True,
        observed=True,
        reason=VOSK_LIVE_SHADOW_OBSERVED_REASON,
        metadata_key=shadow_settings.metadata_key,
        input_source=shadow_settings.input_source,
        recognizer_name=asr_result.recognizer_name or shadow_settings.recognizer_name,
        recognizer_enabled=asr_result.recognizer_enabled,
        recognition_attempted=asr_result.recognition_attempted,
        recognized=asr_result.recognized,
        transcript=asr_result.transcript,
        normalized_text=asr_result.normalized_text,
        language=asr_result.language,
        confidence=asr_result.confidence,
        alternatives=asr_result.alternatives,
        command_matched=match.command_matched,
        command_intent_key=match.command_intent_key,
        command_language=match.command_language,
        command_matched_phrase=match.command_matched_phrase,
        command_confidence=match.command_confidence,
        command_alternatives=match.command_alternatives,
        runtime_integration=False,
        command_execution_enabled=False,
        faster_whisper_bypass_enabled=False,
        microphone_stream_started=False,
        independent_microphone_stream_started=False,
        live_command_recognition_enabled=False,
        raw_pcm_included=False,
        action_executed=False,
        full_stt_prevented=False,
        runtime_takeover=False,
    )


def build_disabled_vosk_live_shadow_contract() -> VoskLiveShadowContractResult:
    return build_vosk_live_shadow_contract(settings=VoskLiveShadowContractSettings())


def validate_vosk_live_shadow_contract_result(
    result: VoskLiveShadowContractResult | dict[str, Any],
) -> dict[str, Any]:
    payload = result.to_json_dict() if hasattr(result, "to_json_dict") else dict(result)
    issues: list[str] = []

    _require_false(payload, issues, "runtime_integration")
    _require_false(payload, issues, "command_execution_enabled")
    _require_false(payload, issues, "faster_whisper_bypass_enabled")
    _require_false(payload, issues, "microphone_stream_started")
    _require_false(payload, issues, "independent_microphone_stream_started")
    _require_false(payload, issues, "live_command_recognition_enabled")
    _require_false(payload, issues, "raw_pcm_included")
    _require_false(payload, issues, "action_executed")
    _require_false(payload, issues, "full_stt_prevented")
    _require_false(payload, issues, "runtime_takeover")

    if payload.get("recognized") is True and payload.get("recognition_attempted") is not True:
        issues.append("recognized_without_recognition_attempt")
    if payload.get("command_matched") is True and payload.get("recognized") is not True:
        issues.append("command_matched_without_recognition")
    if payload.get("enabled") is False and payload.get("recognition_attempted") is True:
        issues.append("disabled_contract_attempted_recognition")
    if payload.get("enabled") is False and payload.get("observed") is True:
        issues.append("disabled_contract_observed")

    return {
        "accepted": not issues,
        "validation_stage": VOSK_LIVE_SHADOW_CONTRACT_STAGE,
        "validation_version": VOSK_LIVE_SHADOW_CONTRACT_VERSION,
        "issues": issues,
        "result": payload,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }


def _disabled_contract(
    settings: VoskLiveShadowContractSettings,
) -> VoskLiveShadowContractResult:
    return VoskLiveShadowContractResult(
        contract_stage=VOSK_LIVE_SHADOW_CONTRACT_STAGE,
        contract_version=VOSK_LIVE_SHADOW_CONTRACT_VERSION,
        enabled=False,
        observed=False,
        reason=VOSK_LIVE_SHADOW_DISABLED_REASON,
        metadata_key=settings.metadata_key,
        input_source=settings.input_source,
        recognizer_name=settings.recognizer_name,
        recognizer_enabled=False,
        recognition_attempted=False,
        recognized=False,
    )


def _enabled_waiting_contract(
    settings: VoskLiveShadowContractSettings,
) -> VoskLiveShadowContractResult:
    return VoskLiveShadowContractResult(
        contract_stage=VOSK_LIVE_SHADOW_CONTRACT_STAGE,
        contract_version=VOSK_LIVE_SHADOW_CONTRACT_VERSION,
        enabled=True,
        observed=False,
        reason=VOSK_LIVE_SHADOW_RESULT_MISSING_REASON,
        metadata_key=settings.metadata_key,
        input_source=settings.input_source,
        recognizer_name=settings.recognizer_name,
        recognizer_enabled=False,
        recognition_attempted=False,
        recognized=False,
    )


def _raise_if_unsafe_asr_result(asr_result: CommandAsrResult) -> None:
    if asr_result.action_executed:
        raise ValueError("Vosk live shadow must not receive action execution")
    if asr_result.full_stt_prevented:
        raise ValueError("Vosk live shadow must not receive full STT prevention")
    if asr_result.runtime_takeover:
        raise ValueError("Vosk live shadow must not receive runtime takeover")


def _require_false(payload: dict[str, Any], issues: list[str], field: str) -> None:
    if payload.get(field) is not False:
        issues.append(f"unsafe_flag:{field}")


__all__ = [
    "DEFAULT_VOSK_LIVE_SHADOW_INPUT_SOURCE",
    "DEFAULT_VOSK_LIVE_SHADOW_METADATA_KEY",
    "DEFAULT_VOSK_LIVE_SHADOW_RECOGNIZER_NAME",
    "VOSK_LIVE_SHADOW_CONTRACT_STAGE",
    "VOSK_LIVE_SHADOW_CONTRACT_VERSION",
    "VOSK_LIVE_SHADOW_DISABLED_REASON",
    "VOSK_LIVE_SHADOW_OBSERVED_REASON",
    "VOSK_LIVE_SHADOW_RESULT_MISSING_REASON",
    "VoskLiveShadowCommandMatch",
    "VoskLiveShadowContractResult",
    "VoskLiveShadowContractSettings",
    "build_disabled_vosk_live_shadow_contract",
    "build_vosk_live_shadow_contract",
    "validate_vosk_live_shadow_contract_result",
]