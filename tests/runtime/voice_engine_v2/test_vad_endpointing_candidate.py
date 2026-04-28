from __future__ import annotations

from modules.runtime.voice_engine_v2.vad_endpointing_candidate import (
    build_vad_endpointing_candidate,
)


def test_vad_endpointing_candidate_detects_complete_endpoint() -> None:
    candidate = build_vad_endpointing_candidate(
        hook="capture_window_pre_transcription",
        vad_shadow={
            "observed": True,
            "frames_processed": 7,
            "speech_started_count": 1,
            "speech_ended_count": 1,
            "speech_frame_count": 3,
            "silence_frame_count": 4,
            "speech_score_max": 0.95,
            "speech_score_avg": 0.48,
            "speech_score_over_threshold_count": 3,
            "latest_event_type": "speech_ended",
            "pcm_profile_signal_level": "high",
            "pcm_profile_rms": 0.08,
            "pcm_profile_peak_abs": 0.71,
            "frame_source_counts": {
                "faster_whisper_capture_window_shadow_tap": 7,
            },
            "observation_completed_monotonic": 10.25,
            "latest_speech_end_to_observe_ms": 180.0,
        },
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "capture_finished_at_monotonic": 10.0,
            "publish_started_at_monotonic": 10.01,
            "capture_finished_to_publish_start_ms": 10.0,
        },
    )

    payload = candidate.to_json_dict()

    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["candidate_present"] is True
    assert payload["endpoint_detected"] is True
    assert payload["reason"] == "endpoint_detected"
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["frames_processed"] == 7
    assert payload["speech_started"] is True
    assert payload["speech_ended"] is True
    assert payload["speech_score_max"] == 0.95
    assert payload["pcm_profile_signal_level"] == "high"
    assert payload["capture_window_publish_to_vad_observed_ms"] == 240.0
    assert payload["capture_finished_to_vad_observed_ms"] == 250.0
    assert payload["latest_speech_end_to_observe_ms"] == 180.0
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


def test_vad_endpointing_candidate_marks_incomplete_endpoint() -> None:
    candidate = build_vad_endpointing_candidate(
        hook="capture_window_pre_transcription",
        vad_shadow={
            "observed": True,
            "frames_processed": 4,
            "speech_started_count": 1,
            "speech_ended_count": 0,
            "speech_frame_count": 4,
            "silence_frame_count": 0,
            "speech_score_max": 0.99,
            "frame_source_counts": {
                "faster_whisper_capture_window_shadow_tap": 4,
            },
            "observation_completed_monotonic": 20.1,
        },
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "capture_finished_at_monotonic": 20.0,
            "publish_started_at_monotonic": 20.02,
        },
    )

    payload = candidate.to_json_dict()

    assert payload["candidate_present"] is True
    assert payload["endpoint_detected"] is False
    assert payload["reason"] == "speech_not_ended_yet"
    assert payload["speech_started"] is True
    assert payload["speech_ended"] is False
    assert payload["capture_window_publish_to_vad_observed_ms"] == 80.0
    assert payload["capture_finished_to_vad_observed_ms"] == 100.0