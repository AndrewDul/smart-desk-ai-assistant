from __future__ import annotations

import pytest

from modules.runtime.voice_engine_v2.command_audio_segment import (
    build_command_audio_segment,
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
    full_stt_prevented: bool = False,
    runtime_takeover: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "capture_window_shadow_tap": (
            _capture_window() if capture_window is None else capture_window
        )
    }
    if candidate is not None:
        metadata["endpointing_candidate"] = candidate

    return {
        "turn_id": "turn-segment",
        "hook": "capture_window_pre_transcription",
        "action_executed": action_executed,
        "full_stt_prevented": full_stt_prevented,
        "runtime_takeover": runtime_takeover,
        "metadata": metadata,
    }


def test_command_audio_segment_accepts_ready_candidate_contract() -> None:
    segment = build_command_audio_segment(
        record=_record(candidate=_candidate()),
    )

    payload = segment.to_json_dict()

    assert payload["segment_present"] is True
    assert payload["reason"] == "segment_ready_for_command_recognizer"
    assert payload["turn_id"] == "turn-segment"
    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["pcm_encoding"] == "pcm_s16le"
    assert payload["raw_pcm_included"] is False
    assert payload["sample_rate"] == 16_000
    assert payload["channels"] == 1
    assert payload["sample_width_bytes"] == 2
    assert payload["audio_sample_count"] == 32_000
    assert payload["audio_duration_ms"] == 2000.0
    assert payload["published_frame_count"] == 32
    assert payload["published_byte_count"] == 64_000
    assert payload["endpoint_detected"] is True
    assert payload["readiness_ready"] is True
    assert payload["readiness_reason"] == "ready_for_command_recognition"
    assert payload["frames_processed"] == 47
    assert payload["speech_score_max"] == 0.99
    assert payload["capture_finished_to_publish_start_ms"] == 2.5
    assert payload["capture_finished_to_vad_observed_ms"] == 228.0
    assert payload["capture_window_publish_to_vad_observed_ms"] == 226.0
    assert payload["candidate_reason"] == "endpoint_detected"
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_command_audio_segment_rejects_incomplete_endpoint() -> None:
    segment = build_command_audio_segment(
        record=_record(
            candidate=_candidate(
                endpoint_detected=False,
                reason="speech_not_ended_yet",
            )
        ),
    )

    payload = segment.to_json_dict()

    assert payload["segment_present"] is False
    assert payload["reason"] == "not_ready:not_ready:endpoint_detected"
    assert payload["readiness_ready"] is False
    assert payload["endpoint_detected"] is False


def test_command_audio_segment_rejects_missing_audio_payload_metadata() -> None:
    segment = build_command_audio_segment(
        record=_record(
            candidate=_candidate(),
            capture_window=_capture_window(
                audio_sample_count=0,
                published_byte_count=0,
            ),
        ),
    )

    payload = segment.to_json_dict()

    assert payload["segment_present"] is False
    assert payload["reason"] == "not_ready:audio_sample_count_missing"
    assert payload["audio_sample_count"] == 0
    assert payload["published_byte_count"] == 0


def test_command_audio_segment_derives_duration_from_sample_rate() -> None:
    segment = build_command_audio_segment(
        record=_record(
            candidate=_candidate(),
            capture_window=_capture_window(
                audio_duration_seconds=None,
                sample_rate=16_000,
                audio_sample_count=8_000,
                published_byte_count=16_000,
            ),
        ),
    )

    payload = segment.to_json_dict()

    assert payload["segment_present"] is True
    assert payload["audio_duration_ms"] == 500.0
    assert payload["sample_width_bytes"] == 2


def test_command_audio_segment_raises_on_top_level_action_execution() -> None:
    with pytest.raises(ValueError, match="must never execute actions"):
        build_command_audio_segment(
            record=_record(
                candidate=_candidate(),
                action_executed=True,
            )
        )


def test_command_audio_segment_raises_on_candidate_full_stt_prevention() -> None:
    with pytest.raises(ValueError, match="must never prevent full STT"):
        build_command_audio_segment(
            record=_record(
                candidate=_candidate(full_stt_prevented=True),
            )
        )


def test_command_audio_segment_raises_on_candidate_runtime_takeover() -> None:
    with pytest.raises(ValueError, match="must never take over runtime"):
        build_command_audio_segment(
            record=_record(
                candidate=_candidate(runtime_takeover=True),
            )
        )