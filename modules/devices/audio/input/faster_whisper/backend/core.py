from __future__ import annotations

import logging
import queue
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult

import numpy as np
import sounddevice as sd
from modules.devices.audio.input.shared import (
    resolve_input_device_selection,
    resolve_supported_input_sample_rate,
)

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator

from .audio_utils_mixin import FasterWhisperAudioUtilsMixin
from .capture_mixin import FasterWhisperCaptureMixin
from .runtime_mixin import FasterWhisperRuntimeMixin
from .text_filters_mixin import FasterWhisperTextFiltersMixin
from .transcription_mixin import FasterWhisperTranscriptionMixin
from .wake_mixin import FasterWhisperWakeMixin

LOGGER = logging.getLogger(__name__)


class FasterWhisperInputBackend(
    FasterWhisperRuntimeMixin,
    FasterWhisperTextFiltersMixin,
    FasterWhisperAudioUtilsMixin,
    FasterWhisperCaptureMixin,
    FasterWhisperTranscriptionMixin,
    FasterWhisperWakeMixin,
):
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

    LOGGER = LOGGER

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
        device_discovery_timeout_seconds: float = 8.0,
        device_discovery_poll_seconds: float = 0.35,
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

        selection = resolve_input_device_selection(
            device_index=device_index,
            device_name_contains=device_name_contains,
            discovery_timeout_seconds=device_discovery_timeout_seconds,
            discovery_poll_seconds=device_discovery_poll_seconds,
        )
        self.device = selection.device
        self.device_name = selection.name
        self.device_default_sample_rate = selection.default_sample_rate
        self.device_selection_reason = selection.reason
        self.available_input_devices_summary = selection.available_inputs_summary
        self.sample_rate = resolve_supported_input_sample_rate(
            device=self.device,
            device_name=self.device_name,
            channels=self.channels,
            dtype=self.dtype,
            preferred_sample_rate=sample_rate,
            default_sample_rate=self.device_default_sample_rate,
            logger=self.LOGGER,
            context_label="FasterWhisperInputBackend",
        )

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

        self.LOGGER.info(
            "FasterWhisperInputBackend prepared: device='%s', sample_rate=%s, language_mode=%s, vad=%s, selection_reason='%s', available_inputs='%s'",
            self.device_name,
            self.sample_rate,
            self.language,
            "on" if self.vad_enabled else "off",
            self.device_selection_reason,
            self.available_input_devices_summary,
        )

        try:
            self._ensure_runtime_ready()
        except Exception as error:
            self.LOGGER.warning("FasterWhisper warmup will be retried lazily. Reason: %s", error)

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            self.LOGGER.warning("FasterWhisper input capture failed: %s", error)
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


    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        started_at = time.monotonic()
        timeout = max(0.1, float(request.timeout_seconds))
        debug = bool(request.debug)
        mode = str(request.mode or "command").strip().lower() or "command"

        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            self.LOGGER.warning("FasterWhisper rich transcribe capture failed: %s", error)
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if transcript is None:
            return None

        cleaned = self._cleanup_transcript(transcript)
        if cleaned is None or self._looks_like_blank_or_garbage(cleaned):
            return None

        ended_at = time.monotonic()
        audio_duration_seconds = 0.0
        try:
            audio_duration_seconds = max(0.0, float(audio.size) / float(self.sample_rate))
        except Exception:
            audio_duration_seconds = 0.0

        metadata = dict(request.metadata or {})
        metadata.setdefault("mode", mode)
        metadata.setdefault("backend_label", "faster_whisper")
        metadata.setdefault("adapter", "backend_native")
        metadata.setdefault("audio_duration_seconds", audio_duration_seconds)

        language = self.language if str(self.language or "").strip() else "auto"

        return TranscriptResult(
            text=cleaned,
            language=language,
            confidence=0.0,
            is_final=True,
            source=request.source if isinstance(request.source, InputSource) else InputSource.VOICE,
            started_at=started_at,
            ended_at=ended_at,
            metadata=metadata,
        )


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
            self.LOGGER.warning("FasterWhisper wake capture failed: %s", error)
            return None

        wake_text = self._transcribe_wake_audio(audio, debug=debug)
        if wake_text is None:
            return None

        if debug:
            print(f"Wake phrase accepted by FasterWhisper backend: {wake_text}")

        return "nexa"

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