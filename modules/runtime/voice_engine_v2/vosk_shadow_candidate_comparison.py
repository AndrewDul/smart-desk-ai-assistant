from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
    normalize_command_text,
)


VOSK_SHADOW_CANDIDATE_COMPARISON_STAGE = "vosk_shadow_candidate_comparison"
VOSK_SHADOW_CANDIDATE_COMPARISON_VERSION = "v1"
DEFAULT_CANDIDATE_COMPARISON_METADATA_KEY = "vosk_shadow_candidate_comparison"

COMPARISON_DISABLED_REASON = "vosk_shadow_candidate_comparison_disabled"
COMPARISON_UNSUPPORTED_HOOK_REASON = "unsupported_hook"
COMPARISON_VOSK_RESULT_MISSING_REASON = "vosk_shadow_asr_result_missing"
COMPARISON_LEGACY_TRANSCRIPT_MISSING_REASON = "legacy_transcript_missing"
COMPARISON_VOSK_NOT_MATCHED_REASON = "vosk_candidate_not_matched"
COMPARISON_LEGACY_NOT_MATCHED_REASON = "legacy_command_not_matched"
COMPARISON_LANGUAGE_MISMATCH_REASON = "language_mismatch"
COMPARISON_INTENT_MISMATCH_REASON = "intent_mismatch"
COMPARISON_AGREES_REASON = "candidate_agrees_with_legacy"


@dataclass(frozen=True, slots=True)
class VoskShadowCandidateComparisonSettings:
    enabled: bool = False
    metadata_key: str = DEFAULT_CANDIDATE_COMPARISON_METADATA_KEY

    def __post_init__(self) -> None:
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty")


@dataclass(frozen=True, slots=True)
class VoskShadowCandidateComparison:
    comparison_stage: str
    comparison_version: str
    enabled: bool
    comparison_present: bool
    reason: str
    metadata_key: str
    hook: str
    turn_id: str

    vosk_result_present: bool
    vosk_recognition_attempted: bool
    vosk_recognized: bool
    vosk_command_matched: bool
    vosk_transcript: str
    vosk_normalized_text: str
    vosk_language: str | None
    vosk_intent_key: str | None
    vosk_matched_phrase: str | None
    vosk_confidence: float | None

    legacy_transcript_present: bool
    legacy_transcript: str
    legacy_normalized_text: str
    legacy_language: str | None
    legacy_intent_key: str | None
    legacy_matched_phrase: str | None
    legacy_confidence: float | None
    legacy_backend_label: str

    transcript_match: bool
    language_match: bool
    intent_match: bool
    candidate_agrees_with_legacy: bool
    safe_to_promote_later: bool

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
            raise ValueError("Candidate comparison must not include raw PCM")
        if self.action_executed:
            raise ValueError("Candidate comparison must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Candidate comparison must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Candidate comparison must never take over runtime")
        if self.runtime_integration:
            raise ValueError("Candidate comparison must not integrate runtime")
        if self.command_execution_enabled:
            raise ValueError("Candidate comparison must not enable command execution")
        if self.faster_whisper_bypass_enabled:
            raise ValueError("Candidate comparison must not bypass FasterWhisper")
        if self.microphone_stream_started:
            raise ValueError("Candidate comparison must not start microphone stream")
        if self.independent_microphone_stream_started:
            raise ValueError("Candidate comparison must not start independent microphone stream")
        if self.live_command_recognition_enabled:
            raise ValueError("Candidate comparison must not enable live command recognition")
        if self.safe_to_promote_later and not self.candidate_agrees_with_legacy:
            raise ValueError("safe_to_promote_later requires candidate agreement")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "comparison_stage": self.comparison_stage,
            "comparison_version": self.comparison_version,
            "enabled": self.enabled,
            "comparison_present": self.comparison_present,
            "reason": self.reason,
            "metadata_key": self.metadata_key,
            "hook": self.hook,
            "turn_id": self.turn_id,
            "vosk_result_present": self.vosk_result_present,
            "vosk_recognition_attempted": self.vosk_recognition_attempted,
            "vosk_recognized": self.vosk_recognized,
            "vosk_command_matched": self.vosk_command_matched,
            "vosk_transcript": self.vosk_transcript,
            "vosk_normalized_text": self.vosk_normalized_text,
            "vosk_language": self.vosk_language,
            "vosk_intent_key": self.vosk_intent_key,
            "vosk_matched_phrase": self.vosk_matched_phrase,
            "vosk_confidence": self.vosk_confidence,
            "legacy_transcript_present": self.legacy_transcript_present,
            "legacy_transcript": self.legacy_transcript,
            "legacy_normalized_text": self.legacy_normalized_text,
            "legacy_language": self.legacy_language,
            "legacy_intent_key": self.legacy_intent_key,
            "legacy_matched_phrase": self.legacy_matched_phrase,
            "legacy_confidence": self.legacy_confidence,
            "legacy_backend_label": self.legacy_backend_label,
            "transcript_match": self.transcript_match,
            "language_match": self.language_match,
            "intent_match": self.intent_match,
            "candidate_agrees_with_legacy": self.candidate_agrees_with_legacy,
            "safe_to_promote_later": self.safe_to_promote_later,
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


def build_vosk_shadow_candidate_comparison(
    *,
    hook: str,
    turn_id: str,
    metadata: Mapping[str, Any],
    settings: VoskShadowCandidateComparisonSettings | None = None,
) -> VoskShadowCandidateComparison:
    comparison_settings = settings or VoskShadowCandidateComparisonSettings()
    safe_metadata = _mapping(metadata)

    if not comparison_settings.enabled:
        return _comparison(
            settings=comparison_settings,
            enabled=False,
            comparison_present=False,
            reason=COMPARISON_DISABLED_REASON,
            hook=hook,
            turn_id=turn_id,
        )

    if str(hook or "") != "post_capture":
        return _comparison(
            settings=comparison_settings,
            enabled=True,
            comparison_present=False,
            reason=COMPARISON_UNSUPPORTED_HOOK_REASON,
            hook=hook,
            turn_id=turn_id,
        )

    vosk_result = _mapping(safe_metadata.get("capture_window_vosk_shadow_asr_result"))
    if not vosk_result:
        vosk_result = _mapping(safe_metadata.get("vosk_shadow_asr_result"))

    transcript_metadata = _mapping(safe_metadata.get("transcript_metadata"))
    legacy_transcript = _first_text(
        transcript_metadata.get("transcript_text"),
        transcript_metadata.get("text"),
        transcript_metadata.get("legacy_transcript"),
    )
    legacy_language = _optional_text(
        transcript_metadata.get("transcript_language"),
        transcript_metadata.get("detected_language"),
        transcript_metadata.get("language"),
    )
    legacy_confidence = _optional_float(
        transcript_metadata.get("transcript_confidence"),
        transcript_metadata.get("language_probability"),
        transcript_metadata.get("confidence"),
    )
    legacy_backend_label = _first_text(
        transcript_metadata.get("backend_label"),
        transcript_metadata.get("engine"),
        transcript_metadata.get("adapter"),
    )

    if not vosk_result:
        return _comparison(
            settings=comparison_settings,
            enabled=True,
            comparison_present=False,
            reason=COMPARISON_VOSK_RESULT_MISSING_REASON,
            hook=hook,
            turn_id=turn_id,
            legacy_transcript=legacy_transcript,
            legacy_language=legacy_language,
            legacy_confidence=legacy_confidence,
            legacy_backend_label=legacy_backend_label,
        )

    if not legacy_transcript:
        return _comparison(
            settings=comparison_settings,
            enabled=True,
            comparison_present=False,
            reason=COMPARISON_LEGACY_TRANSCRIPT_MISSING_REASON,
            hook=hook,
            turn_id=turn_id,
            vosk_result=vosk_result,
            legacy_language=legacy_language,
            legacy_confidence=legacy_confidence,
            legacy_backend_label=legacy_backend_label,
        )

    grammar = build_default_command_grammar()

    vosk_transcript = _first_text(
        vosk_result.get("transcript"),
        vosk_result.get("normalized_text"),
    )
    vosk_match = grammar.match(vosk_transcript)
    legacy_match = grammar.match(legacy_transcript)

    vosk_command_matched = (
        bool(vosk_result.get("command_matched", False))
        and bool(vosk_match.is_match)
    )
    legacy_command_matched = bool(legacy_match.is_match)

    vosk_language = _optional_text(vosk_result.get("language"))
    if vosk_match.is_match:
        vosk_language = vosk_match.language.value

    if legacy_match.is_match:
        legacy_language = legacy_match.language.value

    transcript_match = (
        normalize_command_text(vosk_transcript)
        == normalize_command_text(legacy_transcript)
    )
    language_match = (
        bool(vosk_language)
        and bool(legacy_language)
        and str(vosk_language) == str(legacy_language)
    )
    intent_match = (
        bool(vosk_match.intent_key)
        and bool(legacy_match.intent_key)
        and vosk_match.intent_key == legacy_match.intent_key
    )
    candidate_agrees = (
        vosk_command_matched
        and legacy_command_matched
        and language_match
        and intent_match
    )

    if not vosk_command_matched:
        reason = COMPARISON_VOSK_NOT_MATCHED_REASON
    elif not legacy_command_matched:
        reason = COMPARISON_LEGACY_NOT_MATCHED_REASON
    elif not language_match:
        reason = COMPARISON_LANGUAGE_MISMATCH_REASON
    elif not intent_match:
        reason = COMPARISON_INTENT_MISMATCH_REASON
    else:
        reason = COMPARISON_AGREES_REASON

    return _comparison(
        settings=comparison_settings,
        enabled=True,
        comparison_present=True,
        reason=reason,
        hook=hook,
        turn_id=turn_id,
        vosk_result=vosk_result,
        vosk_intent_key=vosk_match.intent_key,
        vosk_matched_phrase=vosk_match.matched_phrase,
        legacy_transcript=legacy_transcript,
        legacy_language=legacy_language,
        legacy_intent_key=legacy_match.intent_key,
        legacy_matched_phrase=legacy_match.matched_phrase,
        legacy_confidence=legacy_confidence,
        legacy_backend_label=legacy_backend_label,
        transcript_match=transcript_match,
        language_match=language_match,
        intent_match=intent_match,
        candidate_agrees_with_legacy=candidate_agrees,
        safe_to_promote_later=candidate_agrees,
    )


def validate_vosk_shadow_candidate_comparison(
    comparison: VoskShadowCandidateComparison | Mapping[str, Any],
) -> dict[str, Any]:
    payload = (
        comparison.to_json_dict()
        if hasattr(comparison, "to_json_dict")
        else dict(comparison)
    )
    issues: list[str] = []

    for key in (
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
    ):
        if payload.get(key) is True:
            issues.append(f"unsafe_{key}")

    if payload.get("safe_to_promote_later") is True and payload.get(
        "candidate_agrees_with_legacy"
    ) is not True:
        issues.append("safe_to_promote_without_candidate_agreement")

    return {
        "accepted": not issues,
        "validator": "vosk_shadow_candidate_comparison",
        "issues": issues,
    }


def _comparison(
    *,
    settings: VoskShadowCandidateComparisonSettings,
    enabled: bool,
    comparison_present: bool,
    reason: str,
    hook: str,
    turn_id: str,
    vosk_result: Mapping[str, Any] | None = None,
    vosk_intent_key: str | None = None,
    vosk_matched_phrase: str | None = None,
    legacy_transcript: str = "",
    legacy_language: str | None = None,
    legacy_intent_key: str | None = None,
    legacy_matched_phrase: str | None = None,
    legacy_confidence: float | None = None,
    legacy_backend_label: str = "",
    transcript_match: bool = False,
    language_match: bool = False,
    intent_match: bool = False,
    candidate_agrees_with_legacy: bool = False,
    safe_to_promote_later: bool = False,
) -> VoskShadowCandidateComparison:
    vosk_payload = _mapping(vosk_result)
    vosk_transcript = _first_text(
        vosk_payload.get("transcript"),
        vosk_payload.get("normalized_text"),
    )
    return VoskShadowCandidateComparison(
        comparison_stage=VOSK_SHADOW_CANDIDATE_COMPARISON_STAGE,
        comparison_version=VOSK_SHADOW_CANDIDATE_COMPARISON_VERSION,
        enabled=enabled,
        comparison_present=comparison_present,
        reason=reason,
        metadata_key=settings.metadata_key,
        hook=str(hook or ""),
        turn_id=str(turn_id or ""),
        vosk_result_present=bool(vosk_payload),
        vosk_recognition_attempted=bool(
            vosk_payload.get("recognition_attempted", False)
        ),
        vosk_recognized=bool(vosk_payload.get("recognized", False)),
        vosk_command_matched=bool(vosk_payload.get("command_matched", False)),
        vosk_transcript=vosk_transcript,
        vosk_normalized_text=_first_text(
            vosk_payload.get("normalized_text"),
            normalize_command_text(vosk_transcript),
        ),
        vosk_language=_optional_text(vosk_payload.get("language")),
        vosk_intent_key=vosk_intent_key,
        vosk_matched_phrase=vosk_matched_phrase,
        vosk_confidence=_optional_float(vosk_payload.get("confidence")),
        legacy_transcript_present=bool(legacy_transcript.strip()),
        legacy_transcript=legacy_transcript,
        legacy_normalized_text=normalize_command_text(legacy_transcript),
        legacy_language=legacy_language,
        legacy_intent_key=legacy_intent_key,
        legacy_matched_phrase=legacy_matched_phrase,
        legacy_confidence=legacy_confidence,
        legacy_backend_label=legacy_backend_label,
        transcript_match=transcript_match,
        language_match=language_match,
        intent_match=intent_match,
        candidate_agrees_with_legacy=candidate_agrees_with_legacy,
        safe_to_promote_later=safe_to_promote_later,
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


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _optional_text(*values: Any) -> str | None:
    text = _first_text(*values)
    return text or None


def _optional_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


__all__ = [
    "DEFAULT_CANDIDATE_COMPARISON_METADATA_KEY",
    "VOSK_SHADOW_CANDIDATE_COMPARISON_STAGE",
    "VOSK_SHADOW_CANDIDATE_COMPARISON_VERSION",
    "VoskShadowCandidateComparison",
    "VoskShadowCandidateComparisonSettings",
    "build_vosk_shadow_candidate_comparison",
    "validate_vosk_shadow_candidate_comparison",
]
