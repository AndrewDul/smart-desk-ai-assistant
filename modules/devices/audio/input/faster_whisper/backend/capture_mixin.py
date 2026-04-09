from __future__ import annotations

import queue
import time
from collections import deque

import numpy as np
import sounddevice as sd


class FasterWhisperCaptureMixin:
    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.LOGGER.warning("FasterWhisper audio callback status: %s", status)
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
            self.LOGGER.warning("FasterWhisper audio callback error: %s", error)

    def _ensure_stream_open(self) -> None:
        if self._stream is not None:
            return
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        stream.start()
        self._stream = stream
        self._last_stream_open_monotonic = self._now()
        self.LOGGER.info(
            "FasterWhisper input stream started: device='%s', sample_rate=%s, blocksize=%s",
            self.device_name,
            self.sample_rate,
            self.blocksize,
        )

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception as error:
            self.LOGGER.debug("FasterWhisper input stream stop warning: %s", error)
        try:
            stream.close()
        except Exception as error:
            self.LOGGER.debug("FasterWhisper input stream close warning: %s", error)

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _record_until_silence(
        self,
        timeout: float = 8.0,
        debug: bool = False,
        *,
        end_silence_seconds: float | None = None,
        min_speech_seconds: float | None = None,
        pre_roll_seconds: float | None = None,
        flush_queue: bool = True,
    ) -> np.ndarray | None:
        if self._input_blocked_by_assistant_output() or self._recently_unblocked():
            if debug:
                print("Capture skipped because audio shield is active or just released.")
            if flush_queue:
                self._clear_audio_queue()
            return None

        self._ensure_runtime_ready()
        self._ensure_stream_open()

        if flush_queue:
            self._clear_audio_queue()

        if self._stream_recently_opened():
            time.sleep(self.stream_start_settle_seconds)

        effective_end_silence = (
            self.end_silence_seconds
            if end_silence_seconds is None
            else max(float(end_silence_seconds), 0.08)
        )
        effective_min_speech = (
            self.min_speech_seconds
            if min_speech_seconds is None
            else max(float(min_speech_seconds), 0.05)
        )
        effective_pre_roll = (
            self.pre_roll_seconds
            if pre_roll_seconds is None
            else max(float(pre_roll_seconds), 0.05)
        )

        requested_timeout = max(float(timeout), 0.25)
        hard_timeout = min(requested_timeout, self.max_record_seconds)
        hard_timeout = max(hard_timeout, effective_min_speech + effective_end_silence + 0.20)
        start_time = self._now()

        pre_roll_max_chunks = max(
            1,
            int(round(effective_pre_roll * self.sample_rate / self.blocksize)),
        )
        pre_roll = deque(maxlen=pre_roll_max_chunks)

        recorded_chunks: list[np.ndarray] = []
        speech_started = False
        speech_started_at: float | None = None
        last_speech_at: float | None = None
        last_voiced_observation: float | None = None
        low_energy_after_start = 0

        while self._now() - start_time <= hard_timeout:
            if self._input_blocked_by_assistant_output():
                if debug:
                    print("Capture aborted because assistant output shield became active.")
                if flush_queue:
                    self._clear_audio_queue()
                return None

            try:
                chunk = self.audio_queue.get(timeout=0.08)
            except queue.Empty:
                if speech_started and last_speech_at is not None:
                    if (self._now() - last_speech_at) >= effective_end_silence:
                        break
                continue
            except Exception as error:
                self.LOGGER.warning("FasterWhisper queue read error: %s", error)
                self._close_stream()
                return None

            chunk_f32 = self._int16_chunk_to_float32(chunk)
            if chunk_f32.size == 0:
                continue

            pre_roll.append(chunk_f32)
            chunk_has_speech = self._window_contains_speech(chunk_f32)
            if chunk_has_speech:
                last_voiced_observation = self._now()

            if not speech_started:
                onset_window = self._concat_audio(list(pre_roll))
                onset_has_speech = self._window_contains_speech(onset_window)
                if onset_has_speech or chunk_has_speech:
                    speech_started = True
                    speech_started_at = self._now()
                    last_speech_at = speech_started_at
                    recorded_chunks.extend(list(pre_roll))
                    low_energy_after_start = 0
                    if debug:
                        print("Speech onset detected by Faster-Whisper frontend.")
                    continue
            else:
                recorded_chunks.append(chunk_f32)

                trailing_chunks = recorded_chunks[-max(1, pre_roll_max_chunks * 2):]
                trailing_window = self._concat_audio(trailing_chunks)
                trailing_has_speech = self._window_contains_speech(trailing_window)

                if chunk_has_speech or trailing_has_speech:
                    last_speech_at = self._now()
                    low_energy_after_start = 0
                else:
                    low_energy_after_start += 1

                enough_speech = False
                if speech_started_at is not None:
                    enough_speech = (self._now() - speech_started_at) >= effective_min_speech

                if enough_speech and last_speech_at is not None:
                    if (self._now() - last_speech_at) >= effective_end_silence:
                        break

                if (
                    enough_speech
                    and last_voiced_observation is not None
                    and (self._now() - last_voiced_observation)
                    >= max(self.no_speech_decay_seconds, effective_end_silence)
                    and low_energy_after_start >= 2
                ):
                    break

        if not speech_started or not recorded_chunks:
            if debug:
                print(f"No speech onset detected before command timeout ({hard_timeout:.2f}s).")
            return None

        audio = self._concat_audio(recorded_chunks)
        duration = len(audio) / float(self.sample_rate)
        if duration < effective_min_speech:
            if debug:
                print("Recorded utterance too short, dropping.")
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        trimmed_duration = len(trimmed_audio) / float(self.sample_rate) if trimmed_audio.size else 0.0

        if debug:
            print(f"Recorded audio duration: {duration:.2f}s | trimmed duration: {trimmed_duration:.2f}s")

        if trimmed_audio.size >= int(self.sample_rate * effective_min_speech):
            return trimmed_audio
        return audio

    def _window_contains_speech(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return False
        if self.vad_enabled and self._silero_window_contains_speech(audio):
            return True
        return self._energy_window_contains_speech(audio)

    def _silero_window_contains_speech(self, audio: np.ndarray) -> bool:
        if self._silero_model is None or self._silero_get_speech_timestamps is None:
            return False
        resampled = self._resample_audio(audio, self.sample_rate, self.MODEL_SAMPLE_RATE)
        if resampled.size == 0:
            return False
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
            return bool(timestamps)
        except Exception as error:
            self.LOGGER.warning("Silero VAD inference warning: %s", error)
            return False

    def _energy_window_contains_speech(self, audio: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return rms >= self.energy_speech_threshold or peak >= max(
            self.energy_speech_threshold * 4.2,
            0.025,
        )