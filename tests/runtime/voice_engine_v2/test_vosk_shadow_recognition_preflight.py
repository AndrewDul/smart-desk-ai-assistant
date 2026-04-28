from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_recognition_preflight import (
    RECOGNITION_PREFLIGHT_ASR_RESULT_NOT_SAFE_REASON,
    RECOGNITION_PREFLIGHT_DISABLED_REASON,
    RECOGNITION_PREFLIGHT_PCM_REFERENCE_MISSING_REASON,
    RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON,
    RECOGNITION_PREFLIGHT_UNSAFE_DEPENDENCY_REASON,
    VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE,
    VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION,
    VoskShadowRecognitionPreflightSettings,
    build_vosk_shadow_recognition_preflight,
    validate_vosk_shadow_recognition_preflight,
)


def _live_shadow() -> dict[str, object]:
    return {
        "enabled": True,
        "observed": False,
        "reason": "vosk_live_shadow_result_missing",
        "metadata_key": "vosk_live_shadow",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _invocation_plan() -> dict[str, object]:
    return {
        "enabled": True,
        "plan_ready": True,
        "reason": "observe_only_invocation_boundary_ready",
        "metadata_key": "vosk_shadow_invocation_plan",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _pcm_reference() -> dict[str, object]:
    return {
        "enabled": True,
        "reference_ready": True,
        "reason": "existing_capture_window_pcm_reference_ready",
        "metadata_key": "vosk_shadow_pcm_reference",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "pcm_encoding": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bytes": 2,
        "audio_sample_count": 32000,
        "audio_duration_ms": 1800.0,
        "published_frame_count": 32,
        "published_byte_count": 64000,
        "segment_present": True,
        "invocation_plan_present": True,
        "invocation_plan_ready": True,
        "command_asr_candidate_present": True,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _asr_result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "result_present": False,
        "reason": "vosk_shadow_asr_not_attempted",
        "metadata_key": "vosk_shadow_asr_result",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognizer_name": "disabled_command_asr",
        "recognizer_enabled": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "transcript": "",
        "normalized_text": "",
        "language": None,
        "confidence": None,
        "alternatives": [],
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
        "pcm_retrieval_performed": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }
    payload.update(overrides)
    return payload


def _metadata() -> dict[str, object]:
    return {
        "vosk_live_shadow": _live_shadow(),
        "vosk_shadow_invocation_plan": _invocation_plan(),
        "vosk_shadow_pcm_reference": _pcm_reference(),
        "vosk_shadow_asr_result": _asr_result(),
    }


def test_preflight_disabled_by_default() -> None:
    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
    )

    payload = preflight.to_json_dict()

    assert payload["preflight_stage"] == VOSK_SHADOW_RECOGNITION_PREFLIGHT_STAGE
    assert payload["preflight_version"] == VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION
    assert payload["enabled"] is False
    assert payload["preflight_ready"] is False
    assert payload["recognition_allowed"] is False
    assert payload["recognition_blocked"] is True
    assert payload["reason"] == RECOGNITION_PREFLIGHT_DISABLED_REASON
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["result_present"] is False
    assert payload["runtime_takeover"] is False

    assert validate_vosk_shadow_recognition_preflight(payload)["accepted"] is True


def test_preflight_ready_but_recognition_remains_blocked() -> None:
    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )

    payload = preflight.to_json_dict()

    assert payload["enabled"] is True
    assert payload["preflight_ready"] is True
    assert payload["recognition_allowed"] is False
    assert payload["recognition_blocked"] is True
    assert payload["reason"] == RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON
    assert payload["live_shadow_present"] is True
    assert payload["invocation_plan_present"] is True
    assert payload["invocation_plan_ready"] is True
    assert payload["pcm_reference_present"] is True
    assert payload["pcm_reference_ready"] is True
    assert payload["asr_result_present"] is True
    assert payload["asr_result_not_attempted"] is True
    assert payload["audio_sample_count"] == 32000
    assert payload["published_byte_count"] == 64000
    assert payload["sample_rate"] == 16000
    assert payload["pcm_encoding"] == "pcm_s16le"

    assert payload["pcm_retrieval_allowed"] is False
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_allowed"] is False
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["result_present"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["faster_whisper_bypass_enabled"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["independent_microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False

    assert validate_vosk_shadow_recognition_preflight(payload)["accepted"] is True


def test_preflight_requires_pcm_reference() -> None:
    metadata = _metadata()
    metadata.pop("vosk_shadow_pcm_reference")

    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=metadata,
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )

    payload = preflight.to_json_dict()

    assert payload["enabled"] is True
    assert payload["preflight_ready"] is False
    assert payload["recognition_allowed"] is False
    assert payload["recognition_blocked"] is True
    assert payload["reason"] == RECOGNITION_PREFLIGHT_PCM_REFERENCE_MISSING_REASON
    assert payload["pcm_reference_present"] is False
    assert payload["pcm_reference_ready"] is False

    assert validate_vosk_shadow_recognition_preflight(payload)["accepted"] is True


def test_preflight_rejects_unsafe_dependency_without_attempting_recognition() -> None:
    metadata = _metadata()
    asr_result = metadata["vosk_shadow_asr_result"]
    assert isinstance(asr_result, dict)
    asr_result["action_executed"] = True

    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=metadata,
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )

    payload = preflight.to_json_dict()

    assert payload["enabled"] is True
    assert payload["preflight_ready"] is False
    assert payload["recognition_allowed"] is False
    assert payload["recognition_blocked"] is True
    assert payload["reason"] == RECOGNITION_PREFLIGHT_UNSAFE_DEPENDENCY_REASON
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["action_executed"] is False
    assert payload["runtime_takeover"] is False

    assert validate_vosk_shadow_recognition_preflight(payload)["accepted"] is True


def test_preflight_rejects_asr_result_that_is_no_longer_not_attempted() -> None:
    metadata = _metadata()
    metadata["vosk_shadow_asr_result"] = _asr_result(
        result_present=True,
        reason="vosk_shadow_asr_recognized",
        recognizer_name="vosk_command_asr",
        recognizer_enabled=True,
        recognition_invocation_performed=False,
        recognition_attempted=False,
        recognized=False,
        command_matched=False,
    )

    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=metadata,
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )

    payload = preflight.to_json_dict()

    assert payload["preflight_ready"] is False
    assert payload["recognition_allowed"] is False
    assert payload["recognition_blocked"] is True
    assert payload["reason"] == RECOGNITION_PREFLIGHT_ASR_RESULT_NOT_SAFE_REASON
    assert payload["asr_result_present"] is True
    assert payload["asr_result_not_attempted"] is False

    assert validate_vosk_shadow_recognition_preflight(payload)["accepted"] is True


def test_preflight_validator_rejects_manual_recognition_permission() -> None:
    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )
    payload = preflight.to_json_dict()
    payload["recognition_allowed"] = True
    payload["recognition_invocation_allowed"] = True
    payload["recognition_invocation_performed"] = True

    result = validate_vosk_shadow_recognition_preflight(payload)

    assert result["accepted"] is False
    assert "recognition_allowed_must_be_false" in result["issues"]
    assert "recognition_invocation_allowed_must_be_false" in result["issues"]
    assert "recognition_invocation_performed_must_be_false" in result["issues"]


def test_preflight_validator_rejects_ready_payload_with_missing_dependency_flag() -> None:
    preflight = build_vosk_shadow_recognition_preflight(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
        settings=VoskShadowRecognitionPreflightSettings(enabled=True),
    )
    payload = preflight.to_json_dict()
    payload["pcm_reference_ready"] = False

    result = validate_vosk_shadow_recognition_preflight(payload)

    assert result["accepted"] is False
    assert "pcm_reference_ready_must_be_true" in result["issues"]