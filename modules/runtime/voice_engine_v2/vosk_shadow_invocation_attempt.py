from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (
    EXPECTED_HOOK,
    EXPECTED_PUBLISH_STAGE,
    EXPECTED_SOURCE,
)
from modules.runtime.voice_engine_v2.vosk_shadow_recognition_preflight import (
    RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON,
)


VOSK_SHADOW_INVOCATION_ATTEMPT_STAGE = "vosk_shadow_invocation_attempt"
VOSK_SHADOW_INVOCATION_ATTEMPT_VERSION = "vosk_shadow_invocation_attempt_v1"

DEFAULT_INVOCATION_ATTEMPT_METADATA_KEY = "vosk_shadow_invocation_attempt"
EXPECTED_RECOGNIZER_NAME = "vosk_command_asr"

INVOCATION_ATTEMPT_DISABLED_REASON = "vosk_shadow_invocation_attempt_disabled"
INVOCATION_ATTEMPT_READY_BLOCKED_REASON = "recognition_invocation_blocked_by_stage_policy"
INVOCATION_ATTEMPT_PREFLIGHT_MISSING_REASON = "vosk_shadow_recognition_preflight_missing"
INVOCATION_ATTEMPT_PREFLIGHT_NOT_READY_REASON = "vosk_shadow_recognition_preflight_not_ready"
INVOCATION_ATTEMPT_PREFLIGHT_NOT_BLOCKED_REASON = (
    "vosk_shadow_recognition_preflight_not_blocked"
)
INVOCATION_ATTEMPT_UNSAFE_DEPENDENCY_REASON = "unsafe_invocation_attempt_dependency"
INVOCATION_ATTEMPT_WRONG_HOOK_REASON = "non_capture_window_hook"

UNSAFE_DEPENDENCY_FIELDS: tuple[str, ...] = (
    "pcm_retrieval_allowed",
    "pcm_retrieval_performed",
    "recognition_allowed",
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

UNSAFE_ATTEMPT_FIELDS: tuple[str, ...] = UNSAFE_DEPENDENCY_FIELDS


@dataclass(frozen=True, slots=True)
class VoskShadowInvocationAttemptSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_INVOCATION_ATTEMPT_METADATA_KEY
    recognizer_name: str = EXPECTED_RECOGNIZER_NAME

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")
        if not self.recognizer_name.strip():
            raise ValueError("recognizer_name must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowInvocationAttempt:
    attempt_stage: str
    attempt_version: str
    enabled: bool
    attempt_ready: bool
    invocation_allowed: bool
    invocation_blocked: bool
    reason: str
    metadata_key: str
    hook: str
    source: str
    publish_stage: str
    recognizer_name: str
    preflight_present: bool
    preflight_ready: bool
    preflight_recognition_blocked: bool
    preflight_reason: str
    audio_sample_count: int
    published_byte_count: int
    sample_rate: int | None
    pcm_encoding: str
    pcm_retrieval_allowed: bool = False
    pcm_retrieval_performed: bool = False
    recognition_allowed: bool = False
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
        if self.invocation_allowed:
            raise ValueError("Invocation attempt must not allow invocation yet")
        if not self.invocation_blocked:
            raise ValueError("Invocation attempt must keep invocation blocked")
        for field_name in UNSAFE_ATTEMPT_FIELDS:
            if getattr(self, field_name):
                raise ValueError(
                    f"Invocation attempt must keep {field_name}=false"
                )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "attempt_stage": self.attempt_stage,
            "attempt_version": self.attempt_version,
            "enabled": self.enabled,
            "attempt_ready": self.attempt_ready,
            "invocation_allowed": self.invocation_allowed,
            "invocation_blocked": self.invocation_blocked,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "hook": self.hook,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "recognizer_name": self.recognizer_name,
            "preflight_present": self.preflight_present,
            "preflight_ready": self.preflight_ready,
            "preflight_recognition_blocked": self.preflight_recognition_blocked,
            "preflight_reason": self.preflight_reason,
            "audio_sample_count": self.audio_sample_count,
            "published_byte_count": self.published_byte_count,
            "sample_rate": self.sample_rate,
            "pcm_encoding": self.pcm_encoding,
            "pcm_retrieval_allowed": self.pcm_retrieval_allowed,
            "pcm_retrieval_performed": self.pcm_retrieval_performed,
            "recognition_allowed": self.recognition_allowed,
            "recognition_invocation_allowed": self.recognition_invocation_allowed,
            "recognition_invocation_performed": self.recognition_invocation_performed,
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


def build_vosk_shadow_invocation_attempt(
    *,
    hook: str,
    metadata: Mapping[str, Any],
    settings: VoskShadowInvocationAttemptSettings | None = None,
) -> VoskShadowInvocationAttempt:
    attempt_settings = settings or VoskShadowInvocationAttemptSettings()
    safe_metadata = dict(metadata or {})

    if not attempt_settings.enabled:
        return _attempt(
            settings=attempt_settings,
            enabled=False,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_DISABLED_REASON,
            hook=hook,
        )

    if hook != EXPECTED_HOOK:
        return _attempt(
            settings=attempt_settings,
            enabled=True,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_WRONG_HOOK_REASON,
            hook=hook,
        )

    preflight = _mapping(safe_metadata.get("vosk_shadow_recognition_preflight"))
    if not preflight:
        return _attempt(
            settings=attempt_settings,
            enabled=True,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_PREFLIGHT_MISSING_REASON,
            hook=hook,
        )

    if _has_true_value(preflight, UNSAFE_DEPENDENCY_FIELDS):
        return _attempt(
            settings=attempt_settings,
            enabled=True,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_UNSAFE_DEPENDENCY_REASON,
            hook=hook,
            preflight=preflight,
        )

    if preflight.get("preflight_ready") is not True:
        return _attempt(
            settings=attempt_settings,
            enabled=True,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_PREFLIGHT_NOT_READY_REASON,
            hook=hook,
            preflight=preflight,
        )

    if (
        preflight.get("recognition_blocked") is not True
        or preflight.get("reason") != RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON
    ):
        return _attempt(
            settings=attempt_settings,
            enabled=True,
            attempt_ready=False,
            reason=INVOCATION_ATTEMPT_PREFLIGHT_NOT_BLOCKED_REASON,
            hook=hook,
            preflight=preflight,
        )

    return _attempt(
        settings=attempt_settings,
        enabled=True,
        attempt_ready=True,
        reason=INVOCATION_ATTEMPT_READY_BLOCKED_REASON,
        hook=hook,
        preflight=preflight,
    )


def validate_vosk_shadow_invocation_attempt(
    attempt: VoskShadowInvocationAttempt | Mapping[str, Any],
) -> dict[str, Any]:
    payload = attempt.to_json_dict() if hasattr(attempt, "to_json_dict") else dict(attempt)
    issues: list[str] = []

    for field_name in UNSAFE_ATTEMPT_FIELDS:
        _require_false(payload, issues, field_name)

    if payload.get("invocation_allowed") is not False:
        issues.append("invocation_allowed_must_be_false")
    if payload.get("invocation_blocked") is not True:
        issues.append("invocation_blocked_must_be_true")
    if payload.get("attempt_ready") is True:
        _require_true(payload, issues, "preflight_present")
        _require_true(payload, issues, "preflight_ready")
        _require_true(payload, issues, "preflight_recognition_blocked")
        if payload.get("reason") != INVOCATION_ATTEMPT_READY_BLOCKED_REASON:
            issues.append("ready_attempt_must_use_blocked_reason")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_invocation_attempt",
        "issues": issues,
    }


def _attempt(
    *,
    settings: VoskShadowInvocationAttemptSettings,
    enabled: bool,
    attempt_ready: bool,
    reason: str,
    hook: str,
    preflight: Mapping[str, Any] | None = None,
) -> VoskShadowInvocationAttempt:
    safe_preflight = _mapping(preflight)
    return VoskShadowInvocationAttempt(
        attempt_stage=VOSK_SHADOW_INVOCATION_ATTEMPT_STAGE,
        attempt_version=VOSK_SHADOW_INVOCATION_ATTEMPT_VERSION,
        enabled=enabled,
        attempt_ready=attempt_ready,
        invocation_allowed=False,
        invocation_blocked=True,
        reason=reason,
        metadata_key=settings.metadata_key,
        hook=str(hook or ""),
        source=str(safe_preflight.get("source") or ""),
        publish_stage=str(safe_preflight.get("publish_stage") or ""),
        recognizer_name=settings.recognizer_name,
        preflight_present=bool(safe_preflight),
        preflight_ready=bool(safe_preflight.get("preflight_ready", False)),
        preflight_recognition_blocked=bool(
            safe_preflight.get("recognition_blocked", False)
        ),
        preflight_reason=str(safe_preflight.get("reason") or ""),
        audio_sample_count=_int_value(safe_preflight.get("audio_sample_count")),
        published_byte_count=_int_value(safe_preflight.get("published_byte_count")),
        sample_rate=_optional_int(safe_preflight.get("sample_rate")),
        pcm_encoding=str(safe_preflight.get("pcm_encoding") or ""),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _has_true_value(payload: Mapping[str, Any], field_names: tuple[str, ...]) -> bool:
    return any(payload.get(field_name) is True for field_name in field_names)


def _require_false(payload: Mapping[str, Any], issues: list[str], field_name: str) -> None:
    if payload.get(field_name) is not False:
        issues.append(f"{field_name}_must_be_false")


def _require_true(payload: Mapping[str, Any], issues: list[str], field_name: str) -> None:
    if payload.get(field_name) is not True:
        issues.append(f"{field_name}_must_be_true")


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None