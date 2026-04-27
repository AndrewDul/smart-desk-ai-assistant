from __future__ import annotations

import logging
import queue

import numpy as np

from modules.devices.audio.input.faster_whisper.backend.capture_mixin import (
    FasterWhisperCaptureMixin,
)
from modules.devices.audio.realtime import AudioBus


class DummyFasterWhisperCapture(FasterWhisperCaptureMixin):
    LOGGER = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)
        self._realtime_audio_bus_shadow_tap = None
        self._realtime_audio_bus_shadow_tap_enabled = False
        self._realtime_audio_bus_shadow_tap_publish_errors = 0


class BrokenAudioBus:
    def publish_pcm(self, *args, **kwargs) -> None:
        raise RuntimeError("broken audio bus")


def test_faster_whisper_callback_publishes_mono_pcm_to_shadow_bus() -> None:
    backend = DummyFasterWhisperCapture()
    audio_bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
        source_name="test_shadow_tap",
    )

    backend.set_realtime_audio_bus_shadow_tap(audio_bus, enabled=True)

    stereo_input = np.array(
        [
            [1, 100],
            [2, 200],
            [3, 300],
            [4, 400],
        ],
        dtype=np.int16,
    )

    backend._audio_callback(stereo_input, frames=4, time_info=None, status=None)

    assert audio_bus.frame_count == 1

    frame = audio_bus.snapshot_frames()[0]
    assert frame.sample_rate == 16_000
    assert frame.channels == 1
    assert frame.sample_width_bytes == 2
    assert frame.source == "faster_whisper_callback_shadow_tap"
    assert frame.pcm == stereo_input[:, 0].copy().tobytes(order="C")

    queued = backend.audio_queue.get_nowait()
    np.testing.assert_array_equal(queued, stereo_input[:, 0])


def test_faster_whisper_callback_does_not_publish_when_shadow_tap_disabled() -> None:
    backend = DummyFasterWhisperCapture()
    audio_bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    backend.set_realtime_audio_bus_shadow_tap(audio_bus, enabled=False)

    mono_input = np.array([1, 2, 3, 4], dtype=np.int16)

    backend._audio_callback(mono_input, frames=4, time_info=None, status=None)

    assert audio_bus.frame_count == 0

    queued = backend.audio_queue.get_nowait()
    np.testing.assert_array_equal(queued, mono_input)


def test_faster_whisper_callback_shadow_tap_is_fail_open() -> None:
    backend = DummyFasterWhisperCapture()
    backend.set_realtime_audio_bus_shadow_tap(BrokenAudioBus(), enabled=True)

    mono_input = np.array([1, 2, 3, 4], dtype=np.int16)

    backend._audio_callback(mono_input, frames=4, time_info=None, status=None)

    queued = backend.audio_queue.get_nowait()
    np.testing.assert_array_equal(queued, mono_input)
    assert backend._realtime_audio_bus_shadow_tap_publish_errors == 1