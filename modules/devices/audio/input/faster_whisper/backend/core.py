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
        capture_profiles: dict[str, dict[str, float]] | None = None,
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

        self.capture_profiles = self._build_capture_profiles(capture_profiles)

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



    def _build_capture_profiles(
        self,
        overrides: dict[str, dict[str, float]] | None,
    ) -> dict[str, dict[str, float]]:
        base_profile = {
            "timeout_seconds": max(self.max_record_seconds, 0.25),
            "end_silence_seconds": self.end_silence_seconds,
            "min_speech_seconds": self.min_speech_seconds,
            "pre_roll_seconds": self.pre_roll_seconds,
        }
        profile_map = {
            "default": dict(base_profile),
            "command": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 5.2),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.40),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.14),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.24),
                },
            ),
            "inline_command_after_wake": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 4.2),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.32),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.12),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.18),
                },
            ),
            "wake_command": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 4.4),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.26),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.10),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.14),
                },
            ),
            "follow_up": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 4.8),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.34),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.12),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.20),
                },
            ),
            "grace": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 3.2),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.28),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.10),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.16),
                },
            ),
            "conversation": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": max(base_profile["timeout_seconds"], 6.5),
                    "end_silence_seconds": max(base_profile["end_silence_seconds"], 0.60),
                    "min_speech_seconds": max(base_profile["min_speech_seconds"], 0.20),
                    "pre_roll_seconds": max(base_profile["pre_roll_seconds"], 0.45),
                },
            ),
            "wake_fallback": self._merge_capture_profile(
                base_profile,
                {
                    "timeout_seconds": min(base_profile["timeout_seconds"], 1.5),
                    "end_silence_seconds": min(base_profile["end_silence_seconds"], 0.18),
                    "min_speech_seconds": min(base_profile["min_speech_seconds"], 0.07),
                    "pre_roll_seconds": min(base_profile["pre_roll_seconds"], 0.10),
                },
            ),
        }

        for profile_name, profile_overrides in (overrides or {}).items():
            normalized_name = str(profile_name or "").strip().lower()
            if not normalized_name:
                continue
            reference_profile = profile_map.get(normalized_name, profile_map["default"])
            profile_map[normalized_name] = self._merge_capture_profile(
                reference_profile,
                profile_overrides,
            )

        return profile_map

    @staticmethod
    def _merge_capture_profile(
        base_profile: dict[str, float],
        overrides: dict[str, float] | None,
    ) -> dict[str, float]:
        profile = dict(base_profile)
        for key, raw_value in (overrides or {}).items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key not in {
                "timeout_seconds",
                "end_silence_seconds",
                "min_speech_seconds",
                "pre_roll_seconds",
            }:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if normalized_key == "timeout_seconds":
                profile[normalized_key] = max(value, 0.25)
            else:
                profile[normalized_key] = max(value, 0.05)
        return profile

    def _resolve_capture_profile(
        self,
        mode: str,
        timeout_seconds: float,
    ) -> tuple[str, dict[str, float]]:
        profiles = getattr(self, "capture_profiles", None)
        if not isinstance(profiles, dict) or not profiles:
            base_timeout = max(float(getattr(self, "max_record_seconds", timeout_seconds or 8.0)), 0.25)
            profiles = {
                "default": {
                    "timeout_seconds": base_timeout,
                    "end_silence_seconds": max(float(getattr(self, "end_silence_seconds", 0.65)), 0.05),
                    "min_speech_seconds": max(float(getattr(self, "min_speech_seconds", 0.20)), 0.05),
                    "pre_roll_seconds": max(float(getattr(self, "pre_roll_seconds", 0.45)), 0.05),
                }
            }

        normalized_mode = str(mode or "command").strip().lower() or "command"
        profile_name = normalized_mode if normalized_mode in profiles else "default"
        profile = dict(profiles.get(profile_name, profiles["default"]))
        requested_timeout = max(float(timeout_seconds), 0.25)
        max_record_seconds = max(float(getattr(self, "max_record_seconds", profile["timeout_seconds"])), 0.25)
        profile["timeout_seconds"] = min(requested_timeout, float(profile["timeout_seconds"]))
        profile["timeout_seconds"] = min(profile["timeout_seconds"], max_record_seconds)
        profile["timeout_seconds"] = max(profile["timeout_seconds"], 0.25)
        return profile_name, profile

    def _record_with_capture_profile(
        self,
        *,
        mode: str,
        timeout_seconds: float,
        debug: bool,
        flush_queue: bool = True,
    ) -> tuple[np.ndarray | None, str, dict[str, float]]:
        profile_name, profile = self._resolve_capture_profile(mode, timeout_seconds)
        try:
            audio = self._record_until_silence(
                timeout=float(profile["timeout_seconds"]),
                debug=debug,
                end_silence_seconds=float(profile["end_silence_seconds"]),
                min_speech_seconds=float(profile["min_speech_seconds"]),
                pre_roll_seconds=float(profile["pre_roll_seconds"]),
                flush_queue=flush_queue,
            )
        except TypeError:
            audio = self._record_until_silence(
                timeout=float(profile["timeout_seconds"]),
                debug=debug,
            )
        return audio, profile_name, profile


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
            audio, capture_profile_name, capture_profile = self._record_with_capture_profile(
                mode=mode,
                timeout_seconds=timeout,
                debug=debug,
            )
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            self.LOGGER.warning("FasterWhisper rich transcribe capture failed: %s", error)
            return None

        capture_finished_at = time.monotonic()
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

        metadata = dict(request.metadata or {})
        metadata.setdefault("mode", mode)
        metadata.setdefault("backend_label", "faster_whisper")
        metadata.setdefault("adapter", "backend_native")
        metadata.setdefault("audio_duration_seconds", audio_duration_seconds)
        metadata.setdefault("detected_language", language)
        metadata.setdefault("language_probability", language_probability)
        metadata.setdefault("transcription_elapsed_seconds", transcription_elapsed_seconds)
        metadata.setdefault("forced_language", forced_language)
        metadata.setdefault("transcription_path", transcription_path)
        metadata.setdefault("rescue_used", transcription_path in {"rescue", "retry_rescue"})
        metadata.setdefault("retry_used", transcription_path in {"retry", "retry_rescue"})
        metadata.setdefault("engine", str(candidate.get("engine") or "faster_whisper"))
        metadata.setdefault("capture_profile", capture_profile_name)
        metadata.setdefault("capture_timeout_seconds", float(capture_profile["timeout_seconds"]))
        metadata.setdefault("capture_end_silence_seconds", float(capture_profile["end_silence_seconds"]))
        metadata.setdefault("capture_min_speech_seconds", float(capture_profile["min_speech_seconds"]))
        metadata.setdefault("capture_pre_roll_seconds", float(capture_profile["pre_roll_seconds"]))
        metadata.setdefault("capture_finished_at_monotonic", capture_finished_at)
        metadata.setdefault(
            "capture_elapsed_seconds",
            max(0.0, capture_finished_at - started_at),
        )

        return TranscriptResult(
            text=cleaned,
            language=language,
            confidence=language_probability,
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

    def release_capture_ownership(self) -> bool:
        # Close the InputStream so the wake gate (separate process on the
        # same USB mic) can reopen it. On Linux ALSA without PipeWire, a
        # second client cannot open a capture device that another client
        # is still holding — even if the first client is "idle". Previous
        # behaviour (clear queue but keep stream alive) worked under Pulse
        # but causes the wake gate to fail silently on bare ALSA.
        self._clear_audio_queue()
        self._close_stream()
        return True

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