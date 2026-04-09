from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import sounddevice as sd

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


LOGGER = logging.getLogger(__name__)


class OpenWakeWordGateHelpers:
    """Shared helper methods for the openWakeWord gate."""

    MODEL_SAMPLE_RATE: int

    _MIN_SAFE_THRESHOLD: float
    _MAX_SAFE_THRESHOLD: float
    _MIN_SAFE_TRIGGER_LEVEL: int
    _MIN_SAFE_BLOCK_MS: int
    _MIN_SAFE_VAD_THRESHOLD: float
    _MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS: float
    _MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS: float
    _MIN_SAFE_ENERGY_RMS_THRESHOLD: float
    _MIN_SAFE_SCORE_SMOOTHING_WINDOW: int

    audio_coordinator: AssistantAudioCoordinator | None
    block_release_settle_seconds: float
    activation_cooldown_seconds: float
    device: int | str | None
    device_name: str
    channels: int
    dtype: str
    model_path: Path
    model_name: str
    enable_speex_noise_suppression: bool
    vad_threshold: float
    _last_blocked_observed_monotonic: float
    _last_detection_monotonic: float

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


__all__ = ["LOGGER", "OpenWakeWordGateHelpers"]