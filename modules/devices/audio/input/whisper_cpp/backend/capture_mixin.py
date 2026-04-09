from __future__ import annotations

import queue
from collections import deque

import numpy as np
import sounddevice as sd


class WhisperCppCaptureMixin:
    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.LOGGER.warning("Whisper.cpp audio callback status: %s", status)

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
            self.LOGGER.warning("Whisper.cpp audio callback error: %s", error)

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
    ) -> np.ndarray | None:
        if self._input_blocked_by_assistant_output() or self._recently_unblocked():
            if debug:
                print("Capture skipped because audio shield is active or just released.")
            return None

        self._clear_audio_queue()

        hard_timeout = max(float(timeout), self.max_record_seconds)
        start_time = self._now()

        pre_roll_max_chunks = max(
            1,
            int(round(self.pre_roll_seconds * self.sample_rate / self.blocksize)),
        )
        pre_roll = deque(maxlen=pre_roll_max_chunks)

        recorded_chunks: list[np.ndarray] = []
        speech_started = False
        speech_started_at: float | None = None
        last_speech_at: float | None = None

        with sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        ):
            while self._now() - start_time <= hard_timeout:
                if self._input_blocked_by_assistant_output():
                    if debug:
                        print("Capture aborted because assistant output shield became active.")
                    self._clear_audio_queue()
                    return None

                try:
                    chunk = self.audio_queue.get(timeout=0.12)
                except queue.Empty:
                    continue

                chunk_f32 = self._int16_chunk_to_float32(chunk)
                if chunk_f32.size == 0:
                    continue

                pre_roll.append(chunk_f32)
                chunk_has_speech = self._window_contains_speech(chunk_f32)

                if not speech_started:
                    onset_window = self._concat_audio(list(pre_roll))
                    onset_has_speech = self._window_contains_speech(onset_window)

                    if onset_has_speech or chunk_has_speech:
                        speech_started = True
                        speech_started_at = self._now()
                        last_speech_at = speech_started_at
                        recorded_chunks.extend(list(pre_roll))
                        if debug:
                            print("Speech onset detected by whisper.cpp frontend.")
                        continue

                if speech_started:
                    recorded_chunks.append(chunk_f32)

                    trailing_window = self._concat_audio(
                        recorded_chunks[-max(1, pre_roll_max_chunks * 3):]
                    )
                    trailing_has_speech = self._window_contains_speech(trailing_window)

                    if chunk_has_speech or trailing_has_speech:
                        last_speech_at = self._now()

                    enough_speech = False
                    if speech_started_at is not None:
                        enough_speech = (
                            self._now() - speech_started_at
                        ) >= self.min_speech_seconds

                    if enough_speech and last_speech_at is not None:
                        if (self._now() - last_speech_at) >= self.end_silence_seconds:
                            break

        if not speech_started or not recorded_chunks:
            return None

        audio = self._concat_audio(recorded_chunks)
        duration = len(audio) / float(self.sample_rate)
        if duration < self.min_speech_seconds:
            if debug:
                print("Recorded utterance too short, dropping.")
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        trimmed_duration = (
            len(trimmed_audio) / float(self.sample_rate) if trimmed_audio.size else 0.0
        )

        if debug:
            print(
                f"Recorded audio duration: {duration:.2f}s | trimmed duration: {trimmed_duration:.2f}s"
            )

        if trimmed_audio.size >= int(self.sample_rate * self.min_speech_seconds):
            return trimmed_audio
        return audio

    def _window_contains_speech(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        return rms >= self.energy_speech_threshold

    def _trim_audio_for_transcription(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return audio

        abs_audio = np.abs(audio)
        threshold = max(0.010, float(np.max(abs_audio) * 0.18))
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