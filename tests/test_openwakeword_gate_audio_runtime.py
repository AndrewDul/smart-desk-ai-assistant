from __future__ import annotations

import queue
import unittest

import numpy as np

from modules.devices.audio.input.wake.openwakeword_gate.audio_runtime import OpenWakeWordGateAudioRuntime


class _AudioRuntimeProbe(OpenWakeWordGateAudioRuntime):
    def __init__(self, *, wake_channel_mode: str, wake_channel_index: int | None = None) -> None:
        self.wake_channel_mode = wake_channel_mode
        self.wake_channel_index = wake_channel_index
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)


class OpenWakeWordGateAudioRuntimeTests(unittest.TestCase):
    def test_select_mono_input_uses_mean_mix_by_default(self) -> None:
        runtime = _AudioRuntimeProbe(wake_channel_mode="mono_mix")
        indata = np.array(
            [
                [1000, 3000],
                [2000, 4000],
                [3000, 5000],
            ],
            dtype=np.int16,
        )

        mono = runtime._select_mono_input(indata)

        self.assertTrue(np.array_equal(mono, np.array([2000, 3000, 4000], dtype=np.int16)))

    def test_select_mono_input_can_use_fixed_channel(self) -> None:
        runtime = _AudioRuntimeProbe(wake_channel_mode="fixed_channel", wake_channel_index=1)
        indata = np.array(
            [
                [1000, 3000],
                [2000, 4000],
                [3000, 5000],
            ],
            dtype=np.int16,
        )

        mono = runtime._select_mono_input(indata)

        self.assertTrue(np.array_equal(mono, np.array([3000, 4000, 5000], dtype=np.int16)))

    def test_audio_callback_enqueues_mixed_mono_audio(self) -> None:
        runtime = _AudioRuntimeProbe(wake_channel_mode="mono_mix")
        indata = np.array(
            [
                [1000, 3000],
                [2000, 4000],
            ],
            dtype=np.int16,
        )

        runtime._audio_callback(indata, frames=2, time_info=None, status=None)

        mono = runtime.audio_queue.get_nowait()
        self.assertTrue(np.array_equal(mono, np.array([2000, 3000], dtype=np.int16)))


if __name__ == "__main__":
    unittest.main()