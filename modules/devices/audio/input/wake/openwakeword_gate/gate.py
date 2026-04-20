from __future__ import annotations

import queue
from typing import Any

import numpy as np
import sounddevice as sd

from .helpers import LOGGER
from .listener import OpenWakeWordGateListener


class OpenWakeWordGate(OpenWakeWordGateListener):
    """
    Premium wake-word gate for NeXa based on openWakeWord.

    Goals:
    - stable wake detection without over-triggering on noise
    - safer runtime normalization for aggressive configs
    - persistent input stream to avoid losing short wake utterances between calls
    - strong half-duplex protection while assistant output is active
    """

    MODEL_SAMPLE_RATE = 16000

    _MIN_SAFE_THRESHOLD = 0.16
    _MAX_SAFE_THRESHOLD = 0.92
    _MIN_SAFE_TRIGGER_LEVEL = 2
    _MIN_SAFE_BLOCK_MS = 80
    _MIN_SAFE_VAD_THRESHOLD = 0.0
    _MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS = 0.90
    _MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS = 0.12
    _MIN_SAFE_ENERGY_RMS_THRESHOLD = 0.0030
    _MIN_SAFE_SCORE_SMOOTHING_WINDOW = 3
    _MIN_VOICED_FRAMES_FOR_DIRECT_ACCEPT = 2
    _MIN_VOICED_FRAMES_FOR_STABLE_ACCEPT = 2
    _QUEUE_GET_TIMEOUT_SECONDS = 0.12

    def __init__(
        self,
        *,
        model_path: str = "models/wake/nexa.onnx",
        device_index: int | None = None,
        device_name_contains: str | None = None,
        threshold: float = 0.50,
        trigger_level: int = 2,
        block_ms: int = 80,
        vad_threshold: float = 0.0,
        enable_speex_noise_suppression: bool = False,
        activation_cooldown_seconds: float = 1.25,
        block_release_settle_seconds: float = 0.18,
        energy_rms_threshold: float = 0.0085,
        score_smoothing_window: int = 3,
        wake_channel_mode: str = "mono_mix",
        wake_channel_index: int | None = None,
        debug: bool = False,
    ) -> None:
        self.model_path = self._resolve_project_path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Wake model was not found: {self.model_path}")

        self.model_name = self.model_path.stem.lower().strip()

        self.debug = bool(debug)
        self.enable_speex_noise_suppression = bool(enable_speex_noise_suppression)
        self.wake_channel_mode = self._normalize_channel_mode(wake_channel_mode)
        self.wake_channel_index = self._normalize_channel_index(wake_channel_index)
        self.threshold = self._normalize_threshold(threshold)
        self.trigger_level = self._normalize_trigger_level(trigger_level)
        self.block_ms = self._normalize_block_ms(block_ms)
        self.vad_threshold = self._normalize_vad_threshold(vad_threshold)
        self.activation_cooldown_seconds = self._normalize_activation_cooldown(activation_cooldown_seconds)
        self.block_release_settle_seconds = self._normalize_block_release_settle(
            block_release_settle_seconds
        )
        self.input_unblock_settle_seconds = self.block_release_settle_seconds
        self.energy_rms_threshold = self._normalize_energy_rms_threshold(energy_rms_threshold)
        self.score_smoothing_window = self._normalize_smoothing_window(score_smoothing_window)

        self.min_frames_before_accept = max(self.trigger_level, self._MIN_VOICED_FRAMES_FOR_STABLE_ACCEPT)
        self.debug_print_interval_seconds = 0.30

        self.direct_accept_threshold = self._resolve_direct_accept_threshold(self.threshold)
        self.direct_accept_support_floor = self._resolve_direct_accept_support_floor(self.threshold)
        self.relaxed_hit_floor = self._resolve_relaxed_hit_floor(self.threshold)

        self.audio_coordinator = None
        self.device = self._resolve_input_device(device_index, device_name_contains)

        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.dtype = "int16"
        self.available_input_channels = max(1, int(input_info.get("max_input_channels", 1)))
        self.channels = min(2, self.available_input_channels)
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=24)

        default_input_rate = int(round(float(input_info.get("default_samplerate", self.MODEL_SAMPLE_RATE))))
        self.input_sample_rate = self._resolve_supported_input_sample_rate(default_input_rate)

        self.model_frame_samples = int(self.MODEL_SAMPLE_RATE * (self.block_ms / 1000.0))
        self.frame_hop_samples = max(1, self.model_frame_samples // 2)
        self.input_blocksize = max(1, int(self.input_sample_rate * (self.block_ms / 1000.0)))
        self._resampled_buffer = np.array([], dtype=np.int16)

        self._stream: sd.InputStream | None = None
        self._last_detection_monotonic = 0.0
        self._last_blocked_observed_monotonic = 0.0
        self._last_debug_print_monotonic = 0.0
        self._score_history: list[float] = []

        from openwakeword.model import Model

        self.model = self._build_model(
            Model,
            vad_threshold=self.vad_threshold,
            enable_speex_noise_suppression=self.enable_speex_noise_suppression,
        )

        LOGGER.info(
            "OpenWakeWordGate prepared: model='%s', device='%s', input_rate=%s, "
            "threshold=%.3f, direct_accept_threshold=%.3f, direct_support_floor=%.3f, "
            "relaxed_hit_floor=%.3f, trigger_level=%s, min_frames_before_accept=%s, "
            "block_ms=%s, activation_cooldown=%.2fs, block_release_settle=%.2fs, "
            "energy_rms_threshold=%.4f, smoothing_window=%s, channel_mode='%s', "
            "channel_index=%s, selection_reason='%s', available_inputs='%s'",
            str(self.model_path),
            self.device_name,
            self.input_sample_rate,
            self.threshold,
            self.direct_accept_threshold,
            self.direct_accept_support_floor,
            self.relaxed_hit_floor,
            self.trigger_level,
            self.min_frames_before_accept,
            self.block_ms,
            self.activation_cooldown_seconds,
            self.block_release_settle_seconds,
            self.energy_rms_threshold,
            self.score_smoothing_window,
            self.wake_channel_mode,
            self.wake_channel_index,
            getattr(self, "device_selection_reason", "unknown"),
            getattr(self, "available_input_devices_summary", "unknown"),
        )

    def release_capture_ownership(self) -> bool:
        self._clear_audio_queue()
        self._reset_runtime_state()
        return self._stream is not None

    def close(self) -> None:
        self._clear_audio_queue()
        self._reset_runtime_state()
        self._close_stream()


__all__ = ["OpenWakeWordGate"]