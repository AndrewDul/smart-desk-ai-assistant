from __future__ import annotations

import logging
import queue
import re
import tempfile
import time
import unicodedata
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


LOGGER = logging.getLogger(__name__)


class FasterWhisperInputBackend:
    """
    Premium offline speech-input backend based on Faster-Whisper.

    Responsibilities:
    - persistent microphone capture with low-latency queueing
    - assistant-output shielding integration
    - speech onset and end-of-utterance detection
    - Silero-assisted trimming with energy fallback
    - bilingual rescue logic for Polish / English
    - rejection of obvious non-speech / blank hallucinations
    - fast compatibility wake detection in single-capture mode
    """

    MODEL_SAMPLE_RATE = 16000
    SUPPORTED_LANGUAGES = {"pl", "en"}

    WAKE_ALIASES = (
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    )

    WAKE_FILLER_WORDS = {
        "hey",
        "hi",
        "hello",
        "ok",
        "okay",
        "yo",
        "please",
        "hej",
        "halo",
        "dobra",
        "okej",
        "okey",
        "prosze",
        "proszeee",
    }

    POLISH_HINT_WORDS = {
        "ktora", "która", "jaka", "godzina", "godzine", "czas", "kim", "jestes", "jesteś",
        "jak", "sie", "się", "nazywasz", "pokaz", "pokaż", "wyswietl", "wyświetl", "powiedz",
        "wyjasnij", "wyjaśnij", "wytlumacz", "wytłumacz", "zrob", "zrób", "pomoz", "pomóż",
        "pomoc", "przypomnienie", "przypomnienia", "timer", "focus", "fokus", "przerwa",
        "wylacz", "wyłącz", "zamknij", "asystenta", "system", "dziekuje", "dziękuję", "dzieki",
        "dzięki", "nie", "tak", "anuluj", "niewazne", "nieważne", "klucze", "kuchni",
        "imie", "imię", "przypomnij", "zapamietaj", "zapamiętaj", "ustaw", "wlacz", "włącz",
    }

    ENGLISH_HINT_WORDS = {
        "what", "time", "who", "are", "you", "your", "name", "show", "tell", "explain", "help",
        "timer", "reminder", "focus", "break", "turn", "off", "close", "assistant", "system",
        "yes", "no", "cancel", "nevermind", "never", "mind", "keys", "kitchen", "remember",
        "remind", "set", "start", "stop",
    }

    SHORT_COMMAND_PHRASES = {
        "en": {
            "yes", "no", "cancel", "never mind", "nevermind", "stop", "what time is it",
            "what day is it", "what month is it", "what year is it", "who are you",
            "what is your name", "show it", "show that", "tell me", "help me", "close assistant",
            "shutdown system", "where are the keys", "what time", "time is it", "show time",
            "show date", "show day", "show month", "show year", "set timer", "start timer",
            "start focus", "start break",
        },
        "pl": {
            "tak", "nie", "anuluj", "niewazne", "nie wazne", "zostaw to", "zapomnij",
            "ktora godzina", "która godzina", "jaki dzien", "jaki dzień", "jaki miesiac",
            "jaki miesiąc", "jaki rok", "kim jestes", "kim jesteś", "jak masz na imie",
            "jak masz na imię", "pokaz to", "pokaż to", "pomoz mi", "pomóż mi",
            "zamknij asystenta", "wylacz system", "wyłącz system", "gdzie sa klucze",
            "gdzie są klucze", "ktora jest godzina", "która jest godzina", "pokaz godzine",
            "pokaż godzinę", "pokaz date", "pokaż datę", "ustaw timer", "wlacz timer",
            "włącz timer", "wlacz fokus", "włącz fokus",
        },
    }

    SUSPICIOUS_ENGLISH_FALSE_POSITIVES = (
        "thank you very much",
        "thanks for watching",
        "speaking in foreign language",
        "foreign",
        "they won t",
        "they wont",
        "matchminton",
        "ocean ive",
    )

    NON_SPEECH_TRANSCRIPTS = {
        "",
        "[blank_audio]",
        "[noise]",
        "blank audio",
        "no speech",
        "silence",
        "noise",
        "music",
        "foreign",
        "speaking in foreign language",
        "thank you",
        "thanks",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "clap",
        "clapping",
        "applause",
        "static",
        ".",
        "...",
    }

    def __init__(
        self,
        *,
        model_size_or_path: str = "small",
        language: str = "auto",
        device_index: int | None = None,
        device_name_contains: str | None = None,
        sample_rate: int | None = 16000,
        max_record_seconds: float = 8.0,
        end_silence_seconds: float = 0.65,
        pre_roll_seconds: float = 0.45,
        blocksize: int = 512,
        min_speech_seconds: float = 0.20,
        transcription_timeout_seconds: float = 15.0,
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 1,
        best_of: int = 1,
        vad_enabled: bool = True,
        vad_threshold: float = 0.30,
        vad_min_speech_ms: int = 120,
        vad_min_silence_ms: int = 250,
        vad_speech_pad_ms: int = 180,
    ) -> None:
        self.language = self._normalize_language(language, allow_auto=True)

        self.max_record_seconds = max(float(max_record_seconds), 4.0)
        self.end_silence_seconds = max(float(end_silence_seconds), 0.18)
        self.pre_roll_seconds = max(float(pre_roll_seconds), 0.08)
        self.blocksize = max(int(blocksize), 256)
        self.channels = 1
        self.dtype = "int16"
        self.min_speech_seconds = max(float(min_speech_seconds), 0.10)
        self.transcription_timeout_seconds = max(float(transcription_timeout_seconds), 3.0)

        self.compute_type = str(compute_type or "int8").strip() or "int8"
        self.cpu_threads = max(int(cpu_threads), 1)
        self.beam_size = max(int(beam_size), 1)
        self.best_of = max(int(best_of), 1)

        self.vad_enabled = bool(vad_enabled)
        self.vad_threshold = float(vad_threshold)
        self.vad_min_speech_ms = max(int(vad_min_speech_ms), 50)
        self.vad_min_silence_ms = max(int(vad_min_silence_ms), 80)
        self.vad_speech_pad_ms = max(int(vad_speech_pad_ms), 0)

        self.model_size_or_path = str(model_size_or_path or "small").strip() or "small"

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=48)
        self.audio_coordinator: AssistantAudioCoordinator | None = None

        self.device = self._resolve_input_device(device_index, device_name_contains)
        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.device_default_sample_rate = int(round(float(input_info.get("default_samplerate", 16000))))
        self.sample_rate = self._resolve_supported_sample_rate(sample_rate)

        self._fw_model: Any | None = None
        self._silero_model: Any | None = None
        self._silero_get_speech_timestamps = None
        self._fw_dependency_error: str | None = None
        self._silero_unavailable_logged = False

        self.min_transcription_seconds = max(0.24, self.min_speech_seconds)
        self.retry_min_seconds = max(0.65, self.min_transcription_seconds + 0.18)
        self.short_clip_rms_threshold = 0.010
        self.energy_speech_threshold = 0.0048
        self.language_rescue_probability_threshold = 0.80
        self.min_words_for_low_confidence_accept = 4

        # Fast wake mode tuning
        self.wake_timeout_seconds = 0.95
        self.wake_end_silence_seconds = 0.12
        self.wake_pre_roll_seconds = 0.10
        self.wake_min_speech_seconds = 0.07
        self.wake_short_clip_rms_threshold = 0.0048
        self.wake_forced_languages = ("en", "pl")

        self.input_unblock_settle_seconds = 0.16
        self.stream_start_settle_seconds = 0.05
        self.no_speech_decay_seconds = 0.55
        self.debug_print_cooldown_seconds = 0.35
        self._last_input_blocked_monotonic = 0.0
        self._last_debug_print_monotonic = 0.0
        self._last_stream_open_monotonic = 0.0

        self._stream: sd.InputStream | None = None
        self._session_temp_dir = Path(tempfile.mkdtemp(prefix="nexa_fw_stt_"))

        LOGGER.info(
            "FasterWhisperInputBackend prepared: device='%s', sample_rate=%s, language_mode=%s, vad=%s",
            self.device_name,
            self.sample_rate,
            self.language,
            "on" if self.vad_enabled else "off",
        )

        # Warm up once at startup so the first wake does not pay model-load cost.
        try:
            self._ensure_runtime_ready()
        except Exception as error:
            LOGGER.warning("FasterWhisper warmup will be retried lazily. Reason: %s", error)

    @classmethod
    def _normalize_language(cls, language: str | None, *, allow_auto: bool = False) -> str:
        normalized = str(language or "").strip().lower()
        if allow_auto and normalized in {"", "auto"}:
            return "auto"
        if normalized in cls.SUPPORTED_LANGUAGES:
            return normalized
        return "auto" if allow_auto else "en"

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
            self._last_input_blocked_monotonic = self._now()
        return blocked

    def _recently_unblocked(self) -> bool:
        if self._last_input_blocked_monotonic <= 0.0:
            return False
        return (self._now() - self._last_input_blocked_monotonic) < self.input_unblock_settle_seconds

    def _stream_recently_opened(self) -> bool:
        if self._last_stream_open_monotonic <= 0.0:
            return False
        return (self._now() - self._last_stream_open_monotonic) < self.stream_start_settle_seconds

    def _ensure_faster_whisper_runtime(self) -> None:
        if self._fw_dependency_error:
            raise RuntimeError(self._fw_dependency_error)
        if self._fw_model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except Exception as error:
            self._fw_dependency_error = (
                "Missing faster-whisper dependency. Install it before using the Faster-Whisper backend."
            )
            raise RuntimeError(self._fw_dependency_error) from error

        self._fw_model = WhisperModel(
            self.model_size_or_path,
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=1,
        )

        LOGGER.info(
            "Faster-Whisper model loaded: model_ref='%s', compute_type='%s', threads=%s",
            self.model_size_or_path,
            self.compute_type,
            self.cpu_threads,
        )

    def _ensure_silero_runtime(self) -> None:
        if not self.vad_enabled:
            return
        if self._silero_model is not None and self._silero_get_speech_timestamps is not None:
            return
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except Exception as error:
            if not self._silero_unavailable_logged:
                LOGGER.warning(
                    "Silero VAD unavailable. Falling back to energy-based speech detection. Reason: %s",
                    error,
                )
                self._silero_unavailable_logged = True
            return

        self._silero_model = load_silero_vad(onnx=True)
        self._silero_get_speech_timestamps = get_speech_timestamps
        LOGGER.info("Silero VAD loaded successfully for FasterWhisperInputBackend.")

    def _ensure_runtime_ready(self) -> None:
        self._ensure_silero_runtime()
        self._ensure_faster_whisper_runtime()

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

    def _resolve_supported_sample_rate(self, preferred_sample_rate: int | None) -> int:
        candidates: list[int] = []
        if preferred_sample_rate:
            candidates.append(int(preferred_sample_rate))
        candidates.extend([self.device_default_sample_rate, 16000, 32000, 44100, 48000])

        seen: set[int] = set()
        unique_candidates: list[int] = []
        for rate in candidates:
            if rate and rate not in seen:
                unique_candidates.append(rate)
                seen.add(rate)

        for rate in unique_candidates:
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
            f"No supported sample rate found for input device '{self.device_name}'. Tried: {unique_candidates}"
        )

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            LOGGER.warning("FasterWhisper audio callback status: %s", status)
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
            LOGGER.warning("FasterWhisper audio callback error: %s", error)

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
        LOGGER.info(
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
            LOGGER.debug("FasterWhisper input stream stop warning: %s", error)
        try:
            stream.close()
        except Exception as error:
            LOGGER.debug("FasterWhisper input stream close warning: %s", error)

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

        effective_end_silence = self.end_silence_seconds if end_silence_seconds is None else max(float(end_silence_seconds), 0.08)
        effective_min_speech = self.min_speech_seconds if min_speech_seconds is None else max(float(min_speech_seconds), 0.05)
        effective_pre_roll = self.pre_roll_seconds if pre_roll_seconds is None else max(float(pre_roll_seconds), 0.05)

        requested_timeout = max(float(timeout), 0.25)
        hard_timeout = min(requested_timeout, self.max_record_seconds)
        hard_timeout = max(hard_timeout, effective_min_speech + effective_end_silence + 0.20)
        start_time = self._now()

        pre_roll_max_chunks = max(1, int(round(effective_pre_roll * self.sample_rate / self.blocksize)))
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
                LOGGER.warning("FasterWhisper queue read error: %s", error)
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
                    and (self._now() - last_voiced_observation) >= max(self.no_speech_decay_seconds, effective_end_silence)
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
            LOGGER.warning("Silero VAD inference warning: %s", error)
            return False

    def _energy_window_contains_speech(self, audio: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return rms >= self.energy_speech_threshold or peak >= max(self.energy_speech_threshold * 4.2, 0.025)

    def _transcribe_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        self._ensure_faster_whisper_runtime()
        if self._fw_model is None or audio.size == 0:
            return None

        primary_audio = self._trim_audio_for_transcription(audio)
        if primary_audio.size < int(self.sample_rate * self.min_speech_seconds):
            primary_audio = audio

        prepared_primary = self._prepare_audio_for_model(primary_audio)
        if prepared_primary is None:
            if debug:
                print("Skipping transcription: clip too short or too weak after trimming.")
            return None

        primary_candidate = self._transcribe_single_audio(
            prepared_primary,
            debug=debug,
            label="primary",
            forced_language=None,
        )

        if self._accept_candidate(primary_candidate):
            return str(primary_candidate.get("text") or "").strip() or None

        rescue_candidate = self._rescue_bilingual_candidate(
            prepared_primary,
            primary_candidate=primary_candidate,
            debug=debug,
        )
        if rescue_candidate is not None:
            return str(rescue_candidate.get("text") or "").strip() or None

        primary_duration = len(prepared_primary) / float(self.MODEL_SAMPLE_RATE)
        if primary_duration < self.retry_min_seconds:
            return None

        retry_audio = self._extract_voiced_audio_for_retry(audio)
        if retry_audio is None or retry_audio.size == 0:
            return None

        prepared_retry = self._prepare_audio_for_model(retry_audio)
        if prepared_retry is None:
            return None

        retry_candidate = self._transcribe_single_audio(
            prepared_retry,
            debug=debug,
            label="retry",
            forced_language=None,
        )
        if self._accept_candidate(retry_candidate):
            return str(retry_candidate.get("text") or "").strip() or None

        retry_rescue_candidate = self._rescue_bilingual_candidate(
            prepared_retry,
            primary_candidate=retry_candidate,
            debug=debug,
        )
        if retry_rescue_candidate is not None:
            return str(retry_rescue_candidate.get("text") or "").strip() or None

        return None

    def _transcribe_single_audio(
        self,
        audio: np.ndarray,
        *,
        debug: bool = False,
        label: str = "primary",
        forced_language: str | None = None,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "text": None,
            "language": forced_language,
            "language_probability": 0.0,
            "elapsed": 0.0,
            "forced_language": forced_language,
            "engine": "faster_whisper",
        }

        try:
            language_arg = forced_language if forced_language else (None if self.language == "auto" else self.language)
            started_at = self._now()
            segments, info = self._fw_model.transcribe(
                audio,
                language=language_arg,
                beam_size=self.beam_size,
                best_of=self.best_of,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
                temperature=0.0,
            )

            parts: list[str] = []
            for segment in segments:
                text = str(getattr(segment, "text", "")).strip()
                if text:
                    parts.append(text)

            elapsed = self._now() - started_at
            transcript = self._cleanup_transcript(" ".join(parts))
            detected_language = forced_language or getattr(info, "language", None)
            language_probability = getattr(info, "language_probability", None)
            if language_probability is None:
                language_probability = 1.0 if forced_language else 0.0

            candidate.update(
                {
                    "text": transcript,
                    "language": self._normalize_language(detected_language, allow_auto=True),
                    "language_probability": float(language_probability),
                    "elapsed": elapsed,
                }
            )

            if debug and self._debug_print_allowed():
                printable = transcript if transcript else "<empty>"
                mode_label = label if forced_language is None else f"{label}:{forced_language}"
                print(
                    f"FasterWhisper {mode_label} transcript: {printable} | "
                    f"lang={detected_language} prob={language_probability} elapsed={elapsed:.2f}s"
                )

            return candidate
        except Exception as error:
            LOGGER.warning("FasterWhisper transcription error (%s): %s", label, error)
            return candidate

    def _rescue_bilingual_candidate(
        self,
        audio: np.ndarray,
        *,
        primary_candidate: dict[str, Any] | None = None,
        debug: bool = False,
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        primary_language = str((primary_candidate or {}).get("language") or "").strip().lower()
        if primary_language not in self.SUPPORTED_LANGUAGES:
            primary_language = ""

        for forced_language in self._preferred_rescue_languages(primary_candidate):
            candidate = self._transcribe_single_audio(
                audio,
                debug=debug,
                label="rescue",
                forced_language=forced_language,
            )
            if candidate.get("text"):
                candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: self._candidate_score(item, primary_language=primary_language or None),
            reverse=True,
        )
        best = candidates[0]
        if self._candidate_score(best, primary_language=primary_language or None) <= 0.0:
            return None
        return best

    def _preferred_rescue_languages(
        self,
        primary_candidate: dict[str, Any] | None,
    ) -> tuple[str, ...]:
        text = str((primary_candidate or {}).get("text") or "").strip()
        hinted_language = self._guess_hint_language(text)
        if hinted_language == "pl":
            return ("pl", "en")
        if hinted_language == "en":
            return ("en", "pl")

        primary_language = str((primary_candidate or {}).get("language") or "").strip().lower()
        if primary_language == "pl":
            return ("pl", "en")
        if primary_language == "en":
            return ("en", "pl")
        return ("pl", "en")

    def _accept_candidate(self, candidate: dict[str, Any]) -> bool:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()
        probability = float(candidate.get("language_probability") or 0.0)

        if not text:
            return False
        if self._contains_unsupported_script(text):
            return False
        if self._looks_like_blank_or_garbage(text):
            return False
        if self._strong_command_match(text):
            return True

        word_count = len(text.split())
        if language not in self.SUPPORTED_LANGUAGES:
            return False
        if probability >= self.language_rescue_probability_threshold:
            return True
        if word_count >= self.min_words_for_low_confidence_accept:
            return True
        return False

    def _candidate_score(
        self,
        candidate: dict[str, Any],
        *,
        primary_language: str | None = None,
    ) -> float:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()
        probability = float(candidate.get("language_probability") or 0.0)

        if not text:
            return -10.0

        score = 0.0
        score += min(len(text.split()), 8) * 0.25
        score += min(probability, 1.0)

        if language in self.SUPPORTED_LANGUAGES:
            score += 0.5
        elif language == "auto":
            score -= 0.2
        else:
            score -= 2.0

        if self._contains_unsupported_script(text):
            score -= 5.0
        if self._looks_like_blank_or_garbage(text):
            score -= 3.0

        score += self._language_affinity_score(text, language)
        score += self._question_shape_bonus(text, language)
        score += self._command_phrase_bonus(text, language)
        score += self._primary_language_bonus(language, primary_language)
        score -= self._false_positive_penalty(text, language)

        if self._strong_command_match(text):
            score += 1.5

        return score

    def _command_phrase_bonus(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        shared_commands = {
            "yes", "no", "tak", "nie", "cancel", "anuluj", "timer", "focus", "break",
            "exit", "shutdown", "set timer", "what time", "time is it", "ktora godzina",
            "która godzina",
        }

        bonus = 0.0
        if normalized in shared_commands:
            bonus += 1.9
        if language == "en" and normalized in self.SHORT_COMMAND_PHRASES["en"]:
            bonus += 2.1
        if language == "pl" and normalized in self.SHORT_COMMAND_PHRASES["pl"]:
            bonus += 2.1
        return bonus

    def _primary_language_bonus(self, language: str, primary_language: str | None) -> float:
        if not primary_language or primary_language not in self.SUPPORTED_LANGUAGES:
            return 0.0
        if language == primary_language:
            return 0.95
        if language in self.SUPPORTED_LANGUAGES:
            return -0.15
        return 0.0

    def _language_affinity_score(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        words = set(normalized.split())
        polish_hits = len(words & self.POLISH_HINT_WORDS)
        english_hits = len(words & self.ENGLISH_HINT_WORDS)

        if language == "pl":
            return polish_hits * 0.32 - english_hits * 0.12
        if language == "en":
            return english_hits * 0.28 - polish_hits * 0.10
        return 0.0

    def _question_shape_bonus(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        polish_starts = (
            "ktora ", "która ", "jaka ", "kim ", "jak ", "czy ", "pokaz ", "pokaż ",
            "wyswietl ", "wyświetl ", "wytlumacz ", "wytłumacz ", "wyjasnij ", "wyjaśnij ",
            "przypomnij ", "zapamietaj ", "zapamiętaj ",
        )
        english_starts = (
            "what ", "who ", "how ", "show ", "tell ", "explain ", "turn ", "close ",
            "remember ", "remind ", "set ", "start ",
        )

        if language == "pl" and normalized.startswith(polish_starts):
            return 0.55
        if language == "en" and normalized.startswith(english_starts):
            return 0.45
        return 0.0

    def _false_positive_penalty(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        penalty = 0.0
        if language == "en":
            for phrase in self.SUSPICIOUS_ENGLISH_FALSE_POSITIVES:
                if phrase in normalized:
                    penalty += 2.2
            if normalized.startswith("thank ") and len(normalized.split()) <= 4:
                penalty += 1.4
            if normalized in {"thank you", "thanks", "thank you very much"}:
                penalty += 3.0
        if language == "pl" and normalized in {"tak", "nie"}:
            penalty += 0.4
        return penalty

    def _guess_hint_language(self, text: str) -> str | None:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return None

        words = set(normalized.split())
        polish_hits = len(words & self.POLISH_HINT_WORDS)
        english_hits = len(words & self.ENGLISH_HINT_WORDS)

        if polish_hits > english_hits:
            return "pl"
        if english_hits > polish_hits:
            return "en"
        return None

    def _strong_command_match(self, text: str) -> bool:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return False

        for phrases in self.SHORT_COMMAND_PHRASES.values():
            if normalized in phrases:
                return True
        return False

    @staticmethod
    def _normalize_scoring_text(text: str) -> str:
        cleaned = str(text or "").strip().lower()
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
        cleaned = cleaned.replace("ł", "l")
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _contains_unsupported_script(text: str) -> bool:
        if not text:
            return False
        for char in text:
            code = ord(char)
            if 0x4E00 <= code <= 0x9FFF:
                return True
            if 0x3400 <= code <= 0x4DBF:
                return True
            if 0x3040 <= code <= 0x30FF:
                return True
            if 0xAC00 <= code <= 0xD7AF:
                return True
        return False

    @classmethod
    def _looks_like_blank_or_garbage(cls, text: str) -> bool:
        cleaned = cls._normalize_scoring_text(text)
        if not cleaned:
            return True
        if cleaned in cls.NON_SPEECH_TRANSCRIPTS:
            return True

        alpha_only = re.sub(r"[^a-z]", "", cleaned)
        if not alpha_only:
            return True

        short_noise = {
            "hm", "hmm", "uh", "um", "eh", "ah", "mmm", "yy", "yyy", "eee",
            "foreign", "noise", "music",
        }
        if cleaned in short_noise:
            return True

        if len(alpha_only) <= 1:
            return True

        tokens = cleaned.split()
        if len(tokens) <= 3:
            non_speech_keywords = {
                "keyboard", "typing", "knocking", "chair", "movement", "moving", "clap",
                "clapping", "applause", "music", "noise", "static", "foreign", "thanks", "thank",
            }
            if set(tokens).issubset(non_speech_keywords):
                return True

        return False

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
            LOGGER.warning("Silero trim warning: %s", error)
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
                LOGGER.warning("Silero retry extraction warning: %s", error)
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

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            LOGGER.warning("FasterWhisper input capture failed: %s", error)
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if transcript is None:
            return None

        cleaned = self._cleanup_transcript(transcript)
        if cleaned is None or self._looks_like_blank_or_garbage(cleaned):
            return None

        if debug:
            print(f"Selected transcript from FasterWhisper backend: {cleaned}")
        return cleaned

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        return self.listen(timeout=timeout, debug=debug)

    def listen_for_command(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        return self.listen(timeout=timeout, debug=debug)

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        if not ignore_audio_block and (self._input_blocked_by_assistant_output() or self._recently_unblocked()):
            if debug:
                print("Wake capture skipped because audio shield is active or just released.")
            return None

        effective_timeout = min(max(float(timeout), 0.25), self.wake_timeout_seconds)

        try:
            audio = self._record_until_silence(
                timeout=effective_timeout,
                debug=debug,
                end_silence_seconds=self.wake_end_silence_seconds,
                min_speech_seconds=self.wake_min_speech_seconds,
                pre_roll_seconds=self.wake_pre_roll_seconds,
                flush_queue=False,
            )
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            LOGGER.warning("FasterWhisper wake capture failed: %s", error)
            return None

        wake_text = self._transcribe_wake_audio(audio, debug=debug)
        if wake_text is None:
            return None

        if debug:
            print(f"Wake phrase accepted by FasterWhisper backend: {wake_text}")

        return "nexa"

    def _transcribe_wake_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        self._ensure_faster_whisper_runtime()
        if self._fw_model is None or audio.size == 0:
            return None

        prepared_audio = self._prepare_audio_for_wake_model(audio)
        if prepared_audio is None:
            return None

        best_text: str | None = None
        best_score = -999.0

        for forced_language in self.wake_forced_languages:
            candidate = self._transcribe_single_audio(
                prepared_audio,
                debug=debug,
                label="wake-fast",
                forced_language=forced_language,
            )
            text = str(candidate.get("text") or "").strip()
            if not text:
                continue

            score = self._wake_candidate_score(candidate)
            if score > best_score:
                best_score = score
                best_text = text

            if self._looks_like_isolated_wake_text(text):
                return text

        if best_text is None:
            return None
        if not self._contains_wake_alias(best_text):
            return None
        return best_text

    def _wake_candidate_score(self, candidate: dict[str, Any]) -> float:
        text = str(candidate.get("text") or "").strip()
        if not text:
            return -999.0

        normalized = self._normalize_wake_text(text)
        probability = float(candidate.get("language_probability") or 0.0)
        score = probability

        if self._looks_like_isolated_wake_text(normalized):
            score += 4.0
        if self._contains_wake_alias(normalized):
            score += 3.0

        token_count = len(normalized.split())
        if token_count <= 2:
            score += 0.7
        elif token_count <= 4:
            score += 0.25
        else:
            score -= 1.0

        if self._looks_like_blank_or_garbage(text):
            score -= 5.0
        if self._contains_unsupported_script(text):
            score -= 5.0

        return score

    @classmethod
    def _contains_wake_alias(cls, text: str) -> bool:
        normalized = cls._normalize_wake_text(text)
        if not normalized:
            return False

        tokens = [token for token in normalized.split() if token]
        for token in tokens[:6]:
            compact = re.sub(r"[^a-z0-9]", "", token)
            if compact in cls.WAKE_ALIASES:
                return True
            if compact.startswith("nex") and len(compact) <= 8:
                return True

        compact_text = re.sub(r"[^a-z0-9]", "", normalized)
        return compact_text.startswith("nex") and len(compact_text) <= 12

    @classmethod
    def _looks_like_isolated_wake_text(cls, text: str) -> bool:
        normalized = cls._normalize_wake_text(text)
        if not normalized:
            return False

        tokens = [token for token in normalized.split() if token]
        if not tokens or len(tokens) > 4:
            return False

        filtered = [token for token in tokens if token not in cls.WAKE_FILLER_WORDS]
        if not filtered:
            return False

        for token in filtered:
            compact = re.sub(r"[^a-z0-9]", "", token)
            if compact in cls.WAKE_ALIASES:
                continue
            if compact.startswith("nex") and len(compact) <= 8:
                continue
            return False

        return True

    @staticmethod
    def _normalize_wake_text(text: str) -> str:
        cleaned = str(text or "").strip().lower()
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
        cleaned = cleaned.replace("ł", "l")
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def close(self) -> None:
        self._clear_audio_queue()
        self._close_stream()
        try:
            for path in self._session_temp_dir.glob("*"):
                try:
                    path.unlink()
                except OSError:
                    pass
            self._session_temp_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def list_audio_devices() -> None:
        print(sd.query_devices())

    @staticmethod
    def _cleanup_transcript(text: str | None) -> str | None:
        if text is None:
            return None

        cleaned = str(text).strip()
        if not cleaned:
            return None

        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.replace("[BLANK_AUDIO]", "").replace("[NOISE]", "").strip()
        if not cleaned:
            return None

        lowered_words = cleaned.lower().split()
        if len(lowered_words) >= 12:
            for chunk_size in range(4, min(12, len(lowered_words) // 2) + 1):
                phrase = lowered_words[:chunk_size]
                repeats = 1
                index = chunk_size
                while index + chunk_size <= len(lowered_words):
                    if lowered_words[index:index + chunk_size] == phrase:
                        repeats += 1
                        index += chunk_size
                    else:
                        break
                if repeats >= 3:
                    return None

        if FasterWhisperInputBackend._looks_like_repetition_hallucination(cleaned):
            return None

        return cleaned

    @staticmethod
    def _looks_like_repetition_hallucination(text: str) -> bool:
        cleaned = str(text or "").strip().lower()
        if not cleaned:
            return False

        words = cleaned.split()
        if len(words) < 12:
            return False

        for chunk_size in range(2, min(8, len(words) // 3) + 1):
            repeats = 1
            phrase = words[:chunk_size]
            index = chunk_size
            while index + chunk_size <= len(words):
                if words[index:index + chunk_size] == phrase:
                    repeats += 1
                    index += chunk_size
                else:
                    break
            if repeats >= 3:
                return True

        unique_ratio = len(set(words)) / max(len(words), 1)
        return len(words) >= 18 and unique_ratio < 0.38

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


__all__ = ["FasterWhisperInputBackend"]