from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.devices.audio.input.shared import (
    resolve_input_device_selection,
    resolve_supported_input_sample_rate,
)

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
    _device_default_sample_rate: int

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
    def _normalize_channel_mode(raw_value: str) -> str:
        value = str(raw_value).strip().lower()
        if value in {"mono_mix", "first_channel", "fixed_channel"}:
            return value
        LOGGER.warning(
            "Unsupported wake channel mode '%s'; falling back to 'mono_mix'.",
            raw_value,
        )
        return "mono_mix"

    @staticmethod
    def _normalize_channel_index(raw_value: int | None) -> int | None:
        if raw_value is None:
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            LOGGER.warning(
                "Unsupported wake channel index '%s'; falling back to None.",
                raw_value,
            )
            return None
        if value < 0:
            LOGGER.warning(
                "Negative wake channel index '%s' is invalid; falling back to None.",
                raw_value,
            )
            return None
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
        selection = resolve_input_device_selection(
            device_index=device_index,
            device_name_contains=device_name_contains,
        )
        self.device_name = selection.name
        self.available_input_devices_summary = selection.available_inputs_summary
        self.device_selection_reason = selection.reason
        self._device_default_sample_rate = selection.default_sample_rate
        return selection.device

    def _resolve_supported_input_sample_rate(self, preferred_rate: int) -> int:
        default_rate = getattr(self, "_device_default_sample_rate", self.MODEL_SAMPLE_RATE)
        return resolve_supported_input_sample_rate(
            device=self.device,
            device_name=self.device_name,
            channels=self.channels,
            dtype=self.dtype,
            preferred_sample_rate=preferred_rate,
            default_sample_rate=default_rate,
            logger=LOGGER,
            context_label="OpenWakeWordGate",
        )

    def _build_model(
        self,
        model_class: type,
        *,
        vad_threshold: float,
        enable_speex_noise_suppression: bool,
    ) -> Any:
        """
        Build an openwakeword Model that actually has the NeXa wake word
        loaded, across both the 1.x+ and 0.4.x APIs.

        Notes:
        - openwakeword 1.x+ takes 'wakeword_model_paths' and does NOT know
          'inference_framework'.
        - openwakeword 0.4.x takes 'wakeword_models' and 'inference_framework'.
        - Both Model.__init__ accept **kwargs, so unknown keyword arguments
          do not raise — the constructor can quietly return an empty model.
          Every candidate path below is therefore verified against
          model.models after construction. If no variant produces a model
          that actually loaded the wake word, we raise so wake_gate_mixin
          can surface the real reason instead of silently falling through
          to the compatibility path.
        """
        expected_key = str(self.model_name or "").strip().lower()
        model_path_str = str(self.model_path)

        attempts: list[tuple[str, dict[str, Any]]] = []

        # 1.x+ path — current releases. No 'inference_framework' keyword.
        modern_kwargs: dict[str, Any] = {"wakeword_model_paths": [model_path_str]}
        if vad_threshold > 0.0:
            modern_kwargs["vad_threshold"] = vad_threshold
        if enable_speex_noise_suppression:
            modern_kwargs["enable_speex_noise_suppression"] = True
        attempts.append(("openwakeword 1.x+ dedicated API", modern_kwargs))

        # 0.4.x path — kept for backwards compatibility. Uses
        # 'wakeword_models' plus the 'inference_framework' selector.
        legacy_kwargs: dict[str, Any] = {
            "wakeword_models": [model_path_str],
            "inference_framework": "onnx",
        }
        if vad_threshold > 0.0:
            legacy_kwargs["vad_threshold"] = vad_threshold
        if enable_speex_noise_suppression:
            legacy_kwargs["enable_speex_noise_suppression"] = True
        attempts.append(("openwakeword 0.4.x legacy API", legacy_kwargs))

        # Last-resort path — no extras at all. Helps when a future
        # version changes optional keywords but still honours the model
        # paths kwarg.
        attempts.append(
            ("openwakeword minimal API", {"wakeword_model_paths": [model_path_str]})
        )

        last_error: Exception | None = None
        for label, kwargs in attempts:
            try:
                model = model_class(**kwargs)
            except TypeError as error:
                last_error = error
                LOGGER.info(
                    "OpenWakeWordGate: %s rejected (%s). Trying next path.",
                    label,
                    error,
                )
                continue
            except Exception as error:
                last_error = error
                LOGGER.warning(
                    "OpenWakeWordGate: %s raised unexpectedly (%s). Trying next path.",
                    label,
                    error,
                )
                continue

            loaded_keys = list(getattr(model, "models", {}) or {})
            if not loaded_keys:
                last_error = RuntimeError(
                    f"{label} produced a Model with no loaded wake words. "
                    "The kwargs were likely swallowed by **kwargs."
                )
                LOGGER.info("OpenWakeWordGate: %s produced empty model. Trying next path.", label)
                continue

            if expected_key and expected_key not in {str(k).lower() for k in loaded_keys}:
                LOGGER.warning(
                    "OpenWakeWordGate: %s loaded unexpected wake word keys %s, "
                    "expected '%s'. Using the model as-is, downstream code "
                    "may need to adapt if this persists.",
                    label,
                    loaded_keys,
                    expected_key,
                )

            LOGGER.info(
                "OpenWakeWordGate using %s (loaded=%s).",
                label,
                loaded_keys,
            )
            return model

        raise RuntimeError(
            "OpenWakeWord Model could not be constructed with any known API. "
            f"Last error: {last_error}"
        )


__all__ = ["LOGGER", "OpenWakeWordGateHelpers"]