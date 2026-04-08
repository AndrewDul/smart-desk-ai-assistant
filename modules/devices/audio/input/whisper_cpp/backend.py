from __future__ import annotations

import logging
import queue
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import wave
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


LOGGER = logging.getLogger(__name__)


class WhisperCppInputBackend:
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

        self.device = self._resolve_input_device(device_index, device_name_contains)
        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.device_default_sample_rate = int(
            round(float(input_info.get("default_samplerate", 16000)))
        )
        self.sample_rate = self._resolve_supported_sample_rate(sample_rate)

        self.energy_speech_threshold = 0.0070
        self.input_unblock_settle_seconds = 0.20
        self.debug_print_cooldown_seconds = 0.35
        self._last_input_blocked_monotonic = 0.0
        self._last_debug_print_monotonic = 0.0

        self._session_temp_dir = Path(tempfile.mkdtemp(prefix="nexa_whisper_cpp_"))
        self._wav_path = self._session_temp_dir / "utterance.wav"
        self._output_prefix_base = self._session_temp_dir / "utterance"

        self._ensure_runtime_ready()

        LOGGER.info(
            "WhisperCppInputBackend prepared: device='%s', sample_rate=%s, language_mode=%s, vad=%s",
            self.device_name,
            self.sample_rate,
            self.language,
            "on" if self.vad_enabled else "off",
        )

    @classmethod
    def _normalize_language(cls, language: str | None, *, allow_auto: bool = False) -> str:
        normalized = str(language or "").strip().lower()
        if allow_auto and normalized in {"", "auto"}:
            return "auto"
        if normalized in cls.SUPPORTED_LANGUAGES:
            return normalized
        return "auto" if allow_auto else "en"

    @staticmethod
    def _discover_project_root() -> Path:
        current = Path(__file__).resolve()
        for candidate in current.parents:
            if (candidate / "modules").exists() and (candidate / "config").exists():
                return candidate
        return current.parents[5]

    @classmethod
    def _resolve_project_path(cls, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return cls._discover_project_root() / candidate

    @classmethod
    def _resolve_whisper_cli_path(cls, whisper_cli_path: str) -> Path:
        direct_path = cls._resolve_project_path(whisper_cli_path)
        if direct_path.exists():
            return direct_path

        cli_name = Path(whisper_cli_path).name
        discovered = shutil.which(cli_name) or shutil.which("whisper-cli")
        if discovered:
            return Path(discovered)

        return direct_path

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

    def _ensure_runtime_ready(self) -> None:
        if not self.whisper_cli_path.exists():
            raise FileNotFoundError(f"whisper-cli not found at: {self.whisper_cli_path}")

        if not self.model_path.exists():
            raise FileNotFoundError(f"Whisper model not found at: {self.model_path}")

        if self.vad_enabled and self.vad_model_path and not self.vad_model_path.exists():
            LOGGER.warning(
                "Whisper VAD model not found at '%s'. whisper.cpp will continue without CLI VAD.",
                self.vad_model_path,
            )

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            LOGGER.warning("Whisper.cpp audio callback status: %s", status)

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
            LOGGER.warning("Whisper.cpp audio callback error: %s", error)

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

    def _transcribe_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        if audio.size == 0:
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        if trimmed_audio.size == 0:
            trimmed_audio = audio

        auto_candidate = self._transcribe_candidate(
            trimmed_audio,
            forced_language=None,
            label="auto",
            debug=debug,
        )
        if self._accept_candidate(auto_candidate):
            return str(auto_candidate.get("text") or "").strip() or None

        rescue_candidates: list[dict[str, Any]] = []
        for forced_language in self._preferred_rescue_languages(auto_candidate):
            candidate = self._transcribe_candidate(
                trimmed_audio,
                forced_language=forced_language,
                label=f"rescue_{forced_language}",
                debug=debug,
            )
            if candidate.get("text"):
                rescue_candidates.append(candidate)

        if rescue_candidates:
            rescue_candidates.sort(
                key=lambda item: self._candidate_score(
                    item,
                    primary_language=str(auto_candidate.get("language") or "") or None,
                ),
                reverse=True,
            )
            best = rescue_candidates[0]
            if self._candidate_score(
                best,
                primary_language=str(auto_candidate.get("language") or "") or None,
            ) > 0.0:
                return str(best.get("text") or "").strip() or None

        return None

    def _transcribe_candidate(
        self,
        audio: np.ndarray,
        *,
        forced_language: str | None,
        label: str,
        debug: bool = False,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "text": None,
            "language": forced_language or "auto",
            "language_probability": 0.0,
            "elapsed": 0.0,
            "forced_language": forced_language,
            "engine": "whisper_cpp",
        }

        try:
            wav_path = self._write_temp_wav(audio)
            started_at = self._now()
            transcript = self._run_whisper_cpp(
                wav_path,
                forced_language=forced_language,
                label=label,
                debug=debug,
            )
            elapsed = self._now() - started_at
            cleaned = self._cleanup_transcript(transcript)
            guessed_language = forced_language or self._detect_language_from_text(cleaned or "") or "auto"

            candidate.update(
                {
                    "text": cleaned,
                    "language": self._normalize_language(guessed_language, allow_auto=True),
                    "elapsed": elapsed,
                }
            )

            if debug and self._debug_print_allowed():
                printable = cleaned if cleaned else "<empty>"
                mode_label = label if forced_language is None else f"{label}:{forced_language}"
                print(
                    f"Whisper.cpp {mode_label} transcript: {printable} | "
                    f"lang={candidate['language']} elapsed={elapsed:.2f}s"
                )

            return candidate
        except Exception as error:
            LOGGER.warning("Whisper.cpp transcription error (%s): %s", label, error)
            return candidate

    def _write_temp_wav(self, audio: np.ndarray) -> Path:
        pcm = self._float32_audio_to_int16(audio)
        with wave.open(str(self._wav_path), "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return self._wav_path

    def _transcript_prefix(self, label: str) -> Path:
        safe_label = re.sub(r"[^a-zA-Z0-9_\-]", "_", label)
        return self._output_prefix_base.with_name(f"{self._output_prefix_base.name}_{safe_label}")

    def _clear_previous_transcript_files(self, label: str) -> None:
        prefix = self._transcript_prefix(label)
        for suffix in (".txt", ".json", ".srt", ".vtt", ".lrc"):
            path = prefix.with_suffix(suffix)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    def _build_whisper_cpp_command(
        self,
        wav_path: Path,
        *,
        output_label: str,
        forced_language: str | None,
    ) -> list[str]:
        prefix = self._transcript_prefix(output_label)
        cmd = [
            str(self.whisper_cli_path),
            "--model",
            str(self.model_path),
            "--threads",
            str(self.cpu_threads),
            "--output-txt",
            "--no-timestamps",
            "--no-prints",
            "--output-file",
            str(prefix),
            "--file",
            str(wav_path),
        ]

        if forced_language:
            cmd.extend(["--language", forced_language])
        elif self.language in self.SUPPORTED_LANGUAGES:
            cmd.extend(["--language", self.language])

        if (
            self.vad_enabled
            and self.vad_model_path is not None
            and self.vad_model_path.exists()
        ):
            cmd.extend(["--vad", "--vad-model", str(self.vad_model_path)])

        return cmd

    def _run_whisper_cpp(
        self,
        wav_path: Path,
        *,
        forced_language: str | None,
        label: str,
        debug: bool = False,
    ) -> str:
        self._clear_previous_transcript_files(label)
        cmd = self._build_whisper_cpp_command(
            wav_path,
            output_label=label,
            forced_language=forced_language,
        )

        completed = subprocess.run(
            cmd,
            capture_output=debug,
            text=True,
            check=False,
            timeout=self.transcription_timeout_seconds,
        )

        if completed.returncode != 0:
            if debug:
                raise RuntimeError(
                    f"Whisper.cpp transcription failed. STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
                )
            raise RuntimeError("Whisper.cpp transcription failed.")

        transcript_path = self._transcript_prefix(label).with_suffix(".txt")
        if not transcript_path.exists():
            return ""
        return transcript_path.read_text(encoding="utf-8").strip()

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

        if not text:
            return False
        if self._contains_unsupported_script(text):
            return False
        if self._looks_like_blank_or_garbage(text):
            return False
        if self._strong_command_match(text):
            return True

        word_count = len(text.split())

        if language in self.SUPPORTED_LANGUAGES and word_count >= 2:
            return True
        return word_count >= 4

    def _candidate_score(
        self,
        candidate: dict[str, Any],
        *,
        primary_language: str | None = None,
    ) -> float:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()

        if not text:
            return -10.0

        score = 0.0
        score += min(len(text.split()), 8) * 0.25

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
            "yes",
            "no",
            "tak",
            "nie",
            "cancel",
            "anuluj",
            "timer",
            "focus",
            "break",
            "exit",
            "shutdown",
            "set timer",
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
            "ktora ",
            "która ",
            "jaka ",
            "kim ",
            "jak ",
            "czy ",
            "pokaz ",
            "pokaż ",
            "wyswietl ",
            "wyświetl ",
            "wytlumacz ",
            "wytłumacz ",
            "wyjasnij ",
            "wyjaśnij ",
        )
        english_starts = (
            "what ",
            "who ",
            "how ",
            "show ",
            "tell ",
            "explain ",
            "turn ",
            "close ",
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
                penalty += 1.2
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

    def _detect_language_from_text(self, text: str) -> str | None:
        if not text:
            return None
        if re.search(r"[ąćęłńóśźż]", text.lower()):
            return "pl"
        return self._guess_hint_language(text)

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

    @staticmethod
    def _looks_like_blank_or_garbage(text: str) -> bool:
        cleaned = str(text or "").strip().lower()
        if not cleaned:
            return True
        return cleaned in {
            "[blank_audio]",
            "[noise]",
            "blank audio",
            "noise",
            "music",
            "foreign",
            "speaking in foreign language",
        }

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            LOGGER.warning("Whisper.cpp input capture failed: %s", error)
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if debug and transcript:
            print(f"Selected transcript from whisper.cpp backend: {transcript}")
        return transcript

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        return self.listen(timeout=timeout, debug=debug)

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

        if WhisperCppInputBackend._looks_like_repetition_hallucination(cleaned):
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


__all__ = ["WhisperCppInputBackend"]