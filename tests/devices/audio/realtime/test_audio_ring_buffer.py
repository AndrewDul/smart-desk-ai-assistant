import pytest

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.realtime.ring_buffer import AudioRingBuffer


def _frame(sequence: int, sample_count: int = 1600) -> AudioFrame:
    return AudioFrame(
        pcm=b"\x00\x00" * sample_count,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
        timestamp_monotonic=float(sequence),
        sequence=sequence,
        source="test",
    )


def test_ring_buffer_keeps_recent_audio_by_duration() -> None:
    ring = AudioRingBuffer(
        max_duration_seconds=0.25,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    ring.append(_frame(0))
    ring.append(_frame(1))
    ring.append(_frame(2))
    ring.append(_frame(3))

    frames = ring.snapshot_frames()

    assert [frame.sequence for frame in frames] == [2, 3]
    assert ring.duration_seconds == pytest.approx(0.2)
    assert ring.latest_sequence == 3
    assert ring.oldest_sequence == 2


def test_ring_buffer_returns_frames_since_sequence() -> None:
    ring = AudioRingBuffer(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    ring.append(_frame(0))
    ring.append(_frame(1))
    ring.append(_frame(2))

    frames = ring.frames_since(1)

    assert [frame.sequence for frame in frames] == [1, 2]


def test_ring_buffer_snapshot_pcm_can_limit_recent_duration() -> None:
    ring = AudioRingBuffer(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    ring.append(_frame(0))
    ring.append(_frame(1))
    ring.append(_frame(2))

    pcm = ring.snapshot_pcm(max_duration_seconds=0.15)

    assert pcm == _frame(2).pcm


def test_ring_buffer_rejects_mismatched_audio_format() -> None:
    ring = AudioRingBuffer(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    bad_frame = AudioFrame(
        pcm=b"\x00\x00" * 1600,
        sample_rate=8_000,
        channels=1,
        sample_width_bytes=2,
        timestamp_monotonic=0.0,
        sequence=0,
        source="test",
    )

    with pytest.raises(ValueError, match="sample_rate"):
        ring.append(bad_frame)