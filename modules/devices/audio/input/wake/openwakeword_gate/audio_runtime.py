from __future__ import annotations

import queue
from typing import Any

import numpy as np
import sounddevice as sd

from .helpers import LOGGER, OpenWakeWordGateHelpers


class OpenWakeWordGateAudioRuntime(OpenWakeWordGateHelpers):
    """Audio stream and queue runtime helpers for the wake gate."""

    input_sample_rate: int
    input_blocksize: int
    device: int | str | None
    channels: int
    dtype: str
    device_name: str
    audio_queue: queue.Queue[np.ndarray]
    model: Any
    _stream: sd.InputStream | None
    _resampled_buffer: np.ndarray
    _score_history: list[float]

    def _select_mono_input(self, indata: np.ndarray) -> np.ndarray:
        if indata.ndim != 2:
            return indata.copy()

        if indata.shape[1] == 1:
            return indata[:, 0].copy()

        mode = getattr(self, "wake_channel_mode", "mono_mix")
        configured_index = getattr(self, "wake_channel_index", None)

        if mode == "fixed_channel" and configured_index is not None:
            safe_index = max(0, min(int(configured_index), indata.shape[1] - 1))
            return indata[:, safe_index].copy()

        if mode == "first_channel":
            return indata[:, 0].copy()

        mixed = np.mean(indata.astype(np.float32), axis=1)
        return np.clip(np.rint(mixed), -32768, 32767).astype(np.int16)

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            LOGGER.warning("OpenWakeWord audio callback status: %s", status)

        try:
            mono = self._select_mono_input(indata)

            if mono.dtype != np.int16:
                mono = mono.astype(np.int16, copy=False)

            try:
                self.audio_queue.put_nowait(mono)
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.audio_queue.put_nowait(mono)
                except queue.Full:
                    pass
        except Exception as error:
            LOGGER.warning("OpenWakeWord audio callback error: %s", error)

    def _ensure_stream_open(self) -> None:
        if self._stream is not None:
            return

        stream = sd.InputStream(
            samplerate=self.input_sample_rate,
            blocksize=self.input_blocksize,
            device=self.device,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        stream.start()
        self._stream = stream
        LOGGER.info(
            "OpenWakeWord input stream started: device='%s', sample_rate=%s, blocksize=%s",
            self.device_name,
            self.input_sample_rate,
            self.input_blocksize,
        )

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return

        try:
            stream.stop()
        except Exception as error:
            LOGGER.debug("Wake input stream stop warning: %s", error)

        try:
            stream.close()
        except Exception as error:
            LOGGER.debug("Wake input stream close warning: %s", error)

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _reset_runtime_state(self) -> None:
        self._resampled_buffer = np.array([], dtype=np.int16)
        self._score_history.clear()

        reset_method = getattr(self.model, "reset", None)
        if callable(reset_method):
            try:
                reset_method()
            except Exception as error:
                LOGGER.debug("OpenWakeWord model reset warning: %s", error)


__all__ = ["OpenWakeWordGateAudioRuntime"]