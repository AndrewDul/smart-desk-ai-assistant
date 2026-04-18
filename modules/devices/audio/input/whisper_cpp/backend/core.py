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

from .audio_utils_mixin import WhisperCppAudioUtilsMixin
from .capture_mixin import WhisperCppCaptureMixin
from .file_io_mixin import WhisperCppFileIOMixin
from .runtime_mixin import WhisperCppRuntimeMixin
from .text_filters_mixin import WhisperCppTextFiltersMixin
from .transcription_mixin import WhisperCppTranscriptionMixin

LOGGER = logging.getLogger(__name__)


class WhisperCppInputBackend(
    WhisperCppRuntimeMixin,
    WhisperCppTextFiltersMixin,
    WhisperCppAudioUtilsMixin,
    WhisperCppFileIOMixin,
    WhisperCppCaptureMixin,
    WhisperCppTranscriptionMixin,
):
    """
    Premium offline speech-input backend based on whisper.cpp.

    Responsibilities:
    - microphone capture
    - assistant-output shielding integration
    - speech onset / end-of-utterance detection
    - utterance trimming
    - whisper.cpp transcription
    - bilingual rescue logic for Polish / English
    """

    LOGGER = LOGGER

    MODEL_SAMPLE_RATE = 16000
    SUPPORTED_LANGUAGES = {"pl", "en"}

    POLISH_HINT_WORDS = {
        "ktora",
        "która",
        "jaka",
        "godzina",
        "godzine",
        "czas",
        "kim",
        "jestes",
        "jesteś",
        "jak",
        "sie",
        "się",
        "nazywasz",
        "pokaz",
        "pokaż",
        "wyswietl",
        "wyświetl",
        "powiedz",
        "wyjasnij",
        "wyjaśnij",
        "wytlumacz",
        "wytłumacz",
        "zrob",
        "zrób",
        "pomoz",
        "pomóż",
        "pomoc",
        "przypomnienie",
        "przypomnienia",
        "timer",
        "focus",
        "fokus",
        "przerwa",
        "wylacz",
        "wyłącz",
        "zamknij",
        "asystenta",
        "system",
        "dziekuje",
        "dziękuję",
        "dzieki",
        "dzięki",
        "nie",
        "tak",
        "anuluj",
        "niewazne",
        "nieważne",
        "klucze",
        "kuchni",
        "imie",
        "imię",
    }

    ENGLISH_HINT_WORDS = {
        "what",
        "time",
        "who",
        "are",
        "you",
        "your",
        "name",
        "show",
        "tell",
        "explain",
        "help",
        "timer",
        "reminder",
        "focus",
        "break",
        "turn",
        "off",
        "close",
        "assistant",
        "system",
        "yes",
        "no",
        "cancel",
        "nevermind",
        "never",
        "mind",
        "keys",
        "kitchen",
    }

    SHORT_COMMAND_PHRASES = {
        "en": {
            "yes",
            "no",
            "cancel",
            "never mind",
            "nevermind",
            "stop",
            "what time is it",
            "what day is it",
            "what month is it",
            "what year is it",
            "who are you",
            "what is your name",
            "show it",
            "show that",
            "tell me",
            "help me",
            "close assistant",
            "shutdown system",
            "where are the keys",
        },
        "pl": {
            "tak",
            "nie",
            "anuluj",
            "niewazne",
            "nie wazne",
            "zostaw to",
            "zapomnij",
            "ktora godzina",
            "która godzina",
            "jaki dzien",
            "jaki dzień",
            "jaki miesiac",
            "jaki miesiąc",
            "jaki rok",
            "kim jestes",
            "kim jesteś",
            "jak masz na imie",
            "jak masz na imię",
            "pokaz to",
            "pokaż to",
            "pomoz mi",
            "pomóż mi",
            "zamknij asystenta",
            "wylacz system",
            "wyłącz system",
            "gdzie sa klucze",
            "gdzie są klucze",
        },
    }

    SUSPICIOUS_ENGLISH_FALSE_POSITIVES = (
        "thank you very much",
        "thanks for watching",
        "they won t",
        "they wont",
        "matchminton",
        "ocean ive",
    )

    def __init__(
        self,
        *,
        whisper_cli_path: str = "third_party/whisper.cpp/build/bin/whisper-cli",
        model_path: str = "models/whisper/ggml-base.bin",
        vad_enabled: bool = True,
        vad_model_path: str | None = "models/whisper/ggml-silero-v6.2.0.bin",
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
        cpu_threads: int = 4,
    ) -> None:
        self.language = self._normalize_language(language, allow_auto=True)
        self.vad_enabled = bool(vad_enabled)
        self.cpu_threads = max(int(cpu_threads), 1)

        self.max_record_seconds = max(float(max_record_seconds), 4.0)
        self.end_silence_seconds = max(float(end_silence_seconds), 0.18)
        self.pre_roll_seconds = max(float(pre_roll_seconds), 0.08)
        self.blocksize = max(int(blocksize), 256)
        self.channels = 1
        self.dtype = "int16"
        self.min_speech_seconds = max(float(min_speech_seconds), 0.10)
        self.transcription_timeout_seconds = max(float(transcription_timeout_seconds), 3.0)

        self.whisper_cli_path = self._resolve_whisper_cli_path(whisper_cli_path)
        self.model_path = self._resolve_project_path(model_path)
        self.vad_model_path = (
            self._resolve_project_path(vad_model_path)
            if vad_model_path
            else None
        )

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=24)
        self.audio_coordinator: AssistantAudioCoordinator | None = None

        selection = resolve_input_device_selection(
            device_index=device_index,
            device_name_contains=device_name_contains,
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
            context_label="WhisperCppInputBackend",
        )

        self.energy_speech_threshold = 0.0070
        self.input_unblock_settle_seconds = 0.20
        self.debug_print_cooldown_seconds = 0.35
        self._last_input_blocked_monotonic = 0.0
        self._last_debug_print_monotonic = 0.0

        self._session_temp_dir = Path(tempfile.mkdtemp(prefix="nexa_whisper_cpp_"))
        self._wav_path = self._session_temp_dir / "utterance.wav"
        self._output_prefix_base = self._session_temp_dir / "utterance"

        self._ensure_runtime_ready()

        self.LOGGER.info(
            "WhisperCppInputBackend prepared: device='%s', sample_rate=%s, language_mode=%s, vad=%s, selection_reason='%s', available_inputs='%s'",
            self.device_name,
            self.sample_rate,
            self.language,
            "on" if self.vad_enabled else "off",
            self.device_selection_reason,
            self.available_input_devices_summary,
        )

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            self.LOGGER.warning("Whisper.cpp input capture failed: %s", error)
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if debug and transcript:
            print(f"Selected transcript from whisper.cpp backend: {transcript}")
        return transcript

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> str | None:
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
            self.LOGGER.warning("Whisper.cpp rich transcribe capture failed: %s", error)
            return None

        candidate = self._transcribe_audio_candidate(audio, debug=debug)
        if candidate is None:
            return None

        cleaned = str(candidate.get("text") or "").strip()
        if not cleaned:
            return None

        ended_at = time.monotonic()
        audio_duration_seconds = 0.0
        try:
            audio_duration_seconds = max(0.0, float(audio.size) / float(self.sample_rate))
        except Exception:
            audio_duration_seconds = 0.0

        language = str(candidate.get("language") or "auto").strip().lower() or "auto"

        try:
            language_probability = float(candidate.get("language_probability") or 0.0)
        except (TypeError, ValueError):
            language_probability = 0.0
        language_probability = max(0.0, min(1.0, language_probability))

        try:
            transcription_elapsed_seconds = float(candidate.get("elapsed") or 0.0)
        except (TypeError, ValueError):
            transcription_elapsed_seconds = 0.0
        transcription_elapsed_seconds = max(0.0, transcription_elapsed_seconds)

        forced_language = str(candidate.get("forced_language") or "").strip().lower()
        transcription_path = str(candidate.get("path") or "primary").strip().lower() or "primary"

        confidence = language_probability
        if confidence <= 0.0:
            confidence = 1.0 if forced_language else 0.0

        metadata = dict(request.metadata or {})
        metadata.setdefault("mode", mode)
        metadata.setdefault("backend_label", "whisper_cpp")
        metadata.setdefault("adapter", "backend_native")
        metadata.setdefault("audio_duration_seconds", audio_duration_seconds)
        metadata.setdefault("detected_language", language)
        metadata.setdefault("language_probability", language_probability)
        metadata.setdefault("transcription_elapsed_seconds", transcription_elapsed_seconds)
        metadata.setdefault("forced_language", forced_language)
        metadata.setdefault("transcription_path", transcription_path)
        metadata.setdefault("rescue_used", transcription_path == "rescue")
        metadata.setdefault("retry_used", False)
        metadata.setdefault("engine", str(candidate.get("engine") or "whisper_cpp"))

        return TranscriptResult(
            text=cleaned,
            language=language,
            confidence=confidence,
            is_final=True,
            source=request.source if isinstance(request.source, InputSource) else InputSource.VOICE,
            started_at=started_at,
            ended_at=ended_at,
            metadata=metadata,
        )


    def close(self) -> None:
        self._clear_audio_queue()
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