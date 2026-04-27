import pytest

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad.vad_events import (
    VadDecision,
    VadEvent,
    VadEventType,
)


def _frame(sequence: int = 0) -> AudioFrame:
    return AudioFrame(
        pcm=b"\x00\x00" * 1600,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
        timestamp_monotonic=float(sequence),
        sequence=sequence,
        source="test",
    )


def test_vad_decision_from_score_marks_speech_above_threshold() -> None:
    decision = VadDecision.from_score(
        frame=_frame(sequence=4),
        score=0.72,
        threshold=0.5,
    )

    assert decision.is_speech is True
    assert decision.score == 0.72
    assert decision.threshold == 0.5
    assert decision.frame_sequence == 4
    assert decision.frame_duration_seconds == pytest.approx(0.1)


def test_vad_decision_from_score_marks_silence_below_threshold() -> None:
    decision = VadDecision.from_score(
        frame=_frame(sequence=5),
        score=0.2,
        threshold=0.5,
    )

    assert decision.is_speech is False


def test_vad_decision_rejects_invalid_score() -> None:
    with pytest.raises(ValueError, match="score"):
        VadDecision(
            is_speech=True,
            score=1.2,
            threshold=0.5,
            timestamp_monotonic=0.0,
            frame_sequence=0,
            frame_duration_seconds=0.1,
        )


def test_vad_event_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="speech_duration_seconds"):
        VadEvent(
            event_type=VadEventType.SPEECH_ENDED,
            timestamp_monotonic=1.0,
            frame_sequence=1,
            speech_duration_seconds=-0.1,
        )