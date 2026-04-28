from __future__ import annotations

import pytest
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
        self._realtime_audio_bus_shadow_tap = None
        self._realtime_audio_bus_shadow_tap_enabled = False
        self._realtime_audio_bus_shadow_tap_publish_errors = 0


def test_realtime_audio_bus_shadow_tap_records_float_to_int16_collapse() -> None:
    harness = _Harness()
    audio_bus = _FakeAudioBus()
    harness.set_realtime_audio_bus_shadow_tap(audio_bus, enabled=True)

    raw_mono = np.array([0.0, 0.5, -0.5, 0.25], dtype=np.float32)
    converted_mono = raw_mono.astype(np.int16, copy=False)

    harness._publish_realtime_audio_bus_shadow_tap(
        raw_mono=raw_mono,
        converted_mono=converted_mono,
        frames=4,
        time_info={
            "inputBufferAdcTime": 10.0,
            "currentTime": 10.1,
            "outputBufferDacTime": 10.2,
        },
        callback_status=None,
        callback_started_at=42.25,
    )

    snapshot = harness.realtime_audio_bus_shadow_tap_diagnostics_snapshot()
    last_record = snapshot["last_record"]

    assert audio_bus.published
    assert audio_bus.published[0]["timestamp_monotonic"] == 42.25
    assert audio_bus.published[0]["source"] == "faster_whisper_callback_shadow_tap"

    assert snapshot["enabled"] is True
    assert snapshot["attached"] is True
    assert snapshot["publish_errors"] == 0
    assert snapshot["recent_record_count"] == 1

    assert last_record["publish_status"] == "published"
    assert last_record["frames_argument"] == 4
    assert last_record["published_byte_count"] == converted_mono.nbytes
    assert last_record["conversion_warning"] == (
        "float_audio_cast_to_int16_without_scaling"
    )

    assert last_record["raw_profile"]["dtype"] == "float32"
    assert last_record["raw_profile"]["normalized_peak_abs"] == pytest.approx(0.5)
    assert last_record["converted_profile"]["dtype"] == "int16"
    assert last_record["converted_profile"]["raw_peak_abs"] <= 1.0


def test_realtime_audio_bus_shadow_tap_records_clean_int16_pcm() -> None:
    harness = _Harness()
    audio_bus = _FakeAudioBus()
    harness.set_realtime_audio_bus_shadow_tap(audio_bus, enabled=True)

    raw_mono = np.array([0, 1200, -1200, 300], dtype=np.int16)

    harness._publish_realtime_audio_bus_shadow_tap(
        raw_mono=raw_mono,
        converted_mono=raw_mono,
        frames=4,
        time_info=None,
        callback_status=None,
        callback_started_at=11.0,
    )

    snapshot = harness.realtime_audio_bus_shadow_tap_diagnostics_snapshot()
    last_record = snapshot["last_record"]

    assert audio_bus.published
    assert audio_bus.published[0]["pcm"] == raw_mono.tobytes(order="C")
    assert audio_bus.published[0]["timestamp_monotonic"] == 11.0

    assert last_record["publish_status"] == "published"
    assert last_record["conversion_warning"] == ""
    assert last_record["raw_profile"]["dtype"] == "int16"
    assert last_record["converted_profile"]["dtype"] == "int16"
    assert last_record["converted_profile"]["normalized_peak_abs"] == pytest.approx(
        round(1200 / 32768.0, 6)
    )