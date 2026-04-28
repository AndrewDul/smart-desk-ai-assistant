from __future__ import annotations

import pytest

from modules.runtime.voice_engine_v2.command_asr import CommandAsrResult
from modules.runtime.voice_engine_v2.vosk_live_shadow_contract import (
    VOSK_LIVE_SHADOW_DISABLED_REASON,
    VOSK_LIVE_SHADOW_OBSERVED_REASON,
    VOSK_LIVE_SHADOW_RESULT_MISSING_REASON,
    VoskLiveShadowCommandMatch,
    VoskLiveShadowContractResult,
    VoskLiveShadowContractSettings,
    build_disabled_vosk_live_shadow_contract,
    build_vosk_live_shadow_contract,
    validate_vosk_live_shadow_contract_result,
)


def test_disabled_vosk_live_shadow_contract_is_safe_by_default() -> None:
    result = build_disabled_vosk_live_shadow_contract()
    payload = result.to_json_dict()
    validation = validate_vosk_live_shadow_contract_result(result)

    assert validation["accepted"] is True
    assert validation["issues"] == []
    assert payload["enabled"] is False
    assert payload["observed"] is False
    assert payload["reason"] == VOSK_LIVE_SHADOW_DISABLED_REASON
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["faster_whisper_bypass_enabled"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["independent_microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_enabled_contract_waits_without_starting_recognition() -> None:
    result = build_vosk_live_shadow_contract(
        settings=VoskLiveShadowContractSettings(enabled=True),
    )
    payload = result.to_json_dict()
    validation = validate_vosk_live_shadow_contract_result(result)

    assert validation["accepted"] is True
    assert payload["enabled"] is True
    assert payload["observed"] is False
    assert payload["reason"] == VOSK_LIVE_SHADOW_RESULT_MISSING_REASON
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False


def test_enabled_contract_records_injected_observe_only_result() -> None:
    asr_result = CommandAsrResult(
        recognizer_name="vosk_command_asr_shadow",
        recognizer_enabled=True,
        recognition_attempted=True,
        recognized=True,
        reason="command_matched",
        transcript="show desktop",
        normalized_text="show desktop",
        language="en",
        confidence=1.0,
        alternatives=("show desktop",),
    )
    command_match = VoskLiveShadowCommandMatch(
        command_matched=True,
        command_intent_key="visual_shell.show_desktop",
        command_language="en",
        command_matched_phrase="show desktop",
        command_confidence=1.0,
    )

    result = build_vosk_live_shadow_contract(
        settings=VoskLiveShadowContractSettings(enabled=True),
        asr_result=asr_result,
        command_match=command_match,
    )
    payload = result.to_json_dict()
    validation = validate_vosk_live_shadow_contract_result(result)

    assert validation["accepted"] is True
    assert payload["enabled"] is True
    assert payload["observed"] is True
    assert payload["reason"] == VOSK_LIVE_SHADOW_OBSERVED_REASON
    assert payload["recognition_attempted"] is True
    assert payload["recognized"] is True
    assert payload["transcript"] == "show desktop"
    assert payload["command_matched"] is True
    assert payload["command_intent_key"] == "visual_shell.show_desktop"
    assert payload["command_language"] == "en"
    assert payload["action_executed"] is False
    assert payload["runtime_takeover"] is False


def test_disabled_contract_rejects_injected_asr_result() -> None:
    asr_result = CommandAsrResult(
        recognizer_name="vosk_command_asr_shadow",
        recognizer_enabled=True,
        recognition_attempted=True,
        recognized=True,
        reason="command_matched",
        transcript="show desktop",
        normalized_text="show desktop",
        language="en",
    )

    with pytest.raises(ValueError, match="disabled Vosk live shadow contract"):
        build_vosk_live_shadow_contract(asr_result=asr_result)


def test_command_match_requires_intent_language_and_phrase() -> None:
    with pytest.raises(ValueError, match="command_intent_key"):
        VoskLiveShadowCommandMatch(command_matched=True)

    with pytest.raises(ValueError, match="command_language"):
        VoskLiveShadowCommandMatch(
            command_matched=True,
            command_intent_key="visual_shell.show_desktop",
        )

    with pytest.raises(ValueError, match="command_matched_phrase"):
        VoskLiveShadowCommandMatch(
            command_matched=True,
            command_intent_key="visual_shell.show_desktop",
            command_language="en",
        )


def test_contract_rejects_unsafe_flags() -> None:
    with pytest.raises(ValueError, match="must not start microphone stream"):
        VoskLiveShadowContractResult(
            contract_stage="stage",
            contract_version="version",
            enabled=True,
            observed=False,
            reason="unsafe",
            metadata_key="vosk_live_shadow",
            input_source="existing_command_audio_segment",
            recognizer_name="vosk_command_asr_shadow",
            recognizer_enabled=False,
            recognition_attempted=False,
            recognized=False,
            microphone_stream_started=True,
        )


def test_validation_rejects_unsafe_payload_dict() -> None:
    validation = validate_vosk_live_shadow_contract_result(
        {
            "enabled": False,
            "observed": False,
            "recognition_attempted": False,
            "recognized": False,
            "command_matched": False,
            "runtime_integration": False,
            "command_execution_enabled": True,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }
    )

    assert validation["accepted"] is False
    assert "unsafe_flag:command_execution_enabled" in validation["issues"]