from __future__ import annotations

from pydoc import text
import queue
from difflib import SequenceMatcher
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

import numpy as np
import sounddevice as sd

from SmartDeskAI_Assistant.modules.core import language
from modules.system.utils import BASE_DIR, append_log


class FasterWhisperVoiceInput:
    """
    Premium offline-first speech input backend for NeXa.

    Goals of this version:
    - keep the same public interface
    - reduce end-to-end latency
    - avoid expensive retries on clips that are obviously too short
    - transcribe directly from memory instead of writing temporary WAV files
    - stay robust for bilingual Polish / English usage
    - reject unsupported-language drift and recover with forced PL/EN passes
    """

    MODEL_SAMPLE_RATE = 16000
    SUPPORTED_LANGUAGES = {"pl", "en"}

    POLISH_HINT_WORDS = {
        "ktora", "jaka", "godzina", "godzine", "czas", "kim", "jestes", "jak", "sie",
        "nazywasz", "pokaz", "wyswietl", "powiedz", "wyjasnij", "wytlumacz", "zrob",
        "pomoz", "pomoc", "przypomnienie", "timer", "fokus", "focus", "przerwa",
        "wylacz", "zamknij", "asystenta", "system", "dziekuje", "nie", "tak",
    }

    ENGLISH_HINT_WORDS = {
        "what", "time", "who", "are", "you", "your", "name", "show", "tell",
        "explain", "help", "timer", "reminder", "focus", "break", "turn", "off",
        "close", "assistant", "system", "yes", "no",
    }

    SUSPICIOUS_ENGLISH_FALSE_POSITIVES = (
    "thank you very much",
    "they won t",
    "they wont",
    "kimi is",
    "the two matchminton",
    "matchminton",
    )

    WAKE_PHRASE_VARIANTS = (
        "nexa",
        "nexa?",
        "hey nexa",
        "okay nexa",
        "ok nexa",
        "nexta",
        "next up",
        "next app",
        "niksa",
        "niks a",
        "neksa",
        "necks a",
    )

    def __init__(
        self,
        model_size_or_path: str = "small",
        language: str = "auto",
        device_index: Optional[int] = None,
        device_name_contains: Optional[str] = None,
        sample_rate: Optional[int] = 16000,
        max_record_seconds: float = 10.0,
        end_silence_seconds: float = 0.75,
        pre_roll_seconds: float = 0.6,
        blocksize: int = 512,
        min_speech_seconds: float = 0.28,
        transcription_timeout_seconds: float = 45.0,
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 1,
        best_of: int = 1,
        vad_enabled: bool = True,
        vad_threshold: float = 0.5,
        vad_min_speech_ms: int = 250,
        vad_min_silence_ms: int = 500,
        vad_speech_pad_ms: int = 120,
    ) -> None:
        self.language = (language or "auto").strip().lower()

        self.max_record_seconds = max(float(max_record_seconds), 4.0)
        self.end_silence_seconds = max(float(end_silence_seconds), 0.35)
        self.pre_roll_seconds = max(float(pre_roll_seconds), 0.15)
        self.blocksize = int(blocksize)
        self.channels = 1
        self.dtype = "int16"
        self.min_speech_seconds = max(float(min_speech_seconds), 0.18)
        self.transcription_timeout_seconds = float(transcription_timeout_seconds)

        self.compute_type = str(compute_type).strip() or "int8"
        self.cpu_threads = max(int(cpu_threads), 1)
        self.beam_size = max(int(beam_size), 1)
        self.best_of = max(int(best_of), 1)

        self.vad_enabled = bool(vad_enabled)
        self.vad_threshold = float(vad_threshold)
        self.vad_min_speech_ms = int(vad_min_speech_ms)
        self.vad_min_silence_ms = int(vad_min_silence_ms)
        self.vad_speech_pad_ms = int(vad_speech_pad_ms)

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()

        self.device = self._resolve_input_device(device_index, device_name_contains)
        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.device_default_sample_rate = int(round(float(input_info.get("default_samplerate", 16000))))
        self.sample_rate = self._resolve_supported_sample_rate(sample_rate)
        self.model_size_or_path = self._resolve_model_reference(model_size_or_path)

        self._fw_model: Any | None = None
        self._silero_model: Any | None = None
        self._silero_get_speech_timestamps = None
        self._dependency_error: str | None = None

        # Latency-oriented guards
        self.min_transcription_seconds = max(0.45, self.min_speech_seconds)
        self.retry_min_seconds = max(0.80, self.min_transcription_seconds + 0.20)
        self.short_clip_rms_threshold = 0.018

                # Bilingual rescue guards
        self.language_rescue_probability_threshold = 0.88
        self.min_words_for_low_confidence_accept = 5

        # Standby wake-gate settings
        self.wake_sample_window_seconds = 1.8
        self.wake_end_silence_seconds = 0.35
        self.wake_min_speech_seconds = 0.10
        self.wake_phrase_similarity_threshold = 0.74

        append_log(
            "FasterWhisper input prepared: "
            f"device='{self.device_name}', sample_rate={self.sample_rate}, "
            f"language_mode={self.language}, vad={'on' if self.vad_enabled else 'off'}, "
            f"model_ref='{self.model_size_or_path}'"
        )

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    def _resolve_model_reference(self, model_size_or_path: str) -> str:
        raw = str(model_size_or_path or "").strip()
        if not raw:
            return "small"

        candidate = self._resolve_project_path(raw)
        if candidate.exists():
            return str(candidate)

        return raw

    def _resolve_input_device(
        self,
        device_index: Optional[int],
        device_name_contains: Optional[str],
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

    def _resolve_supported_sample_rate(self, preferred_sample_rate: Optional[int]) -> int:
        candidates: list[int] = []

        if preferred_sample_rate:
            candidates.append(int(preferred_sample_rate))

        candidates.extend(
            [
                self.device_default_sample_rate,
                16000,
                32000,
                44100,
                48000,
            ]
        )

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
            f"No supported sample rate found for input device '{self.device_name}'. "
            f"Tried: {unique_candidates}"
        )

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            append_log(f"FasterWhisper audio callback status: {status}")

        try:
            if indata.ndim == 2:
                mono = indata[:, 0].copy()
            else:
                mono = indata.copy()
            self.audio_queue.put_nowait(mono)
        except Exception as error:
            append_log(f"FasterWhisper audio callback error: {error}")

    def _ensure_dependencies(self) -> None:
        if self._dependency_error:
            raise RuntimeError(self._dependency_error)

        if self._fw_model is None:
            try:
                from faster_whisper import WhisperModel
            except Exception as error:
                self._dependency_error = (
                    "Missing faster-whisper dependency. "
                    "Install it before switching the voice_input engine."
                )
                raise RuntimeError(self._dependency_error) from error

            self._fw_model = WhisperModel(
                self.model_size_or_path,
                device="cpu",
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                num_workers=1,
            )
            append_log(
                "FasterWhisper model loaded successfully: "
                f"model_ref='{self.model_size_or_path}', compute_type='{self.compute_type}', "
                f"threads={self.cpu_threads}"
            )

        if self.vad_enabled and self._silero_model is None:
            try:
                from silero_vad import get_speech_timestamps, load_silero_vad
            except Exception as error:
                self._dependency_error = (
                    "Missing silero-vad dependency. "
                    "Install silero-vad and onnxruntime before switching the voice_input engine."
                )
                raise RuntimeError(self._dependency_error) from error

            self._silero_model = load_silero_vad(onnx=True)
            self._silero_get_speech_timestamps = get_speech_timestamps
            append_log("Silero VAD loaded successfully for FasterWhisper input.")

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
        max_record_seconds: float | None = None,
        end_silence_seconds: float | None = None,
        min_speech_seconds: float | None = None,
    ) -> Optional[np.ndarray]:
        self._ensure_dependencies()
        self._clear_audio_queue()

        effective_max_record_seconds = max(float(max_record_seconds or self.max_record_seconds), 0.8)
        effective_end_silence_seconds = max(float(end_silence_seconds or self.end_silence_seconds), 0.15)
        effective_min_speech_seconds = max(float(min_speech_seconds or self.min_speech_seconds), 0.05)

        hard_timeout = max(float(timeout), effective_max_record_seconds)
        start_time = self._now()

        pre_roll_max_chunks = max(1, int(round(self.pre_roll_seconds * self.sample_rate / self.blocksize)))
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
                try:
                    chunk = self.audio_queue.get(timeout=0.15)
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
                            print("Speech onset detected by FasterWhisper frontend.")
                        continue

                if speech_started:
                    recorded_chunks.append(chunk_f32)

                    trailing_window = self._concat_audio(recorded_chunks[-max(1, pre_roll_max_chunks * 3):])
                    trailing_has_speech = self._window_contains_speech(trailing_window)

                    if chunk_has_speech or trailing_has_speech:
                        last_speech_at = self._now()

                    enough_speech = False
                    if speech_started_at is not None:
                        enough_speech = (self._now() - speech_started_at) >= effective_min_speech_seconds

                    if enough_speech and last_speech_at is not None:
                        if (self._now() - last_speech_at) >= effective_end_silence_seconds:
                            break

        if not speech_started or not recorded_chunks:
            return None

        audio = self._concat_audio(recorded_chunks)
        duration = len(audio) / float(self.sample_rate)

        if duration < effective_min_speech_seconds:
            if debug:
                print("Recorded utterance too short, dropping.")
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        trimmed_duration = len(trimmed_audio) / float(self.sample_rate) if trimmed_audio.size else 0.0

        if debug:
            print(
                f"Recorded audio duration: {duration:.2f}s | "
                f"trimmed duration: {trimmed_duration:.2f}s"
            )

        if trimmed_audio.size >= int(self.sample_rate * effective_min_speech_seconds):
            return trimmed_audio

        return audio

    def _window_contains_speech(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return False

        # First try Silero VAD when enabled
        if self.vad_enabled:
            if self._silero_window_contains_speech(audio):
                return True

    # Fallback to simple energy detection for speech onset.
    # This is important on real microphone setups where Silero
    # can miss the very beginning of short commands.
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
            append_log(f"Silero VAD inference warning: {error}")
            return False

    @staticmethod
    def _energy_window_contains_speech(audio: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        return rms >= 0.008

    def _transcribe_audio(self, audio: np.ndarray, debug: bool = False) -> Optional[str]:
        if audio.size == 0:
            return None

        self._ensure_dependencies()
        if self._fw_model is None:
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

        accepted_primary = self._accept_candidate(primary_candidate)
        if accepted_primary:
            if debug and primary_candidate["text"]:
                print(f"Accepted primary transcript: {primary_candidate['text']}")
            return primary_candidate["text"]

        rescue_candidate = self._rescue_bilingual_candidate(
            prepared_primary,
            primary_candidate=primary_candidate,
            debug=debug,
        )
        if rescue_candidate is not None:
            if debug:
                print(
                    f"Selected bilingual rescue transcript: {rescue_candidate['text']} "
                    f"| lang={rescue_candidate['language']}"
                )
            return rescue_candidate["text"]

        primary_duration = len(prepared_primary) / float(self.MODEL_SAMPLE_RATE)
        if primary_duration < self.retry_min_seconds:
            if debug:
                print("Skipping retry: primary clip too short for useful second pass.")
            return None

        retry_audio = self._extract_voiced_audio_for_retry(audio)
        if retry_audio is None or retry_audio.size == 0:
            return None

        prepared_retry = self._prepare_audio_for_model(retry_audio)
        if prepared_retry is None:
            return None

        retry_duration = len(prepared_retry) / float(self.MODEL_SAMPLE_RATE)
        if retry_duration < self.retry_min_seconds:
            if debug:
                print("Skipping retry: voiced-only retry clip still too short.")
            return None

        if debug:
            print(f"Retrying transcription with voiced-only audio: {retry_duration:.2f}s")

        retry_candidate = self._transcribe_single_audio(
            prepared_retry,
            debug=debug,
            label="retry",
            forced_language=None,
        )
        if self._accept_candidate(retry_candidate):
            return retry_candidate["text"]

        retry_rescue_candidate = self._rescue_bilingual_candidate(
            prepared_retry,
            primary_candidate=retry_candidate,
            debug=debug,
        )
        
        if retry_rescue_candidate is not None:
            return retry_rescue_candidate["text"]

        return None

    def _prepare_audio_for_model(self, audio: np.ndarray) -> Optional[np.ndarray]:
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

        if duration < self.min_transcription_seconds:
            return None

        return resampled.astype(np.float32, copy=False)

    def _transcribe_single_audio(
        self,
        audio: np.ndarray,
        *,
        debug: bool = False,
        label: str = "primary",
        forced_language: str | None = None,
    ) -> dict[str, Any]:
        candidate = {
            "text": None,
            "language": forced_language,
            "language_probability": 0.0,
            "elapsed": 0.0,
            "forced_language": forced_language,
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
                    "language": detected_language,
                    "language_probability": float(language_probability),
                    "elapsed": elapsed,
                }
            )

            if debug:
                printable = transcript if transcript else "<empty>"
                mode_label = label if forced_language is None else f"{label}:{forced_language}"
                print(
                    f"FasterWhisper {mode_label} transcript: {printable} | "
                    f"lang={detected_language} prob={language_probability} elapsed={elapsed:.2f}s"
                )

            return candidate

        except Exception as error:
            append_log(f"FasterWhisper transcription error ({label}): {error}")
            return candidate

    
    def _rescue_bilingual_candidate(
        self,
        audio: np.ndarray,
        *,
        primary_candidate: dict[str, Any] | None = None,
        debug: bool = False,
    )  -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []

        primary_language = str((primary_candidate or {}).get("language") or "").strip().lower()
        if primary_language not in self.SUPPORTED_LANGUAGES:
            primary_language = ""

        for forced_language in ("pl", "en"):
            candidate = self._transcribe_single_audio(
                audio,
                debug=debug,
                label="rescue",
                forced_language=forced_language,
            )
            if candidate["text"]:
                candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(
            key=lambda candidate: self._candidate_score(
                candidate,
                primary_language=primary_language or None,
            ),
            reverse=True,
        )
        best = candidates[0]

        if self._candidate_score(best, primary_language=primary_language or None) <= 0.0:
            return None

        return best

    def _accept_candidate(self, candidate: dict[str, Any]) -> bool:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()
        probability = float(candidate.get("language_probability") or 0.0)

        if not text:
            return False

        if language not in self.SUPPORTED_LANGUAGES:
            return False

        if self._contains_unsupported_script(text):
            return False

        word_count = len(text.split())
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
            "shut down",
        }

        english_commands = {
            "what time is it",
            "what day is it",
            "what month is it",
            "what year is it",
            "who are you",
            "what is your name",
            "show it",
            "show that",
            "close assistant",
            "shutdown system",
        }

        polish_commands = {
            "ktora godzina",
            "jaki dzien",
            "jaki miesiac",
            "jaki rok",
            "kim jestes",
            "jak masz na imie",
            "pokaz to",
            "zamknij asystenta",
            "wylacz system",
        }

        bonus = 0.0

        if normalized in shared_commands:
            bonus += 1.9

        if language == "en" and normalized in english_commands:
            bonus += 2.1

        if language == "pl" and normalized in polish_commands:
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
            "jaka ",
            "kim ",
            "jak ",
            "czy ",
            "pokaz ",
            "wyswietl ",
            "wytlumacz ",
            "wyjasnij ",
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

        if language == "pl":
            if normalized in {"tak", "nie"}:
                penalty += 0.4

        return penalty

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

        if cleaned in {
            "[blank_audio]",
            "[noise]",
            "blank audio",
            "noise",
        }:
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

    def _trim_with_silero(self, audio: np.ndarray) -> Optional[np.ndarray]:
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
            append_log(f"Silero trim warning: {error}")
            return None

        if not timestamps:
            return None

        start = timestamps[0]["start"]
        end = timestamps[-1]["end"]

        src_start = int(start * self.sample_rate / self.MODEL_SAMPLE_RATE)
        src_end = int(end * self.sample_rate / self.MODEL_SAMPLE_RATE)

        src_start = max(0, src_start)
        src_end = min(len(audio), max(src_end, src_start + 1))

        if src_end <= src_start:
            return None

        return audio[src_start:src_end].astype(np.float32, copy=False)

    def _trim_with_energy(self, audio: np.ndarray) -> np.ndarray:
        if audio.size == 0:
            return audio

        abs_audio = np.abs(audio)
        threshold = max(0.010, float(np.max(abs_audio) * 0.18))

        mask = abs_audio >= threshold
        indices = np.flatnonzero(mask)

        if indices.size == 0:
            return audio

        pad = int(self.sample_rate * 0.15)
        start = max(0, int(indices[0]) - pad)
        end = min(len(audio), int(indices[-1]) + pad)

        if end <= start:
            return audio

        return audio[start:end].astype(np.float32, copy=False)

    def _extract_voiced_audio_for_retry(self, audio: np.ndarray) -> Optional[np.ndarray]:
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
                append_log(f"Silero retry extraction warning: {error}")
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
    @classmethod
    def _normalize_wake_text(cls, text: str) -> str:
        cleaned = str(text or "").strip().lower()
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def _wake_similarity(cls, left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio()

    @classmethod
    def _looks_like_wake_phrase(cls, text: str, similarity_threshold: float = 0.74) -> bool:
        normalized = cls._normalize_wake_text(text)
        if not normalized:
            return False

        if len(normalized.split()) > 3:
            return False

        if normalized in cls.WAKE_PHRASE_VARIANTS:
            return True

        tokens = normalized.split()
        if not tokens:
            return False

        for variant in cls.WAKE_PHRASE_VARIANTS:
            if normalized == variant:
                return True

            if normalized in variant or variant in normalized:
                return True

            if cls._wake_similarity(normalized, variant) >= similarity_threshold:
                return True

        joined = "".join(tokens)
        for variant in cls.WAKE_PHRASE_VARIANTS:
            variant_joined = variant.replace(" ", "")
            if joined == variant_joined:
                return True
            if cls._wake_similarity(joined, variant_joined) >= similarity_threshold:
                return True

        return False

    def listen_for_wake_phrase(self, timeout: float = 2.4, debug: bool = False) -> Optional[str]:
        try:
            audio = self._record_until_silence(
                timeout=timeout,
                debug=debug,
                max_record_seconds=self.wake_sample_window_seconds,
                end_silence_seconds=self.wake_end_silence_seconds,
                min_speech_seconds=self.wake_min_speech_seconds,
            )
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            append_log(f"Wake gate audio capture failed: {error}")
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if not transcript:
            return None

        if not self._looks_like_wake_phrase(
            transcript,
            similarity_threshold=self.wake_phrase_similarity_threshold,
        ):
            return None

        if debug:
            print(f"Wake gate accepted transcript: {transcript}")

        return "nexa"
    
    def listen(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        try:
            audio = self._record_until_silence(timeout=timeout, debug=debug)
            if audio is None or audio.size == 0:
                return None
        except Exception as error:
            append_log(f"FasterWhisper audio capture failed: {error}")
            return None

        transcript = self._transcribe_audio(audio, debug=debug)
        if debug and transcript:
            print(f"Selected transcript from faster-whisper: {transcript}")
        return transcript

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        return self.listen(timeout=timeout, debug=debug)

    def close(self) -> None:
        self._clear_audio_queue()

    @staticmethod
    def list_audio_devices() -> None:
        print(sd.query_devices())

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
    def _cleanup_transcript(text: str | None) -> Optional[str]:
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

        # Reject obvious repetition loops
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

        return cleaned

    @staticmethod
    def _resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if audio.size == 0:
            return np.array([], dtype=np.float32)

        if src_rate == dst_rate:
            return audio.astype(np.float32, copy=False)

        duration = len(audio) / float(src_rate)
        if duration <= 0:
            return np.array([], dtype=np.float32)

        src_positions = np.linspace(0.0, duration, num=len(audio), endpoint=False, dtype=np.float64)
        dst_length = max(1, int(round(duration * dst_rate)))
        dst_positions = np.linspace(0.0, duration, num=dst_length, endpoint=False, dtype=np.float64)

        resampled = np.interp(dst_positions, src_positions, audio).astype(np.float32)
        return resampled