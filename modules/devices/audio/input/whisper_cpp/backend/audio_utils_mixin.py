from __future__ import annotations

import re
import time
import unicodedata

import numpy as np


class WhisperCppAudioUtilsMixin:
    def _debug_print_allowed(self) -> bool:
        now = self._now()
        if (now - self._last_debug_print_monotonic) >= self.debug_print_cooldown_seconds:
            self._last_debug_print_monotonic = now
            return True
        return False

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    def _int16_chunk_to_float32(chunk: np.ndarray) -> np.ndarray:
        if chunk is None:
            return np.array([], dtype=np.float32)
        array = np.asarray(chunk)
        if array.dtype != np.int16:
            array = array.astype(np.int16, copy=False)
        return array.astype(np.float32) / 32768.0

    @staticmethod
    def _float32_audio_to_int16(audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return np.array([], dtype=np.int16)
        clipped = np.clip(audio, -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16)

    @staticmethod
    def _concat_audio(chunks: list[np.ndarray]) -> np.ndarray:
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    @staticmethod
    def _normalize_text_ascii(text: str) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-zA-ZÀ-ÿ0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered.strip()