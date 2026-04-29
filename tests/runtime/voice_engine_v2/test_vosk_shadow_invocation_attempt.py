from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_invocation_attempt import (
    INVOCATION_ATTEMPT_DISABLED_REASON,
    INVOCATION_ATTEMPT_PREFLIGHT_MISSING_REASON,
    INVOCATION_ATTEMPT_READY_BLOCKED_REASON,
    INVOCATION_ATTEMPT_UNSAFE_DEPENDENCY_REASON,
    VoskShadowInvocationAttemptSettings,
    build_vosk_shadow_invocation_attempt,
    validate_vosk_shadow_invocation_attempt,
)


def _preflight(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "preflight_stage": "vosk_shadow_recognition_preflight",
        "preflight_version": "vosk_shadow_recognition_preflight_v1",
        "enabled": True,
        "preflight_ready": True,
        "recognition_allowed": False,
        "recognition_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "metadata_key": "vosk_shadow_recognition_preflight",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognizer_name": "vosk_command_asr",
        "audio_sample_count": 32000,
        "published_byte_count": 64000,
        "sample_rate": 16000,
        "pcm_encoding": "pcm_s16le",
        "pcm_retrieval_allowed": False,
        "pcm_retrieval_performed": False,
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "recognized": False,
        "command_matched": False,
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


def test_invocation_attempt_is_disabled_by_default() -> None:
    attempt = build_vosk_shadow_invocation_attempt(
        hook="capture_window_pre_transcription",
        metadata={"vosk_shadow_recognition_preflight": _preflight()},
    )

    assert attempt.enabled is False
    assert attempt.attempt_ready is False
    assert attempt.invocation_allowed is False
    assert attempt.invocation_blocked is True
    assert attempt.reason == INVOCATION_ATTEMPT_DISABLED_REASON
    assert attempt.recognition_attempted is False
    assert attempt.action_executed is False
    assert validate_vosk_shadow_invocation_attempt(attempt)["accepted"] is True


def test_invocation_attempt_requires_recognition_preflight() -> None:
    attempt = build_vosk_shadow_invocation_attempt(
        hook="capture_window_pre_transcription",
        metadata={},
        settings=VoskShadowInvocationAttemptSettings(enabled=True),
    )

    assert attempt.enabled is True
    assert attempt.attempt_ready is False
    assert attempt.invocation_allowed is False
    assert attempt.invocation_blocked is True
    assert attempt.reason == INVOCATION_ATTEMPT_PREFLIGHT_MISSING_REASON
    assert attempt.preflight_present is False
    assert validate_vosk_shadow_invocation_attempt(attempt)["accepted"] is True


def test_invocation_attempt_becomes_ready_but_blocked_after_safe_preflight() -> None:
    attempt = build_vosk_shadow_invocation_attempt(
        hook="capture_window_pre_transcription",
        metadata={"vosk_shadow_recognition_preflight": _preflight()},
        settings=VoskShadowInvocationAttemptSettings(enabled=True),
    )
    payload = attempt.to_json_dict()

    assert payload["attempt_stage"] == "vosk_shadow_invocation_attempt"
    assert payload["attempt_version"] == "vosk_shadow_invocation_attempt_v1"
    assert payload["enabled"] is True
    assert payload["attempt_ready"] is True
    assert payload["invocation_allowed"] is False
    assert payload["invocation_blocked"] is True
    assert payload["reason"] == INVOCATION_ATTEMPT_READY_BLOCKED_REASON
    assert payload["metadata_key"] == "vosk_shadow_invocation_attempt"
    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["recognizer_name"] == "vosk_command_asr"
    assert payload["preflight_present"] is True
    assert payload["preflight_ready"] is True
    assert payload["preflight_recognition_blocked"] is True
    assert payload["audio_sample_count"] == 32000
    assert payload["published_byte_count"] == 64000
    assert payload["sample_rate"] == 16000
    assert payload["pcm_encoding"] == "pcm_s16le"
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["result_present"] is False
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["runtime_takeover"] is False
    assert validate_vosk_shadow_invocation_attempt(payload)["accepted"] is True


def test_invocation_attempt_blocks_unsafe_preflight_dependency() -> None:
    attempt = build_vosk_shadow_invocation_attempt(
        hook="capture_window_pre_transcription",
        metadata={
            "vosk_shadow_recognition_preflight": _preflight(
                recognition_attempted=True,
            )
        },
        settings=VoskShadowInvocationAttemptSettings(enabled=True),
    )

    assert attempt.enabled is True
    assert attempt.attempt_ready is False
    assert attempt.reason == INVOCATION_ATTEMPT_UNSAFE_DEPENDENCY_REASON
    assert attempt.recognition_attempted is False
    assert attempt.action_executed is False
    assert attempt.runtime_takeover is False
    assert validate_vosk_shadow_invocation_attempt(attempt)["accepted"] is True


def test_invocation_attempt_validator_rejects_unsafe_payload() -> None:
    attempt = build_vosk_shadow_invocation_attempt(
        hook="capture_window_pre_transcription",
        metadata={"vosk_shadow_recognition_preflight": _preflight()},
        settings=VoskShadowInvocationAttemptSettings(enabled=True),
    ).to_json_dict()

    attempt["recognition_attempted"] = True
    attempt["action_executed"] = True

    result = validate_vosk_shadow_invocation_attempt(attempt)

    assert result["accepted"] is False
    assert "recognition_attempted_must_be_false" in result["issues"]
    assert "action_executed_must_be_false" in result["issues"]
