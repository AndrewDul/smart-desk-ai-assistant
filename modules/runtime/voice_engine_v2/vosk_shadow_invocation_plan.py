from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


VOSK_SHADOW_INVOCATION_PLAN_STAGE = "vosk_shadow_invocation_plan"
VOSK_SHADOW_INVOCATION_PLAN_VERSION = "vosk_shadow_invocation_plan_v1"

DEFAULT_INVOCATION_PLAN_METADATA_KEY = "vosk_shadow_invocation_plan"
EXPECTED_HOOK = "capture_window_pre_transcription"

INVOCATION_PLAN_DISABLED_REASON = "vosk_shadow_invocation_plan_disabled"
INVOCATION_PLAN_READY_REASON = "observe_only_invocation_boundary_ready"
INVOCATION_PLAN_WRONG_HOOK_REASON = "non_capture_window_hook"
INVOCATION_PLAN_CONTRACT_MISSING_REASON = "vosk_live_shadow_contract_missing"
INVOCATION_PLAN_COMMAND_ASR_BRIDGE_MISSING_REASON = "command_asr_shadow_bridge_missing"
INVOCATION_PLAN_COMMAND_ASR_CANDIDATE_MISSING_REASON = "command_asr_candidate_missing"
INVOCATION_PLAN_SEGMENT_NOT_READY_REASON_PREFIX = "command_audio_segment_not_ready"
INVOCATION_PLAN_UNSAFE_CONTRACT_REASON = "unsafe_vosk_live_shadow_contract"
INVOCATION_PLAN_UNSAFE_CANDIDATE_REASON = "unsafe_command_asr_candidate"

UNSAFE_CONTRACT_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
)

UNSAFE_CANDIDATE_FIELDS: tuple[str, ...] = (
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
)


@dataclass(frozen=True, slots=True)
class VoskShadowInvocationPlanSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_INVOCATION_PLAN_METADATA_KEY
    recognizer_name: str = "vosk_command_asr"

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")
        if not self.recognizer_name.strip():
            raise ValueError("recognizer_name must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowInvocationPlan:
    plan_stage: str
    plan_version: str
    enabled: bool
    plan_ready: bool
    reason: str
    metadata_key: str
    hook: str
    input_source: str
    recognizer_name: str
    command_asr_bridge_present: bool
    command_asr_candidate_present: bool
    vosk_live_shadow_contract_present: bool
    segment_present: bool
    segment_reason: str
    segment_audio_duration_ms: float | None
    segment_audio_sample_count: int
    segment_published_byte_count: int
    segment_sample_rate: int | None
    segment_pcm_encoding: str
    recognition_invocation_performed: bool = False
    recognition_attempted: bool = False
    recognized: bool = False
    command_matched: bool = False
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
        if self.recognition_invocation_performed:
            raise ValueError("Invocation plan must not perform recognition invocation")
        if self.recognition_attempted:
            raise ValueError("Invocation plan must not attempt recognition")
        if self.recognized:
            raise ValueError("Invocation plan must not recognize speech")
        if self.command_matched:
            raise ValueError("Invocation plan must not match commands")
        if self.runtime_integration:
            raise ValueError("Invocation plan must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Invocation plan must not enable command execution")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Invocation plan must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Invocation plan must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError("Invocation plan must not start an independent microphone stream")
        if self.live_command_recognition_enabled:
            raise ValueError("Invocation plan must not enable live command recognition")
        if self.raw_pcm_included:
            raise ValueError("Invocation plan must not include raw PCM")
        if self.action_executed:
            raise ValueError("Invocation plan must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Invocation plan must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Invocation plan must never take over runtime")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "plan_stage": self.plan_stage,
            "plan_version": self.plan_version,
            "enabled": self.enabled,
            "plan_ready": self.plan_ready,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "hook": self.hook,
            "input_source": self.input_source,
            "recognizer_name": self.recognizer_name,
            "command_asr_bridge_present": self.command_asr_bridge_present,
            "command_asr_candidate_present": self.command_asr_candidate_present,
            "vosk_live_shadow_contract_present": self.vosk_live_shadow_contract_present,
            "segment_present": self.segment_present,
            "segment_reason": self.segment_reason,
            "segment_audio_duration_ms": self.segment_audio_duration_ms,
            "segment_audio_sample_count": self.segment_audio_sample_count,
            "segment_published_byte_count": self.segment_published_byte_count,
            "segment_sample_rate": self.segment_sample_rate,
            "segment_pcm_encoding": self.segment_pcm_encoding,
            "recognition_invocation_performed": self.recognition_invocation_performed,
            "recognition_attempted": self.recognition_attempted,
            "recognized": self.recognized,
            "command_matched": self.command_matched,
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


def build_vosk_shadow_invocation_plan(
    *,
    hook: str,
    metadata: Mapping[str, Any],
    settings: VoskShadowInvocationPlanSettings | None = None,
) -> VoskShadowInvocationPlan:
    plan_settings = settings or VoskShadowInvocationPlanSettings()
    safe_metadata = dict(metadata or {})

    if not plan_settings.enabled:
        return _plan(
            settings=plan_settings,
            enabled=False,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_DISABLED_REASON,
        )

    if hook != EXPECTED_HOOK:
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_WRONG_HOOK_REASON,
        )

    contract = _mapping(safe_metadata.get("vosk_live_shadow"))
    if not contract:
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_CONTRACT_MISSING_REASON,
        )

    if _has_true_value(contract, UNSAFE_CONTRACT_FIELDS):
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_UNSAFE_CONTRACT_REASON,
            contract=contract,
        )

    bridge = _mapping(safe_metadata.get("command_asr_shadow_bridge"))
    if not bridge:
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_COMMAND_ASR_BRIDGE_MISSING_REASON,
            contract=contract,
        )

    candidate = _mapping(safe_metadata.get("command_asr_candidate"))
    if not candidate:
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_COMMAND_ASR_CANDIDATE_MISSING_REASON,
            contract=contract,
            bridge=bridge,
        )

    if _has_true_value(candidate, UNSAFE_CANDIDATE_FIELDS):
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=INVOCATION_PLAN_UNSAFE_CANDIDATE_REASON,
            contract=contract,
            bridge=bridge,
            candidate=candidate,
        )

    segment_present = bool(candidate.get("segment_present", False))
    segment_reason = str(candidate.get("segment_reason") or candidate.get("reason") or "")

    if not segment_present:
        return _plan(
            settings=plan_settings,
            enabled=True,
            hook=hook,
            plan_ready=False,
            reason=f"{INVOCATION_PLAN_SEGMENT_NOT_READY_REASON_PREFIX}:{segment_reason}",
            contract=contract,
            bridge=bridge,
            candidate=candidate,
        )

    return _plan(
        settings=plan_settings,
        enabled=True,
        hook=hook,
        plan_ready=True,
        reason=INVOCATION_PLAN_READY_REASON,
        contract=contract,
        bridge=bridge,
        candidate=candidate,
    )


def validate_vosk_shadow_invocation_plan(
    plan: VoskShadowInvocationPlan | Mapping[str, Any],
) -> dict[str, Any]:
    payload = plan.to_json_dict() if hasattr(plan, "to_json_dict") else dict(plan)
    issues: list[str] = []

    _require_false(payload, issues, "recognition_invocation_performed")
    _require_false(payload, issues, "recognition_attempted")
    _require_false(payload, issues, "recognized")
    _require_false(payload, issues, "command_matched")
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

    if payload.get("plan_ready") is True and payload.get("segment_present") is not True:
        issues.append("plan_ready_without_segment")

    if payload.get("plan_ready") is True and payload.get("enabled") is not True:
        issues.append("plan_ready_when_disabled")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_invocation_plan",
        "issues": issues,
    }


def _plan(
    *,
    settings: VoskShadowInvocationPlanSettings,
    enabled: bool,
    hook: str,
    plan_ready: bool,
    reason: str,
    contract: Mapping[str, Any] | None = None,
    bridge: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> VoskShadowInvocationPlan:
    safe_contract = dict(contract or {})
    safe_bridge = dict(bridge or {})
    safe_candidate = dict(candidate or {})

    return VoskShadowInvocationPlan(
        plan_stage=VOSK_SHADOW_INVOCATION_PLAN_STAGE,
        plan_version=VOSK_SHADOW_INVOCATION_PLAN_VERSION,
        enabled=enabled,
        plan_ready=plan_ready,
        reason=reason,
        metadata_key=settings.metadata_key,
        hook=str(hook or ""),
        input_source="existing_command_audio_segment_metadata_only",
        recognizer_name=settings.recognizer_name,
        command_asr_bridge_present=bool(safe_bridge),
        command_asr_candidate_present=bool(safe_candidate),
        vosk_live_shadow_contract_present=bool(safe_contract),
        segment_present=bool(safe_candidate.get("segment_present", False)),
        segment_reason=str(
            safe_candidate.get("segment_reason")
            or safe_candidate.get("reason")
            or ""
        ),
        segment_audio_duration_ms=_optional_float(
            safe_candidate.get("segment_audio_duration_ms")
        ),
        segment_audio_sample_count=_positive_int(
            safe_candidate.get("segment_audio_sample_count")
        ),
        segment_published_byte_count=_positive_int(
            safe_candidate.get("segment_published_byte_count")
        ),
        segment_sample_rate=_optional_int(safe_candidate.get("segment_sample_rate")),
        segment_pcm_encoding=str(safe_candidate.get("segment_pcm_encoding") or ""),
        recognition_invocation_performed=False,
        recognition_attempted=False,
        recognized=False,
        command_matched=False,
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


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _has_true_value(payload: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
    return any(payload.get(field_name) is True for field_name in fields)


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


__all__ = [
    "DEFAULT_INVOCATION_PLAN_METADATA_KEY",
    "EXPECTED_HOOK",
    "INVOCATION_PLAN_READY_REASON",
    "VOSK_SHADOW_INVOCATION_PLAN_STAGE",
    "VOSK_SHADOW_INVOCATION_PLAN_VERSION",
    "VoskShadowInvocationPlan",
    "VoskShadowInvocationPlanSettings",
    "build_vosk_shadow_invocation_plan",
    "validate_vosk_shadow_invocation_plan",
]