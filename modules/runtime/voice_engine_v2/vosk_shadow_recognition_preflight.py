from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from modules.runtime.voice_engine_v2.vosk_shadow_asr_result import (
    ASR_RESULT_NOT_ATTEMPTED_REASON,
)
from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (
    EXPECTED_HOOK,
    EXPECTED_PUBLISH_STAGE,
    EXPECTED_SOURCE,
)


VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE = "vosk_shadow_recognition_preflight"
VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION = "vosk_shadow_recognition_preflight_v1"

DEFAULT_RECOGNITION_PREFLIGHT_METADATA_KEY = "vosk_shadow_recognition_preflight"
EXPECTED_RECOGNIZER_NAME = "vosk_command_asr"

RECOGNITION_PREFLIGHT_DISABLED_REASON = "vosk_shadow_recognition_preflight_disabled"
RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON = (
    "recognition_invocation_blocked_by_stage_policy"
)
RECOGNITION_PREFLIGHT_LIVE_SHADOW_MISSING_REASON = "vosk_live_shadow_missing"
RECOGNITION_PREFLIGHT_INVOCATION_PLAN_MISSING_REASON = (
    "vosk_shadow_invocation_plan_missing"
)
RECOGNITION_PREFLIGHT_INVOCATION_PLAN_NOT_READY_REASON = (
    "vosk_shadow_invocation_plan_not_ready"
)
RECOGNITION_PREFLIGHT_PCM_REFERENCE_MISSING_REASON = (
    "vosk_shadow_pcm_reference_missing"
)
RECOGNITION_PREFLIGHT_PCM_REFERENCE_NOT_READY_REASON = (
    "vosk_shadow_pcm_reference_not_ready"
)
RECOGNITION_PREFLIGHT_ASR_RESULT_MISSING_REASON = "vosk_shadow_asr_result_missing"
RECOGNITION_PREFLIGHT_ASR_RESULT_NOT_SAFE_REASON = (
    "vosk_shadow_asr_result_not_safe_not_attempted"
)
RECOGNITION_PREFLIGHT_UNSAFE_DEPENDENCY_REASON = "unsafe_preflight_dependency"
RECOGNITION_PREFLIGHT_WRONG_HOOK_REASON = "non_capture_window_hook"

UNSAFE_DEPENDENCY_FIELDS: tuple[str, ...] = (
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
    "recognition_invocation_performed",
    "recognition_attempted",
    "recognized",
    "command_matched",
)

UNSAFE_PREFLIGHT_FIELDS: tuple[str, ...] = (
    "pcm_retrieval_allowed",
    "pcm_retrieval_performed",
    "recognition_invocation_allowed",
    "recognition_invocation_performed",
    "recognition_attempted",
    "result_present",
    "recognized",
    "command_matched",
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
)


@dataclass(frozen=True, slots=True)
class VoskShadowRecognitionPreflightSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_RECOGNITION_PREFLIGHT_METADATA_KEY
    recognizer_name: str = EXPECTED_RECOGNIZER_NAME

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")
        if not self.recognizer_name.strip():
            raise ValueError("recognizer_name must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowRecognitionPreflight:
    preflight_stage: str
    preflight_version: str
    enabled: bool
    preflight_ready: bool
    recognition_allowed: bool
    recognition_blocked: bool
    reason: str
    metadata_key: str
    hook: str
    source: str
    publish_stage: str
    recognizer_name: str
    live_shadow_present: bool
    invocation_plan_present: bool
    invocation_plan_ready: bool
    pcm_reference_present: bool
    pcm_reference_ready: bool
    asr_result_present: bool
    asr_result_not_attempted: bool
    audio_sample_count: int
    published_byte_count: int
    sample_rate: int | None
    pcm_encoding: str
    pcm_retrieval_allowed: bool = False
    pcm_retrieval_performed: bool = False
    recognition_invocation_allowed: bool = False
    recognition_invocation_performed: bool = False
    recognition_attempted: bool = False
    result_present: bool = False
    recognized: bool = False
    command_matched: bool = False
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
        if self.recognition_allowed:
            raise ValueError("Recognition preflight must not allow recognition yet")
        if not self.recognition_blocked:
            raise ValueError("Recognition preflight must keep recognition blocked")
        if self.pcm_retrieval_allowed:
            raise ValueError("Recognition preflight must not allow PCM retrieval")
        if self.pcm_retrieval_performed:
            raise ValueError("Recognition preflight must not retrieve PCM")
        if self.recognition_invocation_allowed:
            raise ValueError("Recognition preflight must not allow invocation")
        if self.recognition_invocation_performed:
            raise ValueError("Recognition preflight must not invoke recognition")
        if self.recognition_attempted:
            raise ValueError("Recognition preflight must not attempt recognition")
        if self.result_present:
            raise ValueError("Recognition preflight must not produce recognition results")
        if self.recognized:
            raise ValueError("Recognition preflight must not recognize speech")
        if self.command_matched:
            raise ValueError("Recognition preflight must not match commands")
        if self.raw_pcm_included:
            raise ValueError("Recognition preflight must not include raw PCM")
        if self.action_executed:
            raise ValueError("Recognition preflight must not execute actions")
        if self.full_stt_prevented:
            raise ValueError("Recognition preflight must not prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Recognition preflight must not take over runtime")
        if self.runtime_integration:
            raise ValueError("Recognition preflight must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Recognition preflight must not enable command execution")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Recognition preflight must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Recognition preflight must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError(
                "Recognition preflight must not start independent microphone stream"
            )
        if self.live_command_recognition_enabled:
            raise ValueError("Recognition preflight must not enable live recognition")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "preflight_stage": self.preflight_stage,
            "preflight_version": self.preflight_version,
            "enabled": self.enabled,
            "preflight_ready": self.preflight_ready,
            "recognition_allowed": self.recognition_allowed,
            "recognition_blocked": self.recognition_blocked,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "hook": self.hook,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "recognizer_name": self.recognizer_name,
            "live_shadow_present": self.live_shadow_present,
            "invocation_plan_present": self.invocation_plan_present,
            "invocation_plan_ready": self.invocation_plan_ready,
            "pcm_reference_present": self.pcm_reference_present,
            "pcm_reference_ready": self.pcm_reference_ready,
            "asr_result_present": self.asr_result_present,
            "asr_result_not_attempted": self.asr_result_not_attempted,
            "audio_sample_count": self.audio_sample_count,
            "published_byte_count": self.published_byte_count,
            "sample_rate": self.sample_rate,
            "pcm_encoding": self.pcm_encoding,
            "pcm_retrieval_allowed": self.pcm_retrieval_allowed,
            "pcm_retrieval_performed": self.pcm_retrieval_performed,
            "recognition_invocation_allowed": self.recognition_invocation_allowed,
            "recognition_invocation_performed": (
                self.recognition_invocation_performed
            ),
            "recognition_attempted": self.recognition_attempted,
            "result_present": self.result_present,
            "recognized": self.recognized,
            "command_matched": self.command_matched,
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


def build_vosk_shadow_recognition_preflight(
    *,
    hook: str,
    metadata: Mapping[str, Any],
    settings: VoskShadowRecognitionPreflightSettings | None = None,
) -> VoskShadowRecognitionPreflight:
    preflight_settings = settings or VoskShadowRecognitionPreflightSettings()
    safe_metadata = dict(metadata or {})

    if not preflight_settings.enabled:
        return _preflight(
            settings=preflight_settings,
            enabled=False,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_DISABLED_REASON,
            hook=hook,
        )

    if hook != EXPECTED_HOOK:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_WRONG_HOOK_REASON,
            hook=hook,
        )

    live_shadow = _mapping(safe_metadata.get("vosk_live_shadow"))
    if not live_shadow:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_LIVE_SHADOW_MISSING_REASON,
            hook=hook,
        )

    invocation_plan = _mapping(safe_metadata.get("vosk_shadow_invocation_plan"))
    if not invocation_plan:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_INVOCATION_PLAN_MISSING_REASON,
            hook=hook,
            live_shadow=live_shadow,
        )

    pcm_reference = _mapping(safe_metadata.get("vosk_shadow_pcm_reference"))
    if not pcm_reference:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_PCM_REFERENCE_MISSING_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
        )

    asr_result = _mapping(safe_metadata.get("vosk_shadow_asr_result"))
    if not asr_result:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_ASR_RESULT_MISSING_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
            pcm_reference=pcm_reference,
        )

    if (
        _has_true_value(live_shadow, UNSAFE_DEPENDENCY_FIELDS)
        or _has_true_value(invocation_plan, UNSAFE_DEPENDENCY_FIELDS)
        or _has_true_value(pcm_reference, UNSAFE_DEPENDENCY_FIELDS)
        or _has_true_value(asr_result, UNSAFE_DEPENDENCY_FIELDS)
    ):
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_UNSAFE_DEPENDENCY_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
            pcm_reference=pcm_reference,
            asr_result=asr_result,
        )

    if invocation_plan.get("plan_ready") is not True:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_INVOCATION_PLAN_NOT_READY_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
            pcm_reference=pcm_reference,
            asr_result=asr_result,
        )

    if pcm_reference.get("reference_ready") is not True:
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_PCM_REFERENCE_NOT_READY_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
            pcm_reference=pcm_reference,
            asr_result=asr_result,
        )

    if (
        asr_result.get("result_present") is not False
        or asr_result.get("recognition_attempted") is not False
        or asr_result.get("reason") != ASR_RESULT_NOT_ATTEMPTED_REASON
    ):
        return _preflight(
            settings=preflight_settings,
            enabled=True,
            preflight_ready=False,
            reason=RECOGNITION_PREFLIGHT_ASR_RESULT_NOT_SAFE_REASON,
            hook=hook,
            live_shadow=live_shadow,
            invocation_plan=invocation_plan,
            pcm_reference=pcm_reference,
            asr_result=asr_result,
        )

    return _preflight(
        settings=preflight_settings,
        enabled=True,
        preflight_ready=True,
        reason=RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON,
        hook=hook,
        live_shadow=live_shadow,
        invocation_plan=invocation_plan,
        pcm_reference=pcm_reference,
        asr_result=asr_result,
    )


def validate_vosk_shadow_recognition_preflight(
    preflight: VoskShadowRecognitionPreflight | Mapping[str, Any],
) -> dict[str, Any]:
    payload = (
        preflight.to_json_dict()
        if hasattr(preflight, "to_json_dict")
        else dict(preflight)
    )
    issues: list[str] = []

    for field_name in UNSAFE_PREFLIGHT_FIELDS:
        _require_false(payload, issues, field_name)

    if payload.get("recognition_allowed") is not False:
        issues.append("recognition_allowed_must_be_false")
    if payload.get("recognition_blocked") is not True:
        issues.append("recognition_blocked_must_be_true")
    if payload.get("preflight_ready") is True:
        _require_true(payload, issues, "live_shadow_present")
        _require_true(payload, issues, "invocation_plan_present")
        _require_true(payload, issues, "invocation_plan_ready")
        _require_true(payload, issues, "pcm_reference_present")
        _require_true(payload, issues, "pcm_reference_ready")
        _require_true(payload, issues, "asr_result_present")
        _require_true(payload, issues, "asr_result_not_attempted")
        if payload.get("reason") != RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON:
            issues.append("ready_preflight_must_use_blocked_reason")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_recognition_preflight",
        "issues": issues,
    }


def _preflight(
    *,
    settings: VoskShadowRecognitionPreflightSettings,
    enabled: bool,
    preflight_ready: bool,
    reason: str,
    hook: str,
    live_shadow: Mapping[str, Any] | None = None,
    invocation_plan: Mapping[str, Any] | None = None,
    pcm_reference: Mapping[str, Any] | None = None,
    asr_result: Mapping[str, Any] | None = None,
) -> VoskShadowRecognitionPreflight:
    live_shadow_payload = _mapping(live_shadow)
    plan_payload = _mapping(invocation_plan)
    reference_payload = _mapping(pcm_reference)
    asr_payload = _mapping(asr_result)

    return VoskShadowRecognitionPreflight(
        preflight_stage=VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE,
        preflight_version=VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION,
        enabled=enabled,
        preflight_ready=preflight_ready,
        recognition_allowed=False,
        recognition_blocked=True,
        reason=reason,
        metadata_key=settings.metadata_key,
        hook=hook,
        source=str(reference_payload.get("source") or EXPECTED_SOURCE),
        publish_stage=str(
            reference_payload.get("publish_stage") or EXPECTED_PUBLISH_STAGE
        ),
        recognizer_name=settings.recognizer_name,
        live_shadow_present=bool(live_shadow_payload),
        invocation_plan_present=bool(plan_payload),
        invocation_plan_ready=bool(plan_payload.get("plan_ready", False)),
        pcm_reference_present=bool(reference_payload),
        pcm_reference_ready=bool(reference_payload.get("reference_ready", False)),
        asr_result_present=bool(asr_payload),
        asr_result_not_attempted=(
            asr_payload.get("result_present") is False
            and asr_payload.get("recognition_attempted") is False
            and asr_payload.get("reason") == ASR_RESULT_NOT_ATTEMPTED_REASON
        ),
        audio_sample_count=_positive_int(reference_payload.get("audio_sample_count")),
        published_byte_count=_positive_int(
            reference_payload.get("published_byte_count")
        ),
        sample_rate=_optional_int(reference_payload.get("sample_rate")),
        pcm_encoding=str(reference_payload.get("pcm_encoding") or ""),
        pcm_retrieval_allowed=False,
        pcm_retrieval_performed=False,
        recognition_invocation_allowed=False,
        recognition_invocation_performed=False,
        recognition_attempted=False,
        result_present=False,
        recognized=False,
        command_matched=False,
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


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _has_true_value(payload: Mapping[str, Any], field_names: tuple[str, ...]) -> bool:
    return any(payload.get(field_name) is True for field_name in field_names)


def _require_false(
    payload: Mapping[str, Any],
    issues: list[str],
    field_name: str,
) -> None:
    if payload.get(field_name) is not False:
        issues.append(f"{field_name}_must_be_false")


def _require_true(
    payload: Mapping[str, Any],
    issues: list[str],
    field_name: str,
) -> None:
    if payload.get(field_name) is not True:
        issues.append(f"{field_name}_must_be_true")


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


__all__ = [
    "DEFAULT_RECOGNITION_PREFLIGHT_METADATA_KEY",
    "RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON",
    "VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE",
    "VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION",
    "VoskShadowRecognitionPreflight",
    "VoskShadowRecognitionPreflightSettings",
    "build_vosk_shadow_recognition_preflight",
    "validate_vosk_shadow_recognition_preflight",
]