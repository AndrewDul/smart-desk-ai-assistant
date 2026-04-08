from __future__ import annotations

import logging
import queue
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


LOGGER = logging.getLogger(__name__)


class OpenWakeWordGate:
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
        debug: bool = False,
    ) -> None:
        self.model_path = self._resolve_project_path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Wake model was not found: {self.model_path}")

        self.model_name = self.model_path.stem.lower().strip()

        self.debug = bool(debug)
        self.enable_speex_noise_suppression = bool(enable_speex_noise_suppression)

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

        self.audio_coordinator: AssistantAudioCoordinator | None = None
        self.device = self._resolve_input_device(device_index, device_name_contains)

        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.dtype = "int16"
        self.channels = 1
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
            "energy_rms_threshold=%.4f, smoothing_window=%s",
            self.model_path,
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
        )

    @classmethod
    def _normalize_threshold(cls, raw_value: float) -> float:
        value = float(raw_value)
        if value < cls._MIN_SAFE_THRESHOLD:
            LOGGER.warning(
                "Wake threshold %.3f is too aggressive; promoting to safe minimum %.3f.",
                value,
                cls._MIN_SAFE_THRESHOLD,
            )
            return cls._MIN_SAFE_THRESHOLD
        if value > cls._MAX_SAFE_THRESHOLD:
            LOGGER.warning(
                "Wake threshold %.3f is too restrictive; lowering to %.3f.",
                value,
                cls._MAX_SAFE_THRESHOLD,
            )
            return cls._MAX_SAFE_THRESHOLD
        return value

    @classmethod
    def _normalize_trigger_level(cls, raw_value: int) -> int:
        value = int(raw_value)
        if value < cls._MIN_SAFE_TRIGGER_LEVEL:
            LOGGER.warning(
                "Wake trigger level %s is too low; promoting to %s.",
                value,
                cls._MIN_SAFE_TRIGGER_LEVEL,
            )
            return cls._MIN_SAFE_TRIGGER_LEVEL
        return value

    @classmethod
    def _normalize_block_ms(cls, raw_value: int) -> int:
        value = int(raw_value)
        if value < cls._MIN_SAFE_BLOCK_MS:
            LOGGER.warning(
                "Wake block size %sms is too low; promoting to %sms.",
                value,
                cls._MIN_SAFE_BLOCK_MS,
            )
            return cls._MIN_SAFE_BLOCK_MS
        return value

    @classmethod
    def _normalize_vad_threshold(cls, raw_value: float) -> float:
        value = float(raw_value)
        if value < cls._MIN_SAFE_VAD_THRESHOLD:
            return cls._MIN_SAFE_VAD_THRESHOLD
        return value

    @classmethod
    def _normalize_activation_cooldown(cls, raw_value: float) -> float:
        value = float(raw_value)
        if value < cls._MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS:
            LOGGER.warning(
                "Wake activation cooldown %.2fs is too short; promoting to %.2fs.",
                value,
                cls._MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS,
            )
            return cls._MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS
        return value

    @classmethod
    def _normalize_block_release_settle(cls, raw_value: float) -> float:
        value = float(raw_value)
        if value < cls._MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS:
            LOGGER.warning(
                "Wake unblock settle %.2fs is too short; promoting to %.2fs.",
                value,
                cls._MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS,
            )
            return cls._MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS
        return value

    @classmethod
    def _normalize_energy_rms_threshold(cls, raw_value: float) -> float:
        value = float(raw_value)
        if value < cls._MIN_SAFE_ENERGY_RMS_THRESHOLD:
            LOGGER.warning(
                "Wake energy RMS threshold %.4f is too low; promoting to %.4f.",
                value,
                cls._MIN_SAFE_ENERGY_RMS_THRESHOLD,
            )
            return cls._MIN_SAFE_ENERGY_RMS_THRESHOLD
        return value

    @classmethod
    def _normalize_smoothing_window(cls, raw_value: int) -> int:
        value = int(raw_value)
        if value < cls._MIN_SAFE_SCORE_SMOOTHING_WINDOW:
            LOGGER.warning(
                "Wake smoothing window %s is too small; promoting to %s.",
                value,
                cls._MIN_SAFE_SCORE_SMOOTHING_WINDOW,
            )
            return cls._MIN_SAFE_SCORE_SMOOTHING_WINDOW
        return value

    @staticmethod
    def _resolve_direct_accept_threshold(threshold: float) -> float:
        return min(0.95, max(0.38, threshold + 0.12))

    @staticmethod
    def _resolve_direct_accept_support_floor(threshold: float) -> float:
        return max(0.12, min(threshold, threshold * 0.85))

    @staticmethod
    def _resolve_relaxed_hit_floor(threshold: float) -> float:
        return max(0.08, min(threshold, threshold * 0.62))

    @staticmethod
    def _discover_project_root() -> Path:
        current = Path(__file__).resolve()
        for candidate in current.parents:
            if (candidate / "modules").exists() and (candidate / "config").exists():
                return candidate
        return current.parents[6]

    @classmethod
    def _resolve_project_path(cls, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return cls._discover_project_root() / candidate

    def set_audio_coordinator(self, audio_coordinator: AssistantAudioCoordinator | None) -> None:
        self.audio_coordinator = audio_coordinator

    def _input_blocked_by_assistant_output(self) -> bool:
        if self.audio_coordinator is None:
            return False

        try:
            blocked = bool(self.audio_coordinator.input_blocked())
        except Exception:
            return False

        if blocked:
            self._last_blocked_observed_monotonic = time.monotonic()

        return blocked

    def _recently_unblocked(self) -> bool:
        if self._last_blocked_observed_monotonic <= 0.0:
            return False
        return (time.monotonic() - self._last_blocked_observed_monotonic) < self.block_release_settle_seconds

    def _in_activation_cooldown(self) -> bool:
        if self._last_detection_monotonic <= 0.0:
            return False
        return (time.monotonic() - self._last_detection_monotonic) < self.activation_cooldown_seconds

    def _resolve_input_device(
        self,
        device_index: int | None,
        device_name_contains: str | None,
    ) -> int | str | None:
        if device_name_contains:
            wanted = device_name_contains.lower()
            for index, device in enumerate(sd.query_devices()):
                if device.get("max_input_channels", 0) < 1:
                    continue
                if wanted in str(device["name"]).lower():
                    return index
            raise ValueError(f"Input device containing '{device_name_contains}' was not found.")
        return device_index

    def _resolve_supported_input_sample_rate(self, preferred_rate: int) -> int:
        candidates = [preferred_rate, self.MODEL_SAMPLE_RATE, 32000, 44100, 48000]
        seen: set[int] = set()

        for rate in candidates:
            if not rate or rate in seen:
                continue
            seen.add(rate)
            try:
                sd.check_input_settings(
                    device=self.device,
                    channels=self.channels,
                    dtype=self.dtype,
                    samplerate=rate,
                )
                return rate
            except Exception:
                continue

        raise RuntimeError(
            f"No supported sample rate found for openWakeWord gate on device '{self.device_name}'."
        )

    def _build_model(
        self,
        model_class: type,
        *,
        vad_threshold: float,
        enable_speex_noise_suppression: bool,
    ) -> Any:
        modern_kwargs: dict[str, Any] = {
            "wakeword_models": [str(self.model_path)],
            "inference_framework": "onnx",
        }

        if vad_threshold > 0.0:
            modern_kwargs["vad_threshold"] = vad_threshold

        if enable_speex_noise_suppression:
            modern_kwargs["enable_speex_noise_suppression"] = True

        try:
            model = model_class(**modern_kwargs)
            LOGGER.info("OpenWakeWordGate using modern model API.")
            return model
        except TypeError as error:
            LOGGER.info("OpenWakeWord modern API unavailable, falling back to legacy API: %s", error)

        legacy_kwargs: dict[str, Any] = {
            "wakeword_model_paths": [str(self.model_path)],
        }
        if vad_threshold > 0.0:
            legacy_kwargs["vad_threshold"] = vad_threshold

        try:
            model = model_class(**legacy_kwargs)
            LOGGER.info("OpenWakeWordGate using legacy 0.4.x model API.")
            return model
        except TypeError:
            legacy_kwargs.pop("vad_threshold", None)
            model = model_class(**legacy_kwargs)
            LOGGER.info("OpenWakeWordGate using minimal legacy model API.")
            return model

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            LOGGER.warning("OpenWakeWord audio callback status: %s", status)

        try:
            if indata.ndim == 2:
                mono = indata[:, 0].copy()
            else:
                mono = indata.copy()

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

    def _extract_numeric(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float, np.integer, np.floating)):
            return float(value)
        if isinstance(value, np.ndarray):
            if value.size == 0:
                return None
            flattened = value.reshape(-1)
            return float(flattened[-1])
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            for item in reversed(value):
                numeric = self._extract_numeric(item)
                if numeric is not None:
                    return numeric
            return None
        if isinstance(value, dict):
            if "score" in value:
                numeric = self._extract_numeric(value["score"])
                if numeric is not None:
                    return numeric

            preferred_keys: list[Any] = []
            for key in value.keys():
                key_str = str(key).lower()
                if key_str == self.model_name:
                    preferred_keys.append(key)
                elif self.model_name in key_str:
                    preferred_keys.append(key)

            for key in preferred_keys:
                numeric = self._extract_numeric(value[key])
                if numeric is not None:
                    return numeric

            for nested in value.values():
                numeric = self._extract_numeric(nested)
                if numeric is not None:
                    return numeric
            return None
        return None

    def _extract_score(self, prediction: Any) -> float:
        numeric = self._extract_numeric(prediction)
        if numeric is None:
            if self.debug:
                print(f"OpenWakeWord raw prediction (unparsed): {prediction!r}")
            return 0.0
        return float(numeric)

    @staticmethod
    def _resample_to_16k(audio_int16: np.ndarray, src_rate: int) -> np.ndarray:
        if audio_int16.size == 0:
            return np.array([], dtype=np.int16)
        if src_rate == OpenWakeWordGate.MODEL_SAMPLE_RATE:
            return audio_int16.astype(np.int16, copy=False)

        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        duration = len(audio_f32) / float(src_rate)
        if duration <= 0:
            return np.array([], dtype=np.int16)

        src_positions = np.linspace(0.0, duration, num=len(audio_f32), endpoint=False, dtype=np.float64)
        dst_length = max(1, int(round(duration * OpenWakeWordGate.MODEL_SAMPLE_RATE)))
        dst_positions = np.linspace(0.0, duration, num=dst_length, endpoint=False, dtype=np.float64)
        resampled = np.interp(dst_positions, src_positions, audio_f32)
        return np.clip(resampled * 32768.0, -32768, 32767).astype(np.int16)

    @staticmethod
    def _frame_rms(frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        audio = frame.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))

    def _frame_has_enough_energy(self, frame: np.ndarray) -> bool:
        return self._frame_rms(frame) >= self.energy_rms_threshold

    def _smoothed_score(self, raw_score: float) -> float:
        self._score_history.append(float(raw_score))
        if len(self._score_history) > self.score_smoothing_window:
            self._score_history = self._score_history[-self.score_smoothing_window :]
        if not self._score_history:
            return 0.0
        return float(sum(self._score_history) / len(self._score_history))

    def _soft_decay_state(self) -> None:
        if self._score_history:
            self._score_history.append(0.0)
            if len(self._score_history) > self.score_smoothing_window:
                self._score_history = self._score_history[-self.score_smoothing_window :]

    def _should_print_debug(self) -> bool:
        now = time.monotonic()
        if (now - self._last_debug_print_monotonic) >= self.debug_print_interval_seconds:
            self._last_debug_print_monotonic = now
            return True
        return False

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        effective_debug = bool(debug or self.debug)

        if not ignore_audio_block and self._input_blocked_by_assistant_output():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        if not ignore_audio_block and self._recently_unblocked():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        if self._in_activation_cooldown():
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        try:
            self._ensure_stream_open()
        except Exception as error:
            LOGGER.error("Failed to start wake input stream: %s", error)
            self._close_stream()
            self._clear_audio_queue()
            self._reset_runtime_state()
            return None

        self._clear_audio_queue()
        self._reset_runtime_state()

        started_at = time.monotonic()
        consecutive_hits = 0
        best_raw_score = 0.0
        best_smoothed_score = 0.0
        evaluated_frames = 0
        skipped_low_energy_frames = 0
        voiced_frames = 0

        while time.monotonic() - started_at <= float(timeout):
            if not ignore_audio_block and self._input_blocked_by_assistant_output():
                self._clear_audio_queue()
                self._reset_runtime_state()
                return None

            try:
                chunk = self.audio_queue.get(timeout=self._QUEUE_GET_TIMEOUT_SECONDS)
            except queue.Empty:
                continue
            except Exception as error:
                LOGGER.warning("Wake queue read error: %s", error)
                self._close_stream()
                self._clear_audio_queue()
                self._reset_runtime_state()
                return None

            pcm16 = np.asarray(chunk).astype(np.int16, copy=False)
            pcm16 = self._resample_to_16k(pcm16, self.input_sample_rate)
            if pcm16.size == 0:
                continue

            self._resampled_buffer = np.concatenate((self._resampled_buffer, pcm16))

            while len(self._resampled_buffer) >= self.model_frame_samples:
                frame = self._resampled_buffer[: self.model_frame_samples]
                self._resampled_buffer = self._resampled_buffer[self.frame_hop_samples :]

                if not self._frame_has_enough_energy(frame):
                    skipped_low_energy_frames += 1
                    consecutive_hits = max(0, consecutive_hits - 1)
                    self._soft_decay_state()
                    continue

                voiced_frames += 1

                try:
                    raw_prediction = self.model.predict(frame)
                except Exception as error:
                    LOGGER.warning("Wake model prediction failed: %s", error)
                    self._close_stream()
                    self._clear_audio_queue()
                    self._reset_runtime_state()
                    return None

                raw_score = self._extract_score(raw_prediction)
                smoothed_score = self._smoothed_score(raw_score)

                evaluated_frames += 1
                best_raw_score = max(best_raw_score, raw_score)
                best_smoothed_score = max(best_smoothed_score, smoothed_score)

                if smoothed_score >= self.threshold:
                    consecutive_hits += 1
                elif raw_score >= self.relaxed_hit_floor:
                    consecutive_hits = max(1, consecutive_hits)
                else:
                    consecutive_hits = max(0, consecutive_hits - 1)

                if effective_debug and self._should_print_debug():
                    print(
                        "OpenWakeWord "
                        f"raw={raw_score:.3f} smooth={smoothed_score:.3f} "
                        f"hits={consecutive_hits} eval={evaluated_frames} "
                        f"skip={skipped_low_energy_frames} voiced={voiced_frames}"
                    )

                strong_direct_accept = (
                    raw_score >= self.direct_accept_threshold
                    and smoothed_score >= self.direct_accept_support_floor
                    and voiced_frames >= self._MIN_VOICED_FRAMES_FOR_DIRECT_ACCEPT
                )

                stable_accept = (
                    smoothed_score >= self.threshold
                    and consecutive_hits >= self.min_frames_before_accept
                    and voiced_frames >= self._MIN_VOICED_FRAMES_FOR_STABLE_ACCEPT
                )

                if strong_direct_accept or stable_accept:
                    self._last_detection_monotonic = time.monotonic()
                    LOGGER.info(
                        "OpenWakeWord wake accepted: raw_score=%.3f, smooth_score=%.3f, "
                        "best_raw=%.3f, best_smooth=%.3f, evaluated_frames=%s, "
                        "skipped_low_energy_frames=%s, voiced_frames=%s, accept_path=%s",
                        raw_score,
                        smoothed_score,
                        best_raw_score,
                        best_smoothed_score,
                        evaluated_frames,
                        skipped_low_energy_frames,
                        voiced_frames,
                        "direct" if strong_direct_accept else "stable",
                    )
                    self._clear_audio_queue()
                    self._reset_runtime_state()
                    return "nexa"

        if effective_debug:
            print(
                "OpenWakeWord "
                f"best_raw={best_raw_score:.3f} best_smooth={best_smoothed_score:.3f} "
                f"eval={evaluated_frames} skip={skipped_low_energy_frames} voiced={voiced_frames}"
            )

        self._clear_audio_queue()
        self._reset_runtime_state()
        return None

    def close(self) -> None:
        self._clear_audio_queue()
        self._reset_runtime_state()
        self._close_stream()


__all__ = ["OpenWakeWordGate"]