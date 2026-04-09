from __future__ import annotations

import time
from typing import Any

import numpy as np

from .helpers import OpenWakeWordGateHelpers


class OpenWakeWordGateScoring(OpenWakeWordGateHelpers):
    """Scoring, smoothing, energy, and resampling helpers for the wake gate."""

    debug: bool
    debug_print_interval_seconds: float
    energy_rms_threshold: float
    score_smoothing_window: int
    model_name: str
    _last_debug_print_monotonic: float
    _score_history: list[float]

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
        model_sample_rate = 16000

        if audio_int16.size == 0:
            return np.array([], dtype=np.int16)
        if src_rate == model_sample_rate:
            return audio_int16.astype(np.int16, copy=False)

        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        duration = len(audio_f32) / float(src_rate)
        if duration <= 0:
            return np.array([], dtype=np.int16)

        src_positions = np.linspace(0.0, duration, num=len(audio_f32), endpoint=False, dtype=np.float64)
        dst_length = max(1, int(round(duration * model_sample_rate)))
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


__all__ = ["OpenWakeWordGateScoring"]