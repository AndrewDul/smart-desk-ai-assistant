from __future__ import annotations

import pytest

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)
from modules.runtime.voice_engine_v2.command_asr import build_command_asr_candidate
from modules.runtime.voice_engine_v2.vosk_command_asr_adapter import (
    VOSK_COMMAND_ASR_DISABLED_REASON,
    VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON,
    VOSK_COMMAND_ASR_SEGMENT_TOO_LONG_REASON,
    VoskCommandAsrAdapter,
    VoskCommandAsrAdapterSettings,
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
        "turn_id": "turn-vosk-command-asr",
        "hook": "capture_window_pre_transcription",
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "metadata": metadata,
    }


def test_vosk_command_asr_adapter_is_disabled_by_default() -> None:
    adapter = VoskCommandAsrAdapter()

    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is False
    assert payload["reason"] == "command_asr_disabled"
    assert payload["recognizer_name"] == "vosk_command_asr"
    assert payload["recognizer_enabled"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["asr_reason"] == VOSK_COMMAND_ASR_DISABLED_REASON
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_vosk_command_asr_adapter_requires_pcm_provider_when_enabled() -> None:
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
    )

    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is False
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["reason"] == "command_asr_not_attempted"
    assert payload["asr_reason"] == VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON
    assert payload["transcript"] == ""
    assert payload["raw_pcm_included"] is False


def test_vosk_command_asr_adapter_maps_injected_pcm_recognition_result() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "pokaż pulpit",
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

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is True
    assert payload["reason"] == "command_asr_candidate_present"
    assert payload["recognizer_name"] == "vosk_command_asr"
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_attempted"] is True
    assert payload["recognized"] is True
    assert payload["asr_reason"] == "vosk_command_asr_recognized"
    assert payload["transcript"] == "pokaż pulpit"
    assert payload["normalized_text"] == "pokaz pulpit"
    assert payload["language"] == "pl"
    assert payload["confidence"] == 1.0
    assert payload["raw_pcm_included"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_vosk_command_asr_adapter_keeps_no_match_as_non_candidate() -> None:
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

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is False
    assert payload["reason"] == "not_recognized:vosk_command_asr_not_recognized:no_match"
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_attempted"] is True
    assert payload["recognized"] is False
    assert payload["transcript"] == "unrelated speech"
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_vosk_command_asr_adapter_does_not_attempt_not_ready_segment() -> None:
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )

    candidate = build_command_asr_candidate(
        record=_record(
            candidate=_candidate(
                endpoint_detected=False,
                reason="speech_not_ended_yet",
            )
        ),
        recognizer=adapter,
    )

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is False
    assert payload["segment_present"] is False
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["asr_reason"].startswith("vosk_command_asr_segment_not_ready")


def test_vosk_command_asr_adapter_rejects_segment_that_is_too_long() -> None:
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(
            enabled=True,
            max_audio_duration_ms=1_000.0,
        ),
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )

    candidate = build_command_asr_candidate(
        record=_record(candidate=_candidate()),
        recognizer=adapter,
    )

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is False
    assert payload["recognizer_enabled"] is True
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["asr_reason"] == VOSK_COMMAND_ASR_SEGMENT_TOO_LONG_REASON


def test_vosk_command_asr_adapter_rejects_unsafe_record_before_adapter() -> None:
    adapter = VoskCommandAsrAdapter(
        settings=VoskCommandAsrAdapterSettings(enabled=True),
    )

    with pytest.raises(ValueError, match="must never execute actions"):
        build_command_asr_candidate(
            record=_record(candidate=_candidate(), action_executed=True),
            recognizer=adapter,
        )