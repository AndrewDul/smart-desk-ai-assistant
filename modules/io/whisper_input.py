from __future__ import annotations

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
from typing import Optional

import numpy as np
import sounddevice as sd

from modules.system.utils import BASE_DIR, append_log


class WhisperVoiceInput:
    def __init__(
        self,
        whisper_cli_path: str,
        model_path: str,
        vad_enabled: bool = True,
        vad_model_path: Optional[str] = None,
        language: str = "auto",
        device_index: Optional[int] = None,
        device_name_contains: Optional[str] = None,
        sample_rate: Optional[int] = None,
        max_record_seconds: float = 8.0,
        silence_threshold: float = 350.0,
        end_silence_seconds: float = 1.0,
        pre_roll_seconds: float = 0.4,
        threads: int = 4,
        min_speech_seconds: float = 0.20,
        transcription_timeout_seconds: float = 45.0,
    ) -> None:
        resolved_cli = self._resolve_whisper_cli_path(whisper_cli_path)
        self.whisper_cli_path = str(resolved_cli)
        self.model_path = str(self._resolve_project_path(model_path))
        self.vad_enabled = bool(vad_enabled)
        self.vad_model_path = str(self._resolve_project_path(vad_model_path)) if vad_model_path else None
        self.language = (language or "auto").strip().lower()

        self.max_record_seconds = max(float(max_record_seconds), 10.0)
        self.silence_threshold = float(silence_threshold)
        self.end_silence_seconds = max(float(end_silence_seconds), 0.65)
        self.pre_roll_seconds = max(float(pre_roll_seconds), 0.5)
        self.threads = int(threads)
        self.min_speech_seconds = max(float(min_speech_seconds), 0.28)
        self.transcription_timeout_seconds = float(transcription_timeout_seconds)

        self.blocksize = 512
        self.channels = 1
        self.dtype = "int16"
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self._tail_keep_chunks = 3

        self._speech_window_seconds = 0.42
        self._speech_like_chunk_requirement = 4
        self._speech_like_duration_requirement = 0.18
        self._speech_start_reset_seconds = 0.85

        self.device = self._resolve_input_device(device_index, device_name_contains)
        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.device_default_sample_rate = int(round(float(input_info.get("default_samplerate", 16000))))
        self.sample_rate = self._resolve_supported_sample_rate(sample_rate)

        cli_path = Path(self.whisper_cli_path)
        model_file = Path(self.model_path)

        if not cli_path.exists():
            raise FileNotFoundError(f"whisper-cli not found at: {cli_path}")

        if not model_file.exists():
            raise FileNotFoundError(f"Whisper model not found at: {model_file}")

        if self.vad_enabled and self.vad_model_path and not Path(self.vad_model_path).exists():
            raise FileNotFoundError(f"VAD model not found at: {self.vad_model_path}")

        self._session_temp_dir = Path(tempfile.mkdtemp(prefix="smartdesk_whisper_"))
        self._wav_path = self._session_temp_dir / "utterance.wav"
        self._output_prefix_base = self._session_temp_dir / "utterance"

        self._whisper_base_cmd_common = [
            self.whisper_cli_path,
            "--model",
            self.model_path,
            "--threads",
            str(self.threads),
            "--output-txt",
            "--no-timestamps",
            "--no-prints",
        ]

        if self.vad_enabled and self.vad_model_path:
            self._whisper_base_cmd_common.extend(["--vad", "--vad-model", self.vad_model_path])

        self._lang_keywords = {
            "en": {
                "help",
                "menu",
                "time",
                "date",
                "day",
                "year",
                "timer",
                "focus",
                "break",
                "status",
                "memory",
                "reminder",
                "reminders",
                "show",
                "display",
                "assistant",
                "what",
                "where",
                "remember",
                "remind",
                "stop",
                "exit",
                "shutdown",
                "yes",
                "no",
                "name",
                "who",
                "how",
                "sleep",
                "rest",
                "turn",
                "off",
                "hour",
                "keys",
                "kitchen",
                "eat",
            },
            "pl": {
                "pomoc",
                "menu",
                "godzina",
                "czas",
                "data",
                "dzien",
                "dzień",
                "rok",
                "timer",
                "focus",
                "przerwa",
                "stan",
                "status",
                "pamiec",
                "pamięć",
                "przypomnienie",
                "przypomnienia",
                "pokaz",
                "pokaż",
                "wyswietl",
                "wyświetl",
                "asystent",
                "asystenta",
                "ktora",
                "która",
                "jaka",
                "co",
                "gdzie",
                "zapamietaj",
                "zapamiętaj",
                "przypomnij",
                "stop",
                "wyjdz",
                "wyjdź",
                "wylacz",
                "wyłącz",
                "tak",
                "nie",
                "imie",
                "imię",
                "potrafisz",
                "jak",
                "mozesz",
                "możesz",
                "spac",
                "spać",
                "odpocznij",
                "idz",
                "idź",
                "jest",
                "jestes",
                "jestes",
                "kim",
                "czym",
                "nazywasz",
                "klucze",
                "kuchni",
                "zjesc",
                "zjeść",
                "pamieci",
                "pamięci",
                "pomoc",
            },
        }

        self._exact_command_phrases = {
            "en": {
                "what time is it",
                "show time",
                "show me the time",
                "show date",
                "show me the date",
                "show day",
                "show me the day",
                "show year",
                "show me the year",
                "help",
                "menu",
                "status",
                "what can you do",
                "how can you help me",
                "what is your name",
                "whats your name",
                "who are you",
                "what are you",
                "go to sleep",
                "turn off assistant",
                "where are the keys",
                "remember that the keys are in the kitchen",
            },
            "pl": {
                "ktora jest godzina",
                "ktora godzina",
                "jaka jest godzina",
                "pokaz godzine",
                "pokaz mi godzine",
                "pokaz date",
                "pokaz mi date",
                "pokaz dzien",
                "pokaz mi dzien",
                "pokaz rok",
                "pokaz mi rok",
                "jaka jest data",
                "jaki jest dzisiaj dzien",
                "jaki mamy dzisiaj dzien",
                "jaki mamy rok",
                "pomoc",
                "menu",
                "co potrafisz",
                "jak mozesz mi pomoc",
                "w czym mozesz mi pomoc",
                "status",
                "jak sie nazywasz",
                "kim jestes",
                "czym jestes",
                "idz spac",
                "wylacz asystenta",
                "odpocznij",
                "gdzie sa klucze",
                "zapamietaj ze klucze sa w kuchni",
                "usun klucze z pamieci",
            },
        }

        self._strong_confirmation_tokens = {
            "en": {"yes", "yeah", "yep", "no", "nope"},
            "pl": {"tak", "nie", "jasne", "pewnie", "anuluj"},
        }

        self._fuzzy_confirmation_tokens = {
            "en": {"ye", "yeh", "ya"},
            "pl": {"tag", "tac", "tek", "tok", "ni", "ne", "nje", "nee"},
        }

        self._ambiguous_short_tokens = {
            "no",
            "yeah",
            "yep",
            "yes",
            "tak",
            "nie",
            "tag",
            "tac",
            "tek",
            "tok",
            "ni",
            "ne",
            "nje",
            "nee",
            "ye",
            "yeh",
            "ya",
        }

        self._suspicious_auto_phrases = {
            "which is an hour",
            "which is hour",
            "which hour",
            "which is the hour",
            "which is a hour",
        }

        append_log(
            f"Whisper input ready: device='{self.device_name}', sample_rate={self.sample_rate}, "
            f"language_mode={self.language}, vad={'on' if self.vad_enabled else 'off'}"
        )

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    def _resolve_whisper_cli_path(self, whisper_cli_path: str) -> Path:
        direct_path = self._resolve_project_path(whisper_cli_path)
        if direct_path.exists():
            return direct_path

        cli_name = Path(whisper_cli_path).name
        discovered = shutil.which(cli_name) or shutil.which("whisper-cli")
        if discovered:
            return Path(discovered)

        return direct_path

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
                48000,
                44100,
                32000,
                16000,
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
            append_log(f"Audio callback status: {status}")
        self.audio_queue.put(bytes(indata))

    def _required_end_silence(self, elapsed_speech: float) -> float:
        if elapsed_speech < 0.9:
            return max(self.end_silence_seconds, 0.95)
        if elapsed_speech < 2.0:
            return max(self.end_silence_seconds, 0.82)
        if elapsed_speech < 4.0:
            return max(self.end_silence_seconds, 0.72)
        return max(self.end_silence_seconds, 0.65)

    def _trim_trailing_silence(self, recorded_chunks: list[bytes], trailing_silence_chunks: int) -> list[bytes]:
        if trailing_silence_chunks <= 0:
            return recorded_chunks

        keep_back = min(trailing_silence_chunks, self._tail_keep_chunks)
        drop_count = max(trailing_silence_chunks - keep_back, 0)

        if drop_count <= 0:
            return recorded_chunks

        if drop_count >= len(recorded_chunks):
            return recorded_chunks

        return recorded_chunks[:-drop_count]

    def _adaptive_start_threshold(self, ambient_rms: list[float]) -> float:
        if not ambient_rms:
            return self.silence_threshold

        median_noise = float(np.median(ambient_rms))
        mean_noise = float(np.mean(ambient_rms))

        adaptive = max(
            self.silence_threshold,
            median_noise * 2.8,
            mean_noise * 2.4,
            median_noise + 30.0,
        )
        return adaptive

    def _analyze_chunk(self, chunk: bytes) -> dict[str, float]:
        audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if audio.size == 0:
            return {
                "rms": 0.0,
                "peak": 0.0,
                "zcr": 0.0,
                "speech_band_ratio": 0.0,
                "spectral_centroid": 0.0,
                "duration": 0.0,
            }

        duration = float(audio.size) / float(self.sample_rate)
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0

        centered = audio - float(np.mean(audio))
        if centered.size >= 2:
            zero_crossings = np.count_nonzero(np.diff(np.signbit(centered)))
            zcr = float(zero_crossings) / float(centered.size - 1)
        else:
            zcr = 0.0

        window = np.hanning(centered.size) if centered.size > 1 else np.ones_like(centered)
        windowed = centered * window
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(centered.size, d=1.0 / float(self.sample_rate)) if centered.size else np.array([0.0])

        total_energy = float(np.sum(spectrum)) + 1e-9
        speech_mask = (freqs >= 85.0) & (freqs <= 4000.0)
        speech_energy = float(np.sum(spectrum[speech_mask]))
        speech_band_ratio = speech_energy / total_energy

        if float(np.sum(spectrum)) > 0.0:
            spectral_centroid = float(np.sum(freqs * spectrum) / total_energy)
        else:
            spectral_centroid = 0.0

        return {
            "rms": rms,
            "peak": peak,
            "zcr": zcr,
            "speech_band_ratio": speech_band_ratio,
            "spectral_centroid": spectral_centroid,
            "duration": duration,
        }

    def _is_speech_like_chunk(self, metrics: dict[str, float], start_threshold: float) -> bool:
        rms = metrics["rms"]
        peak = metrics["peak"]
        zcr = metrics["zcr"]
        speech_band_ratio = metrics["speech_band_ratio"]
        spectral_centroid = metrics["spectral_centroid"]

        if rms < start_threshold:
            return False

        transient_ratio = peak / max(rms, 1.0)
        if transient_ratio >= 11.5 and speech_band_ratio < 0.76:
            return False

        if speech_band_ratio < 0.52:
            return False

        if zcr < 0.015 or zcr > 0.24:
            return False

        if spectral_centroid < 110.0 or spectral_centroid > 3600.0:
            return False

        return True

    def _record_until_silence(self, timeout: float, debug: bool = False) -> bytes | None:
        self.audio_queue = queue.Queue()

        pre_roll_block_count = max(1, int((self.pre_roll_seconds * self.sample_rate) / self.blocksize))
        pre_roll = deque(maxlen=pre_roll_block_count)
        recorded_chunks: list[bytes] = []

        speech_started = False
        speech_start_time: float | None = None
        silence_started_at: float | None = None
        trailing_silence_chunks = 0
        listen_started_at = self._now()

        ambient_rms: list[float] = []
        speech_gate_window: deque[tuple[float, bool]] = deque()
        last_speech_like_at: float | None = None

        try:
            stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                device=self.device,
                dtype=self.dtype,
                channels=self.channels,
                callback=self._audio_callback,
            )
        except Exception as error:
            append_log(f"Audio input stream creation failed: {error}")
            return None

        with stream:
            while True:
                try:
                    chunk = self.audio_queue.get(timeout=0.04)
                except queue.Empty:
                    now = self._now()

                    if not speech_started and (now - listen_started_at) >= timeout:
                        if debug:
                            print("No speech detected before timeout.")
                        return None

                    if speech_started and speech_start_time is not None:
                        if (now - speech_start_time) >= self.max_record_seconds:
                            if debug:
                                print("Max record duration reached during queue wait.")
                            break
                    continue

                metrics = self._analyze_chunk(chunk)
                rms = metrics["rms"]
                now = self._now()

                if not speech_started:
                    pre_roll.append(chunk)

                    if len(ambient_rms) < 30:
                        ambient_rms.append(rms)

                    start_threshold = self._adaptive_start_threshold(ambient_rms)
                    speech_like = self._is_speech_like_chunk(metrics, start_threshold)
                    speech_gate_window.append((now, speech_like))

                    while speech_gate_window and (now - speech_gate_window[0][0]) > self._speech_window_seconds:
                        speech_gate_window.popleft()

                    speech_like_count = sum(1 for _, flag in speech_gate_window if flag)
                    speech_like_duration = sum(metrics["duration"] for _, flag in speech_gate_window if flag)

                    if speech_like:
                        last_speech_like_at = now
                    elif last_speech_like_at is not None and (now - last_speech_like_at) > self._speech_start_reset_seconds:
                        speech_gate_window.clear()
                        last_speech_like_at = None

                    if debug:
                        print(
                            f"RMS: {rms:.2f} | start_threshold: {start_threshold:.2f} | "
                            f"speech_like={speech_like} | gate_count={speech_like_count}"
                        )

                    if (
                        speech_like_count >= self._speech_like_chunk_requirement
                        or speech_like_duration >= self._speech_like_duration_requirement
                    ):
                        speech_started = True
                        speech_start_time = now
                        recorded_chunks.extend(pre_roll)
                        recorded_chunks.append(chunk)
                        silence_started_at = None
                        trailing_silence_chunks = 0
                        if debug:
                            print("Speech started.")
                    else:
                        if (now - listen_started_at) >= timeout:
                            if debug:
                                print("Timeout reached without speech.")
                            return None
                    continue

                recorded_chunks.append(chunk)

                assert speech_start_time is not None

                elapsed_speech = now - speech_start_time
                required_end_silence = self._required_end_silence(elapsed_speech)
                start_threshold = self._adaptive_start_threshold(ambient_rms)
                end_threshold = max(self.silence_threshold, start_threshold * 0.46)

                if debug:
                    print(f"RMS: {rms:.2f} | end_threshold: {end_threshold:.2f}")

                if rms < end_threshold:
                    trailing_silence_chunks += 1

                    if elapsed_speech >= self.min_speech_seconds:
                        if silence_started_at is None:
                            silence_started_at = now
                        elif (now - silence_started_at) >= required_end_silence:
                            if debug:
                                print(
                                    "Detected end-of-speech silence "
                                    f"(elapsed={elapsed_speech:.2f}s, required={required_end_silence:.2f}s)."
                                )
                            break
                else:
                    silence_started_at = None
                    trailing_silence_chunks = 0

                if elapsed_speech >= self.max_record_seconds:
                    if debug:
                        print("Max record duration reached.")
                    break

        if not recorded_chunks:
            return None

        trimmed_chunks = self._trim_trailing_silence(recorded_chunks, trailing_silence_chunks)
        combined = b"".join(trimmed_chunks)
        if not combined:
            return None

        return combined

    def _transcript_prefix(self, label: str) -> Path:
        return self._output_prefix_base.with_name(f"{self._output_prefix_base.name}_{label}")

    def _clear_previous_output_files(self) -> None:
        try:
            if self._wav_path.exists():
                self._wav_path.unlink()
        except OSError:
            pass

        for label in {"auto", "pl"}:
            prefix = self._transcript_prefix(label)
            for path in [
                prefix.with_suffix(".txt"),
                prefix.with_suffix(".srt"),
                prefix.with_suffix(".vtt"),
                prefix.with_suffix(".json"),
                prefix.with_suffix(".lrc"),
            ]:
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass

    def _clear_previous_transcript_files(self, label: str) -> None:
        prefix = self._transcript_prefix(label)
        for path in [
            prefix.with_suffix(".txt"),
            prefix.with_suffix(".srt"),
            prefix.with_suffix(".vtt"),
            prefix.with_suffix(".json"),
            prefix.with_suffix(".lrc"),
        ]:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    def _write_wav(self, pcm_bytes: bytes) -> Path:
        self._clear_previous_output_files()

        with wave.open(str(self._wav_path), "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_bytes)

        return self._wav_path

    def _build_whisper_command(self, wav_path: Path, label: str) -> list[str]:
        prefix = self._transcript_prefix(label)
        cmd = [
            *self._whisper_base_cmd_common,
            "--output-file",
            str(prefix),
            "--file",
            str(wav_path),
        ]

        if label != "auto":
            cmd.extend(["--language", label])

        return cmd

    def _transcribe(self, wav_path: Path, label: str, debug: bool = False) -> str:
        self._clear_previous_transcript_files(label)
        cmd = self._build_whisper_command(wav_path, label)

        if debug:
            print(f"Using input device: {self.device_name}")
            print(f"Using sample rate: {self.sample_rate}")
            print(f"Whisper command ({label}):")
            print(" ".join(cmd))

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
                    f"Whisper transcription failed for language '{label}'.\n"
                    f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
                )
            raise RuntimeError(f"Whisper transcription failed for language '{label}'.")

        transcript_path = self._transcript_prefix(label).with_suffix(".txt")
        if not transcript_path.exists():
            return ""

        return transcript_path.read_text(encoding="utf-8").strip()

    def _normalize_text(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-zA-ZÀ-ÿ0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered.strip()

    def _normalized_word_tokens(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        return [token for token in normalized.split() if token]

    def _cleanup_transcript(self, transcript: str, debug: bool = False) -> str | None:
        if not transcript:
            return None

        cleaned = transcript.strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return None

        normalized = self._normalize_text(cleaned)

        bad_markers = {
            "",
            "blank audio",
            "blank_audio",
            "silence",
            "no speech",
            "no speech recognized",
            "noise",
            "thank you",
            "thanks for watching",
            "you",
            "applause",
            "keyboard",
            "typing",
            "knocking",
            "chair",
            "stukanie",
            "klaskanie",
            "krzeslo",
        }

        if normalized in bad_markers:
            if debug:
                print(f"Ignored blank marker transcript: {cleaned}")
            return None

        alpha_only = re.sub(r"[^a-zA-ZÀ-ÿ]", "", cleaned)
        if len(alpha_only) <= 1:
            return None

        return cleaned

    def _score_transcript(self, transcript: str | None, lang: str) -> float:
        if not transcript:
            return -999.0

        normalized = self._normalize_text(transcript)
        if not normalized:
            return -999.0

        if lang == "auto":
            score = max(
                self._score_transcript(transcript, "en"),
                self._score_transcript(transcript, "pl"),
            ) + 0.25
            if normalized in self._suspicious_auto_phrases:
                score -= 1.6
            return score

        tokens = set(self._normalized_word_tokens(transcript))
        score = 0.0

        non_speech_tokens = {
            "music",
            "muzyka",
            "upbeat",
            "pogodna",
            "applause",
            "oklaski",
            "laughter",
            "smiech",
            "noise",
            "szum",
            "silence",
            "cisza",
            "ambient",
            "background",
            "static",
            "instrumental",
            "keyboard",
            "typing",
            "knocking",
            "chair",
            "stukanie",
            "klaskanie",
            "krzeslo",
        }

        filler_tokens = {
            "yeah",
            "yep",
            "okay",
            "ok",
            "hmm",
            "hm",
            "mmm",
            "uh",
            "um",
        }

        if len(normalized) >= 2:
            score += 0.4
        if len(tokens) >= 2:
            score += 0.6

        if normalized in self._exact_command_phrases[lang]:
            score += 6.5

        keyword_hits = len(tokens & self._lang_keywords[lang])
        score += min(keyword_hits * 1.8, 7.0)

        if normalized in self._strong_confirmation_tokens[lang]:
            score += 3.0

        if normalized in self._fuzzy_confirmation_tokens[lang]:
            score += 2.0

        other_lang = "pl" if lang == "en" else "en"
        if normalized in self._strong_confirmation_tokens[other_lang]:
            score -= 0.8

        noise_hits = len(tokens & non_speech_tokens)
        filler_hits = len(tokens & filler_tokens)

        if noise_hits:
            score -= noise_hits * 2.4

        if len(tokens) <= 4 and noise_hits >= 1 and not (tokens & self._lang_keywords[lang]):
            score -= 2.5

        if len(tokens) <= 4 and noise_hits >= 2 and (noise_hits + filler_hits) >= len(tokens):
            score -= 5.0

        if len(tokens) == 1 and normalized in self._ambiguous_short_tokens:
            score += 0.2

        if lang == "pl":
            strong_token_sets = [
                {"jak", "mozesz", "mi", "pomoc"},
                {"w", "czym", "mozesz", "mi", "pomoc"},
                {"jak", "sie", "nazywasz"},
                {"kim", "jestes"},
                {"czym", "jestes"},
                {"jaki", "jest", "dzisiaj", "dzien"},
                {"jaki", "mamy", "rok"},
                {"pokaz", "mi", "godzine"},
                {"gdzie", "sa", "klucze"},
                {"usun", "klucze", "z", "pamieci"},
            ]
            for token_set in strong_token_sets:
                if token_set.issubset(tokens):
                    score += 4.0

        return score

    def _should_try_forced_languages(self, auto_transcript: str | None) -> bool:
        if auto_transcript is None:
            return True

        normalized = self._normalize_text(auto_transcript)
        tokens = set(self._normalized_word_tokens(auto_transcript))
        auto_score = self._score_transcript(auto_transcript, "auto")
        auto_en_score = self._score_transcript(auto_transcript, "en")
        auto_pl_score = self._score_transcript(auto_transcript, "pl")

        if self._normalize_text(auto_transcript) in self._exact_command_phrases["pl"]:
            return True

        if self._is_confirmation_candidate(normalized):
            return False

        if self._is_exact_phrase(normalized, "en") or self._is_exact_phrase(normalized, "pl"):
            if len(tokens) <= 6:
                return True
            return False

        if normalized in self._suspicious_auto_phrases:
            return True

        if len(tokens) <= 7:
            return True

        if auto_en_score >= 3.6 and auto_en_score >= auto_pl_score + 1.0 and len(tokens) >= 3:
            return False

        if auto_pl_score >= 3.6 and auto_pl_score >= auto_en_score + 0.6 and len(tokens) >= 3:
            return True

        if len(tokens) <= 1 and normalized in self._ambiguous_short_tokens:
            return True

        if len(tokens) <= 5 and auto_score < 3.2:
            return True

        if auto_pl_score >= auto_en_score and len(tokens) <= 8:
            return True

        return False

    def _is_exact_phrase(self, normalized: str, lang: str) -> bool:
        return normalized in self._exact_command_phrases[lang]

    def _is_confirmation_candidate(self, normalized: str) -> bool:
        return (
            normalized in self._strong_confirmation_tokens["en"]
            or normalized in self._strong_confirmation_tokens["pl"]
            or normalized in self._fuzzy_confirmation_tokens["en"]
            or normalized in self._fuzzy_confirmation_tokens["pl"]
        )

    def _select_best_transcript(self, wav_path: Path, debug: bool = False) -> str | None:
        auto_raw = self._transcribe(wav_path, "auto", debug=debug)
        auto_clean = self._cleanup_transcript(auto_raw, debug=debug)

        if not self._should_try_forced_languages(auto_clean):
            if debug and auto_clean:
                print(f"Selected auto transcript directly: {auto_clean}")
            return auto_clean

        pl_raw = self._transcribe(wav_path, "pl", debug=debug)
        pl_clean = self._cleanup_transcript(pl_raw, debug=debug)

        if auto_clean is None and pl_clean is None:
            return None

        if auto_clean is None:
            if debug and pl_clean:
                print("Selected transcript from: pl (auto was empty)")
            return pl_clean

        if pl_clean is None:
            if debug and auto_clean:
                print("Selected transcript from: auto (pl was empty)")
            return auto_clean

        auto_score = self._score_transcript(auto_clean, "auto")
        auto_en_score = self._score_transcript(auto_clean, "en")
        pl_score = self._score_transcript(pl_clean, "pl")

        auto_normalized = self._normalize_text(auto_clean)
        auto_tokens = set(self._normalized_word_tokens(auto_clean))
        pl_normalized = self._normalize_text(pl_clean)
        pl_tokens = set(self._normalized_word_tokens(pl_clean))

        if debug:
            print(
                "Candidate summary: "
                f"auto={repr(auto_clean)} score={auto_score:.2f} en={auto_en_score:.2f} | "
                f"pl={repr(pl_clean)} score={pl_score:.2f}"
            )

        if self._is_exact_phrase(pl_normalized, "pl"):
            if debug:
                print("Selected transcript from: pl (exact polish phrase)")
            return pl_clean

        if (
            len(pl_tokens) <= 8
            and pl_score >= auto_score - 0.2
            and len(pl_tokens & self._lang_keywords["pl"]) >= 2
        ):
            if debug:
                print("Selected transcript from: pl (short utterance polish bias)")
            return pl_clean

        if auto_normalized in self._suspicious_auto_phrases and pl_score >= 1.6:
            if debug:
                print("Selected transcript from: pl (suspicious auto phrase)")
            return pl_clean

        if pl_score > (auto_score + 0.20):
            if debug:
                print("Selected transcript from: pl")
            return pl_clean

        if len(auto_tokens) <= 5 and pl_score >= auto_score and pl_score >= 2.0:
            if debug:
                print("Selected transcript from: pl (short utterance tie-break)")
            return pl_clean

        if debug:
            print("Selected transcript from: auto")
        return auto_clean

    def _cleanup_temp_files(self) -> None:
        self._clear_previous_output_files()

    def close(self) -> None:
        self._cleanup_temp_files()
        try:
            if self._session_temp_dir.exists():
                shutil.rmtree(self._session_temp_dir, ignore_errors=True)
        except Exception as error:
            append_log(f"Whisper temp directory cleanup warning: {error}")

    def listen(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        try:
            pcm_bytes = self._record_until_silence(timeout=timeout, debug=debug)
            if not pcm_bytes:
                return None
        except Exception as error:
            append_log(f"Audio capture failed: {error}")
            return None

        wav_path = self._write_wav(pcm_bytes)

        try:
            cleaned = self._select_best_transcript(wav_path, debug=debug)

            if debug and cleaned:
                print(f"Whisper transcript: {cleaned}")

            return cleaned

        except subprocess.TimeoutExpired:
            append_log("Whisper transcription timed out.")
            return None
        except Exception as error:
            append_log(f"Whisper listen error: {error}")
            return None
        finally:
            self._cleanup_temp_files()

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        return self.listen(timeout=timeout, debug=debug)

    @staticmethod
    def list_audio_devices() -> None:
        print(sd.query_devices())

    @staticmethod
    def _now() -> float:
        return time.monotonic()