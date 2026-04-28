from __future__ import annotations

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)
from modules.runtime.voice_engine_v2.command_asr import build_command_asr_candidate
from modules.runtime.voice_engine_v2.vosk_command_asr_adapter import (
    VoskCommandAsrAdapter,
    VoskCommandAsrAdapterSettings,
)
from modules.runtime.voice_engine_v2.vosk_shadow_asr_result import (
    ASR_RESULT_DISABLED_REASON,
    ASR_RESULT_NOT_ATTEMPTED_REASON,
    ASR_RESULT_NOT_RECOGNIZED_REASON,
    ASR_RESULT_RECOGNIZED_REASON,
    VoskShadowAsrResultSettings,
    build_vosk_shadow_asr_result,
    validate_vosk_shadow_asr_result,
)


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "capture_window_pre_transcription",
        "candidate_present": True,
        "endpoint_detected": True,
        "reason": "endpoint_detected",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "frames_processed": 47,
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _capture_window(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "sample_rate": 16_000,
        "channels": 1,
        "audio_sample_count": 32_000,
        "audio_duration_seconds": 2.0,
        "published_frame_count": 32,
        "published_byte_count": 64_000,
        "capture_finished_to_publish_start_ms": 2.5,
    }
    payload.update(overrides)
    return payload


def _record(
    *,
    candidate: dict[str, object] | None = None,
    capture_window: dict[str, object] | None = None,
    action_executed: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "capture_window_shadow_tap": (
            _capture_window() if capture_window is None else capture_window
        )
    }
    if candidate is not None:
        metadata["endpointing_candidate"] = candidate

    return {
        "turn_id": "turn-vosk-shadow-asr-result",
        "hook": "capture_window_pre_transcription",
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "metadata": metadata,
    }


def test_asr_result_is_disabled_by_default() -> None:
    adapter = VoskCommandAsrAdapter()
    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    result = build_vosk_shadow_asr_result(candidate=candidate)
    payload = result.to_json_dict()

    assert payload["enabled"] is False
    assert payload["result_present"] is False
    assert payload["reason"] == ASR_RESULT_DISABLED_REASON
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["raw_pcm_included"] is False
    assert validate_vosk_shadow_asr_result(result)["accepted"] is True


def test_asr_result_reports_not_attempted_when_pcm_is_unavailable() -> None:
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
    )
    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    result = build_vosk_shadow_asr_result(
        candidate=candidate,
        settings=VoskShadowAsrResultSettings(enabled=True),
    )
    payload = result.to_json_dict()

    assert payload["enabled"] is True
    assert payload["result_present"] is False
    assert payload["reason"] == ASR_RESULT_NOT_ATTEMPTED_REASON
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["pcm_retrieval_performed"] is False
    assert validate_vosk_shadow_asr_result(result)["accepted"] is True


def test_asr_result_wraps_observe_only_recognized_command() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "what time is it",
    )
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
        recognizer=recognizer,
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )
    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    result = build_vosk_shadow_asr_result(
        candidate=candidate,
        settings=VoskShadowAsrResultSettings(enabled=True),
    )
    payload = result.to_json_dict()

    assert payload["enabled"] is True
    assert payload["result_present"] is True
    assert payload["reason"] == ASR_RESULT_RECOGNIZED_REASON
    assert payload["recognizer_name"] == "vosk_command_asr"
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_invocation_performed"] is True
    assert payload["recognition_attempted"] is True
    assert payload["recognized"] is True
    assert payload["command_matched"] is True
    assert payload["transcript"] == "what time is it"
    assert payload["normalized_text"] == "what time is it"
    assert payload["language"] == "en"
    assert payload["confidence"] == 1.0
    assert payload["pcm_retrieval_performed"] is True
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
    assert validate_vosk_shadow_asr_result(result)["accepted"] is True


def test_asr_result_wraps_observe_only_no_match() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "unrelated speech",
    )
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
        recognizer=recognizer,
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )
    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    result = build_vosk_shadow_asr_result(
        candidate=candidate,
        settings=VoskShadowAsrResultSettings(enabled=True),
    )
    payload = result.to_json_dict()

    assert payload["enabled"] is True
    assert payload["result_present"] is True
    assert payload["reason"] == ASR_RESULT_NOT_RECOGNIZED_REASON
    assert payload["recognition_invocation_performed"] is True
    assert payload["recognition_attempted"] is True
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["transcript"] == "unrelated speech"
    assert payload["pcm_retrieval_performed"] is True
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False
    assert validate_vosk_shadow_asr_result(result)["accepted"] is True


def test_asr_result_rejects_unsafe_payload() -> None:
    result = build_vosk_shadow_asr_result(
        candidate={
            "recognizer_name": "vosk_command_asr",
            "recognizer_enabled": True,
            "recognition_attempted": True,
            "recognized": True,
            "candidate_present": True,
            "transcript": "what time is it",
            "raw_pcm_included": True,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        },
        settings=VoskShadowAsrResultSettings(enabled=True),
    )

    payload = result.to_json_dict()

    assert payload["result_present"] is False
    assert payload["reason"] == "unsafe_command_asr_candidate"
    assert payload["raw_pcm_included"] is False
    assert validate_vosk_shadow_asr_result(result)["accepted"] is True


def test_asr_result_validator_rejects_manually_unsafe_result() -> None:
    validation = validate_vosk_shadow_asr_result(
        {
            "result_stage": "vosk_shadow_asr_result",
            "result_version": "vosk_shadow_asr_result_v1",
            "enabled": True,
            "result_present": True,
            "reason": "vosk_shadow_asr_recognized",
            "metadata_key": "vosk_shadow_asr_result",
            "recognizer_name": "vosk_command_asr",
            "recognizer_enabled": True,
            "recognition_invocation_performed": True,
            "recognition_attempted": True,
            "recognized": True,
            "command_matched": True,
            "transcript": "what time is it",
            "normalized_text": "what time is it",
            "language": "en",
            "confidence": 1.0,
            "alternatives": [],
            "raw_pcm_included": False,
            "action_executed": True,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }
    )

    assert validation["accepted"] is False
    assert "action_executed_must_be_false" in validation["issues"]