from __future__ import annotations

import pytest

from modules.runtime.voice_engine_v2.command_recognition_readiness import (
    build_command_recognition_readiness,
)


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "capture_window_pre_transcription",
        "candidate_present": True,
        "endpoint_detected": True,
        "reason": "endpoint_detected",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "frames_processed": 7,
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _record(
    candidate: dict[str, object],
    *,
    hook: str = "capture_window_pre_transcription",
    action_executed: bool = False,
    full_stt_prevented: bool = False,
    runtime_takeover: bool = False,
) -> dict[str, object]:
    return {
        "hook": hook,
        "action_executed": action_executed,
        "full_stt_prevented": full_stt_prevented,
        "runtime_takeover": runtime_takeover,
        "metadata": {
            "endpointing_candidate": candidate,
        },
    }


def test_command_recognition_readiness_accepts_clean_endpoint_candidate() -> None:
    readiness = build_command_recognition_readiness(
        record=_record(_candidate()),
    )

    payload = readiness.to_json_dict()

    assert payload["ready"] is True
    assert payload["reason"] == "ready_for_command_recognition"
    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["candidate_present"] is True
    assert payload["endpoint_detected"] is True
    assert payload["pre_transcription_hook"] is True
    assert payload["capture_window_source"] is True
    assert payload["before_transcription_stage"] is True
    assert payload["score_ready"] is True
    assert payload["latency_ready"] is True
    assert payload["frames_ready"] is True
    assert payload["safety_ready"] is True
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False


@pytest.mark.parametrize(
    ("candidate_override", "expected_reason"),
    [
        ({"candidate_present": False}, "not_ready:candidate_present"),
        ({"endpoint_detected": False}, "not_ready:endpoint_detected"),
        ({"source": "wrong_source"}, "not_ready:capture_window_source"),
        ({"publish_stage": "after_transcription"}, "not_ready:before_transcription_stage"),
        ({"speech_score_max": 0.1}, "not_ready:score_ready"),
        ({"capture_finished_to_vad_observed_ms": 9999.0}, "not_ready:latency_ready"),
        ({"frames_processed": 0}, "not_ready:frames_ready"),
    ],
)
def test_command_recognition_readiness_rejects_failed_requirements(
    candidate_override: dict[str, object],
    expected_reason: str,
) -> None:
    readiness = build_command_recognition_readiness(
        record=_record(_candidate(**candidate_override)),
    )

    payload = readiness.to_json_dict()

    assert payload["ready"] is False
    assert payload["reason"] == expected_reason


def test_command_recognition_readiness_rejects_wrong_hook() -> None:
    readiness = build_command_recognition_readiness(
        record=_record(
            _candidate(),
            hook="post_capture",
        ),
    )

    payload = readiness.to_json_dict()

    assert payload["ready"] is False
    assert payload["reason"] == "not_ready:pre_transcription_hook"


def test_command_recognition_readiness_fails_closed_on_missing_candidate() -> None:
    readiness = build_command_recognition_readiness(
        record={
            "hook": "capture_window_pre_transcription",
            "metadata": {},
        },
    )

    payload = readiness.to_json_dict()

    assert payload["ready"] is False
    assert payload["reason"] == "not_ready:candidate_present"
    assert payload["candidate_present"] is False
    assert payload["endpoint_detected"] is False


def test_command_recognition_readiness_raises_if_top_level_action_was_executed() -> None:
    with pytest.raises(ValueError, match="must never execute actions"):
        build_command_recognition_readiness(
            record=_record(
                _candidate(),
                action_executed=True,
            ),
        )


def test_command_recognition_readiness_raises_if_candidate_prevented_full_stt() -> None:
    with pytest.raises(ValueError, match="must never prevent full STT"):
        build_command_recognition_readiness(
            record=_record(
                _candidate(full_stt_prevented=True),
            ),
        )


def test_command_recognition_readiness_raises_if_candidate_took_over_runtime() -> None:
    with pytest.raises(ValueError, match="must never take over runtime"):
        build_command_recognition_readiness(
            record=_record(
                _candidate(runtime_takeover=True),
            ),
        )