from __future__ import annotations

import numpy as np

from modules.devices.audio.input.faster_whisper.backend.capture_mixin import (
    FasterWhisperCaptureMixin,
)


class _FakeLogger:
    def warning(self, *_args, **_kwargs) -> None:
        return None


class _FakeAudioBus:
    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    def publish_pcm(
        self,
        pcm: bytes,
        *,
        timestamp_monotonic: float,
        source: str,
    ) -> None:
        self.published.append(
            {
                "pcm": pcm,
                "timestamp_monotonic": timestamp_monotonic,
                "source": source,
            }
        )


class _Harness(FasterWhisperCaptureMixin):
    LOGGER = _FakeLogger()

    def __init__(self) -> None:
        self.sample_rate = 16_000
        self.blocksize = 4
        self._realtime_audio_bus_shadow_tap = None
        self._realtime_audio_bus_shadow_tap_enabled = False
        self._realtime_audio_bus_shadow_tap_publish_errors = 0


def test_capture_window_shadow_tap_scales_float_audio_to_int16_pcm() -> None:
    harness = _Harness()
    audio_bus = _FakeAudioBus()
    harness.set_realtime_audio_bus_shadow_tap(audio_bus, enabled=True)

    audio = np.array(
        [0.0, 0.5, -0.5, 0.25, 0.0, 0.1, -0.1, 0.0],
        dtype=np.float32,
    )

    record = harness.publish_realtime_audio_bus_capture_window_shadow_tap(
        audio,
        capture_finished_at_monotonic=10.0,
        transcription_finished_at_monotonic=11.0,
    )

    assert record["enabled"] is True
    assert record["attached"] is True
    assert record["published"] is True
    assert record["reason"] == "published"
    assert record["source"] == "faster_whisper_capture_window_shadow_tap"
    assert record["conversion_reason"] == "float_scaled_from_float32_to_int16"
    assert record["published_frame_count"] == 2
    assert record["published_byte_count"] == 16
    assert record["audio_sample_count"] == 8
    assert record["chunk_sample_count"] == 4

    assert len(audio_bus.published) == 2
    assert {item["source"] for item in audio_bus.published} == {
        "faster_whisper_capture_window_shadow_tap"
    }

    first_pcm = audio_bus.published[0]["pcm"]
    first_samples = np.frombuffer(first_pcm, dtype=np.int16)

    assert first_samples[0] == 0
    assert first_samples[1] > 16000
    assert first_samples[2] < -16000
    assert first_samples[3] > 8000

    first_timestamp = float(audio_bus.published[0]["timestamp_monotonic"])
    second_timestamp = float(audio_bus.published[1]["timestamp_monotonic"])

    assert second_timestamp > first_timestamp


def test_capture_window_shadow_tap_returns_disabled_record_when_tap_disabled() -> None:
    harness = _Harness()

    record = harness.publish_realtime_audio_bus_capture_window_shadow_tap(
        np.array([0.5], dtype=np.float32),
        capture_finished_at_monotonic=10.0,
        transcription_finished_at_monotonic=11.0,
    )

    assert record["enabled"] is False
    assert record["attached"] is False
    assert record["published"] is False
    assert record["reason"] == "shadow_tap_disabled"
    assert record["source"] == "faster_whisper_capture_window_shadow_tap"