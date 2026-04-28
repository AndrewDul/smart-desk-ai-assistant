from __future__ import annotations

import pytest

from modules.runtime.voice_engine_v2.command_asr import (
    DISABLED_COMMAND_ASR_REASON,
    CommandAsrResult,
    DisabledCommandAsrRecognizer,
    NullCommandAsrRecognizer,
    build_disabled_command_asr_candidate,
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
        "turn_id": "turn-command-asr",
        "hook": "capture_window_pre_transcription",
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "metadata": metadata,
    }


def test_disabled_command_asr_recognizer_returns_safe_noop_result() -> None:
    command_asr_candidate = build_disabled_command_asr_candidate(
        record=_record(candidate=_candidate()),
    )

    payload = command_asr_candidate.to_json_dict()

    assert payload["contract_stage"] == "disabled_command_asr_contract"
    assert payload["contract_present"] is True
    assert payload["candidate_present"] is False
    assert payload["reason"] == DISABLED_COMMAND_ASR_REASON
    assert payload["turn_id"] == "turn-command-asr"
    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["segment_present"] is True
    assert payload["segment_reason"] == "segment_ready_for_command_recognizer"
    assert payload["segment_audio_duration_ms"] == 2000.0
    assert payload["segment_audio_sample_count"] == 32_000
    assert payload["segment_published_byte_count"] == 64_000
    assert payload["segment_sample_rate"] == 16_000
    assert payload["segment_pcm_encoding"] == "pcm_s16le"
    assert payload["recognizer_name"] == "disabled_command_asr"
    assert payload["recognizer_enabled"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["asr_reason"] == DISABLED_COMMAND_ASR_REASON
    assert payload["transcript"] == ""
    assert payload["normalized_text"] == ""
    assert payload["language"] is None
    assert payload["confidence"] is None
    assert payload["alternatives"] == []
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_null_command_asr_recognizer_aliases_disabled_recognizer() -> None:
    recognizer = NullCommandAsrRecognizer()

    assert isinstance(recognizer, DisabledCommandAsrRecognizer)
    assert recognizer.recognizer_enabled is False
    assert recognizer.recognizer_name == "disabled_command_asr"


def test_disabled_command_asr_candidate_waits_for_ready_segment() -> None:
    command_asr_candidate = build_disabled_command_asr_candidate(
        record=_record(
            candidate=_candidate(
                endpoint_detected=False,
                reason="speech_not_ended_yet",
            )
        ),
    )

    payload = command_asr_candidate.to_json_dict()

    assert payload["contract_present"] is True
    assert payload["candidate_present"] is False
    assert payload["segment_present"] is False
    assert payload["reason"] == "not_ready:not_ready:endpoint_detected"
    assert payload["recognizer_enabled"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False


def test_disabled_command_asr_result_rejects_attempted_disabled_recognition() -> None:
    with pytest.raises(ValueError, match="Disabled command ASR result cannot attempt"):
        CommandAsrResult(
            recognizer_name="disabled_command_asr",
            recognizer_enabled=False,
            recognition_attempted=True,
            recognized=False,
            reason="invalid",
        )


def test_disabled_command_asr_result_rejects_recognition_without_transcript() -> None:
    with pytest.raises(ValueError, match="cannot be recognized without transcript"):
        CommandAsrResult(
            recognizer_name="future_vosk_command_asr",
            recognizer_enabled=True,
            recognition_attempted=True,
            recognized=True,
            reason="recognized",
            transcript="",
        )


def test_disabled_command_asr_candidate_raises_on_unsafe_segment() -> None:
    with pytest.raises(ValueError, match="must never execute actions"):
        build_disabled_command_asr_candidate(
            record=_record(candidate=_candidate(), action_executed=True)
        )