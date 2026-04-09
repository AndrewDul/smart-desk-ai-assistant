from __future__ import annotations

import time

import numpy as np


class FasterWhisperAudioUtilsMixin:
    def _trim_audio_for_transcription(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return audio

        if self.vad_enabled:
            silero_trimmed = self._trim_with_silero(audio)
            if silero_trimmed is not None and silero_trimmed.size > 0:
                return silero_trimmed

        energy_trimmed = self._trim_with_energy(audio)
        if energy_trimmed.size > 0:
            return energy_trimmed

        return audio

    def _trim_with_silero(self, audio: np.ndarray) -> np.ndarray | None:
        if self._silero_model is None or self._silero_get_speech_timestamps is None:
            return None

        resampled = self._resample_audio(audio, self.sample_rate, self.MODEL_SAMPLE_RATE)
        if resampled.size == 0:
            return None

        try:
            timestamps = self._silero_get_speech_timestamps(
                resampled,
                self._silero_model,
                sampling_rate=self.MODEL_SAMPLE_RATE,
                threshold=self.vad_threshold,
                min_speech_duration_ms=self.vad_min_speech_ms,
                min_silence_duration_ms=self.vad_min_silence_ms,
                speech_pad_ms=self.vad_speech_pad_ms,
            )
        except Exception as error:
            self.LOGGER.warning("Silero trim warning: %s", error)
            return None

        if not timestamps:
            return None

        start = int(timestamps[0]["start"] * self.sample_rate / self.MODEL_SAMPLE_RATE)
        end = int(timestamps[-1]["end"] * self.sample_rate / self.MODEL_SAMPLE_RATE)
        start = max(0, start)
        end = min(len(audio), max(end, start + 1))
        if end <= start:
            return None

        return audio[start:end].astype(np.float32, copy=False)

    def _trim_with_energy(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return audio

        abs_audio = np.abs(audio)
        dynamic_threshold = float(np.max(abs_audio) * 0.16) if abs_audio.size else 0.0
        threshold = max(0.008, dynamic_threshold)
        mask = abs_audio >= threshold
        indices = np.flatnonzero(mask)
        if indices.size == 0:
            return audio

        pad = int(self.sample_rate * 0.12)
        start = max(0, int(indices[0]) - pad)
        end = min(len(audio), int(indices[-1]) + pad)
        if end <= start:
            return audio

        return audio[start:end].astype(np.float32, copy=False)

    def _prepare_audio_for_model(self, audio: np.ndarray) -> np.ndarray | None:
        if audio.size == 0:
            return None

        trimmed = self._trim_audio_for_transcription(audio)
        if trimmed.size == 0:
            trimmed = audio

        resampled = self._resample_audio(trimmed, self.sample_rate, self.MODEL_SAMPLE_RATE)
        if resampled.size == 0:
            return None

        duration = len(resampled) / float(self.MODEL_SAMPLE_RATE)
        rms = float(np.sqrt(np.mean(np.square(resampled), dtype=np.float64))) if resampled.size else 0.0

        if duration < self.min_transcription_seconds and rms < self.short_clip_rms_threshold:
            return None
        if duration < 0.18:
            return None

        return resampled.astype(np.float32, copy=False)

    def _prepare_audio_for_wake_model(self, audio: np.ndarray) -> np.ndarray | None:
        if audio.size == 0:
            return None

        trimmed = self._trim_audio_for_transcription(audio)
        if trimmed.size == 0:
            trimmed = audio

        resampled = self._resample_audio(trimmed, self.sample_rate, self.MODEL_SAMPLE_RATE)
        if resampled.size == 0:
            return None

        duration = len(resampled) / float(self.MODEL_SAMPLE_RATE)
        rms = float(np.sqrt(np.mean(np.square(resampled), dtype=np.float64))) if resampled.size else 0.0

        if duration < 0.06:
            return None
        if duration < 0.14 and rms < self.wake_short_clip_rms_threshold:
            return None

        return resampled.astype(np.float32, copy=False)

    def _extract_voiced_audio_for_retry(self, audio: np.ndarray) -> np.ndarray | None:
        if audio.size == 0:
            return None

        if self.vad_enabled and self._silero_model is not None and self._silero_get_speech_timestamps is not None:
            resampled = self._resample_audio(audio, self.sample_rate, self.MODEL_SAMPLE_RATE)
            try:
                timestamps = self._silero_get_speech_timestamps(
                    resampled,
                    self._silero_model,
                    sampling_rate=self.MODEL_SAMPLE_RATE,
                    threshold=self.vad_threshold,
                    min_speech_duration_ms=self.vad_min_speech_ms,
                    min_silence_duration_ms=self.vad_min_silence_ms,
                    speech_pad_ms=self.vad_speech_pad_ms,
                )
            except Exception as error:
                self.LOGGER.warning("Silero retry extraction warning: %s", error)
                timestamps = []

            if timestamps:
                parts: list[np.ndarray] = []
                for stamp in timestamps:
                    src_start = int(stamp["start"] * self.sample_rate / self.MODEL_SAMPLE_RATE)
                    src_end = int(stamp["end"] * self.sample_rate / self.MODEL_SAMPLE_RATE)
                    src_start = max(0, src_start)
                    src_end = min(len(audio), max(src_end, src_start + 1))
                    if src_end > src_start:
                        parts.append(audio[src_start:src_end])

                if parts:
                    joined = self._concat_audio(parts)
                    if joined.size > 0:
                        return joined

        trimmed = self._trim_with_energy(audio)
        if trimmed.size > 0:
            return trimmed
        return None

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
    def _concat_audio(chunks: list[np.ndarray]) -> np.ndarray:
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32, copy=False)

    @staticmethod
    def _resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if audio.size == 0:
            return np.array([], dtype=np.float32)
        if src_rate == dst_rate:
            return audio.astype(np.float32, copy=False)

        duration = len(audio) / float(src_rate)
        if duration <= 0:
            return np.array([], dtype=np.float32)

        src_positions = np.linspace(
            0.0,
            duration,
            num=len(audio),
            endpoint=False,
            dtype=np.float64,
        )
        dst_length = max(1, int(round(duration * dst_rate)))
        dst_positions = np.linspace(
            0.0,
            duration,
            num=dst_length,
            endpoint=False,
            dtype=np.float64,
        )
        return np.interp(dst_positions, src_positions, audio).astype(np.float32)