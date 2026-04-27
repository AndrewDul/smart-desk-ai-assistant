import pytest

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad.silero_vad_engine import SileroVadEngine


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


def test_silero_vad_engine_wraps_score_provider_result() -> None:
    engine = SileroVadEngine(
        score_provider=lambda frame: 0.84,
        speech_threshold=0.5,
    )

    decision = engine.score_frame(_frame(sequence=7))

    assert decision.is_speech is True
    assert decision.score == 0.84
    assert decision.threshold == 0.5
    assert decision.frame_sequence == 7


def test_silero_vad_engine_marks_silence_below_threshold() -> None:
    engine = SileroVadEngine(
        score_provider=lambda frame: 0.12,
        speech_threshold=0.5,
    )

    decision = engine.score_frame(_frame())

    assert decision.is_speech is False


def test_silero_vad_engine_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="speech_threshold"):
        SileroVadEngine(
            score_provider=lambda frame: 0.5,
            speech_threshold=1.5,
        )


def test_silero_vad_engine_rejects_invalid_score_provider_output() -> None:
    engine = SileroVadEngine(
        score_provider=lambda frame: 2.0,
        speech_threshold=0.5,
    )

    with pytest.raises(ValueError, match="score_provider"):
        engine.score_frame(_frame())