from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


VOSK_SHADOW_PCM_REFERENCE_STAGE = "vosk_shadow_pcm_reference"
VOSK_SHADOW_PCM_REFERENCE_VERSION = "vosk_shadow_pcm_reference_v1"

DEFAULT_PCM_REFERENCE_METADATA_KEY = "vosk_shadow_pcm_reference"
EXPECTED_HOOK = "capture_window_pre_transcription"
EXPECTED_SOURCE = "faster_whisper_capture_window_shadow_tap"
EXPECTED_PUBLISH_STAGE = "before_transcription"

PCM_REFERENCE_DISABLED_REASON = "vosk_shadow_pcm_reference_disabled"
PCM_REFERENCE_READY_REASON = "existing_capture_window_pcm_reference_ready"
PCM_REFERENCE_WRONG_HOOK_REASON = "non_capture_window_hook"
PCM_REFERENCE_INVOCATION_PLAN_MISSING_REASON = "vosk_shadow_invocation_plan_missing"
PCM_REFERENCE_INVOCATION_PLAN_NOT_READY_REASON = "vosk_shadow_invocation_plan_not_ready"
PCM_REFERENCE_CANDIDATE_MISSING_REASON = "command_asr_candidate_missing"
PCM_REFERENCE_SEGMENT_NOT_READY_REASON = "command_audio_segment_not_ready"
PCM_REFERENCE_UNSAFE_PLAN_REASON = "unsafe_vosk_shadow_invocation_plan"
PCM_REFERENCE_UNSAFE_CANDIDATE_REASON = "unsafe_command_asr_candidate"
PCM_REFERENCE_UNEXPECTED_SOURCE_REASON = "unexpected_audio_source"
PCM_REFERENCE_UNEXPECTED_PUBLISH_STAGE_REASON = "unexpected_publish_stage"
PCM_REFERENCE_AUDIO_COUNTS_MISSING_REASON = "audio_counts_missing"

UNSAFE_PLAN_FIELDS: tuple[str, ...] = (
    "recognition_invocation_performed",
    "recognition_attempted",
    "recognized",
    "command_matched",
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
class VoskShadowPcmReferenceSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_PCM_REFERENCE_METADATA_KEY
    retrieval_strategy: str = "existing_capture_window_audio_bus_snapshot"

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")
        if not self.retrieval_strategy.strip():
            raise ValueError("retrieval_strategy must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowPcmReference:
    reference_stage: str
    reference_version: str
    enabled: bool
    reference_ready: bool
    reason: str
    metadata_key: str
    hook: str
    retrieval_strategy: str
    source: str
    publish_stage: str
    pcm_encoding: str
    sample_rate: int | None
    channels: int | None
    sample_width_bytes: int | None
    audio_sample_count: int
    audio_duration_ms: float | None
    published_frame_count: int
    published_byte_count: int
    segment_present: bool
    invocation_plan_present: bool
    invocation_plan_ready: bool
    command_asr_candidate_present: bool
    raw_pcm_included: bool = False
    pcm_retrieval_performed: bool = False
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
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False

    def __post_init__(self) -> None:
        if self.raw_pcm_included:
            raise ValueError("PCM reference must not include raw PCM")
        if self.pcm_retrieval_performed:
            raise ValueError("PCM reference must not retrieve PCM")
        if self.recognition_invocation_performed:
            raise ValueError("PCM reference must not invoke recognition")
        if self.recognition_attempted:
            raise ValueError("PCM reference must not attempt recognition")
        if self.recognized:
            raise ValueError("PCM reference must not recognize speech")
        if self.command_matched:
            raise ValueError("PCM reference must not match commands")
        if self.runtime_integration:
            raise ValueError("PCM reference must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("PCM reference must not enable command execution")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("PCM reference must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("PCM reference must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError("PCM reference must not start independent microphone stream")
        if self.live_command_recognition_enabled:
            raise ValueError("PCM reference must not enable live recognition")
        if self.action_executed:
            raise ValueError("PCM reference must not execute actions")
        if self.full_stt_prevented:
            raise ValueError("PCM reference must not prevent full STT")
        if self.runtime_takeover:
            raise ValueError("PCM reference must not take over runtime")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "reference_stage": self.reference_stage,
            "reference_version": self.reference_version,
            "enabled": self.enabled,
            "reference_ready": self.reference_ready,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "hook": self.hook,
            "retrieval_strategy": self.retrieval_strategy,
            "source": self.source,
            "publish_stage": self.publish_stage,
            "pcm_encoding": self.pcm_encoding,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "audio_sample_count": self.audio_sample_count,
            "audio_duration_ms": self.audio_duration_ms,
            "published_frame_count": self.published_frame_count,
            "published_byte_count": self.published_byte_count,
            "segment_present": self.segment_present,
            "invocation_plan_present": self.invocation_plan_present,
            "invocation_plan_ready": self.invocation_plan_ready,
            "command_asr_candidate_present": self.command_asr_candidate_present,
            "raw_pcm_included": self.raw_pcm_included,
            "pcm_retrieval_performed": self.pcm_retrieval_performed,
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
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
        }


def build_vosk_shadow_pcm_reference(
    *,
    hook: str,
    metadata: Mapping[str, Any],
    settings: VoskShadowPcmReferenceSettings | None = None,
) -> VoskShadowPcmReference:
    reference_settings = settings or VoskShadowPcmReferenceSettings()
    safe_metadata = dict(metadata or {})

    if not reference_settings.enabled:
        return _reference(
            settings=reference_settings,
            enabled=False,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_DISABLED_REASON,
        )

    if hook != EXPECTED_HOOK:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_WRONG_HOOK_REASON,
        )

    plan = _mapping(safe_metadata.get("vosk_shadow_invocation_plan"))
    if not plan:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_INVOCATION_PLAN_MISSING_REASON,
        )

    if _has_true_value(plan, UNSAFE_PLAN_FIELDS):
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_UNSAFE_PLAN_REASON,
            plan=plan,
        )

    if plan.get("plan_ready") is not True:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_INVOCATION_PLAN_NOT_READY_REASON,
            plan=plan,
        )

    candidate = _mapping(safe_metadata.get("command_asr_candidate"))
    if not candidate:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_CANDIDATE_MISSING_REASON,
            plan=plan,
        )

    if _has_true_value(candidate, UNSAFE_CANDIDATE_FIELDS):
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_UNSAFE_CANDIDATE_REASON,
            plan=plan,
            candidate=candidate,
        )

    if candidate.get("segment_present") is not True:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_SEGMENT_NOT_READY_REASON,
            plan=plan,
            candidate=candidate,
        )

    source = _audio_source(candidate, plan)
    if source != EXPECTED_SOURCE:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_UNEXPECTED_SOURCE_REASON,
            plan=plan,
            candidate=candidate,
        )

    publish_stage = _publish_stage(candidate, plan)
    if publish_stage != EXPECTED_PUBLISH_STAGE:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_UNEXPECTED_PUBLISH_STAGE_REASON,
            plan=plan,
            candidate=candidate,
        )

    audio_sample_count = _audio_sample_count(candidate, plan)
    published_byte_count = _published_byte_count(candidate, plan)
    if audio_sample_count <= 0 or published_byte_count <= 0:
        return _reference(
            settings=reference_settings,
            enabled=True,
            hook=hook,
            reference_ready=False,
            reason=PCM_REFERENCE_AUDIO_COUNTS_MISSING_REASON,
            plan=plan,
            candidate=candidate,
        )

    return _reference(
        settings=reference_settings,
        enabled=True,
        hook=hook,
        reference_ready=True,
        reason=PCM_REFERENCE_READY_REASON,
        plan=plan,
        candidate=candidate,
    )


def validate_vosk_shadow_pcm_reference(
    reference: VoskShadowPcmReference | Mapping[str, Any],
) -> dict[str, Any]:
    payload = (
        reference.to_json_dict()
        if hasattr(reference, "to_json_dict")
        else dict(reference)
    )
    issues: list[str] = []

    _require_false(payload, issues, "raw_pcm_included")
    _require_false(payload, issues, "pcm_retrieval_performed")
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
    _require_false(payload, issues, "action_executed")
    _require_false(payload, issues, "full_stt_prevented")
    _require_false(payload, issues, "runtime_takeover")

    if payload.get("reference_ready") is True and payload.get("enabled") is not True:
        issues.append("reference_ready_when_disabled")
    if payload.get("reference_ready") is True and payload.get("segment_present") is not True:
        issues.append("reference_ready_without_segment")
    if payload.get("reference_ready") is True and payload.get("invocation_plan_ready") is not True:
        issues.append("reference_ready_without_invocation_plan")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_pcm_reference",
        "issues": issues,
    }


def _reference(
    *,
    settings: VoskShadowPcmReferenceSettings,
    enabled: bool,
    hook: str,
    reference_ready: bool,
    reason: str,
    plan: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
) -> VoskShadowPcmReference:
    safe_plan = dict(plan or {})
    safe_candidate = dict(candidate or {})

    return VoskShadowPcmReference(
        reference_stage=VOSK_SHADOW_PCM_REFERENCE_STAGE,
        reference_version=VOSK_SHADOW_PCM_REFERENCE_VERSION,
        enabled=enabled,
        reference_ready=reference_ready,
        reason=reason,
        metadata_key=settings.metadata_key,
        hook=str(hook or ""),
        retrieval_strategy=settings.retrieval_strategy,
        source=_audio_source(safe_candidate, safe_plan),
        publish_stage=_publish_stage(safe_candidate, safe_plan),
        pcm_encoding=_pcm_encoding(safe_candidate, safe_plan),
        sample_rate=_sample_rate(safe_candidate, safe_plan),
        channels=_channels(safe_candidate, safe_plan),
        sample_width_bytes=_sample_width_bytes(safe_candidate, safe_plan),
        audio_sample_count=_audio_sample_count(safe_candidate, safe_plan),
        audio_duration_ms=_audio_duration_ms(safe_candidate, safe_plan),
        published_frame_count=_published_frame_count(safe_candidate),
        published_byte_count=_published_byte_count(safe_candidate, safe_plan),
        segment_present=bool(safe_candidate.get("segment_present", False)),
        invocation_plan_present=bool(safe_plan),
        invocation_plan_ready=bool(safe_plan.get("plan_ready", False)),
        command_asr_candidate_present=bool(safe_candidate),
        raw_pcm_included=False,
        pcm_retrieval_performed=False,
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
        action_executed=False,
        full_stt_prevented=False,
        runtime_takeover=False,
    )


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _audio_source(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> str:
    explicit_source = (
        candidate.get("source")
        or candidate.get("segment_source")
        or plan.get("source")
    )
    if explicit_source:
        return str(explicit_source)

    if plan.get("input_source") == "existing_command_audio_segment_metadata_only":
        return EXPECTED_SOURCE

    if candidate.get("segment_present") is True and plan.get("plan_ready") is True:
        return EXPECTED_SOURCE

    return ""


def _publish_stage(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> str:
    explicit_stage = (
        candidate.get("publish_stage")
        or candidate.get("segment_publish_stage")
        or plan.get("publish_stage")
    )
    if explicit_stage:
        return str(explicit_stage)

    if plan.get("input_source") == "existing_command_audio_segment_metadata_only":
        return EXPECTED_PUBLISH_STAGE

    if candidate.get("segment_present") is True and plan.get("plan_ready") is True:
        return EXPECTED_PUBLISH_STAGE

    return ""


def _pcm_encoding(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> str:
    return str(
        candidate.get("pcm_encoding")
        or candidate.get("segment_pcm_encoding")
        or plan.get("segment_pcm_encoding")
        or ""
    )


def _sample_rate(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int | None:
    return _optional_int(
        candidate.get("sample_rate")
        or candidate.get("segment_sample_rate")
        or plan.get("segment_sample_rate")
    )


def _channels(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int | None:
    explicit_channels = _optional_int(
        candidate.get("channels")
        or candidate.get("segment_channels")
        or plan.get("channels")
        or plan.get("segment_channels")
    )
    if explicit_channels is not None:
        return explicit_channels

    source = _audio_source(candidate, plan)
    if source == EXPECTED_SOURCE:
        return 1

    return None


def _sample_width_bytes(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int | None:
    explicit_width = _optional_int(
        candidate.get("sample_width_bytes")
        or candidate.get("segment_sample_width_bytes")
        or plan.get("sample_width_bytes")
        or plan.get("segment_sample_width_bytes")
    )
    if explicit_width is not None:
        return explicit_width

    encoding = _pcm_encoding(candidate, plan)
    if encoding == "pcm_s16le":
        return 2

    sample_count = _audio_sample_count(candidate, plan)
    byte_count = _published_byte_count(candidate, plan)
    if sample_count > 0 and byte_count > 0 and byte_count % sample_count == 0:
        derived_width = byte_count // sample_count
        if derived_width in {1, 2, 3, 4}:
            return derived_width

    return None


def _audio_sample_count(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int:
    return _positive_int(
        candidate.get("audio_sample_count")
        or candidate.get("segment_audio_sample_count")
        or plan.get("segment_audio_sample_count")
    )


def _audio_duration_ms(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> float | None:
    return _optional_float(
        candidate.get("audio_duration_ms")
        or candidate.get("segment_audio_duration_ms")
        or plan.get("segment_audio_duration_ms")
    )


def _published_frame_count(candidate: Mapping[str, Any]) -> int:
    return _positive_int(
        candidate.get("published_frame_count")
        or candidate.get("segment_published_frame_count")
    )


def _published_byte_count(
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> int:
    return _positive_int(
        candidate.get("published_byte_count")
        or candidate.get("segment_published_byte_count")
        or plan.get("segment_published_byte_count")
    )



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
    "DEFAULT_PCM_REFERENCE_METADATA_KEY",
    "EXPECTED_HOOK",
    "EXPECTED_PUBLISH_STAGE",
    "EXPECTED_SOURCE",
    "PCM_REFERENCE_READY_REASON",
    "VOSK_SHADOW_PCM_REFERENCE_STAGE",
    "VOSK_SHADOW_PCM_REFERENCE_VERSION",
    "VoskShadowPcmReference",
    "VoskShadowPcmReferenceSettings",
    "build_vosk_shadow_pcm_reference",
    "validate_vosk_shadow_pcm_reference",
]