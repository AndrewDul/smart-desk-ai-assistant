from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from modules.system.utils import BASE_DIR, CACHE_DIR, append_log


class VoiceOutput:
    _CACHE_VERSION = "tts-v2-neksa-pronunciation"

    def __init__(
        self,
        enabled: bool = True,
        preferred_engine: str = "piper",
        default_language: str = "en",
        speed: int = 155,
        pitch: int = 58,
        voices: dict[str, str] | None = None,
        piper_models: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.preferred_engine = str(preferred_engine or "piper").lower().strip()
        self.default_language = self._normalize_language(default_language)
        self.speed = int(speed)
        self.pitch = int(pitch)

        self.voices = voices or {
            "pl": "pl+f3",
            "en": "en+f3",
        }

        self.piper_models = piper_models or {
            "pl": {
                "model": "voices/piper/pl_PL-gosia-medium.onnx",
                "config": "voices/piper/pl_PL-gosia-medium.onnx.json",
            },
            "en": {
                "model": "voices/piper/en_GB-jenny_dioco-medium.onnx",
                "config": "voices/piper/en_GB-jenny_dioco-medium.onnx.json",
            },
        }

        self.python_path = sys.executable
        self.aplay_path = shutil.which("aplay")
        self.ffplay_path = shutil.which("ffplay")
        self.espeak_path = shutil.which("espeak-ng") or shutil.which("espeak")

        self._lock = threading.Lock()
        self._speak_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._current_process: subprocess.Popen | None = None

        self._base_dir = BASE_DIR
        self._tts_cache_dir = CACHE_DIR / "tts"
        self._tts_cache_dir.mkdir(parents=True, exist_ok=True)

        self._playback_timeout_seconds = 30
        self._synthesis_timeout_seconds = 30

        self._piper_ready_cache: dict[str, bool] = {}
        self._cache_warmup_thread: threading.Thread | None = None

        self.audio_coordinator = None

        self._common_cache_phrases: dict[str, list[str]] = {
            "pl": [
                "Dobrze.",
                "Powiedz tak albo nie.",
                "Nie usłyszałam wyraźnie. Powiedz proszę jeszcze raz.",
                "Jak mogę pomóc?",
                "Nie mogę tego teraz zrobić.",
                "Przypomnienie.",
                "Nazywam się NeXa.",
            ],
            "en": [
                "Okay.",
                "Please say yes or no.",
                "I did not catch that clearly. Please say it again.",
                "How can I help?",
                "I cannot do that right now.",
                "Reminder.",
                "My name is NeXa.",
            ],
        }

        self._start_cache_warmup()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    def _resolve_language(self, language: str | None) -> str:
        normalized = self._normalize_language(language)
        if normalized in {"pl", "en"}:
            return normalized
        return self.default_language

    def clear_stop_request(self) -> None:
        self._stop_requested.clear()

    def stop_playback(self) -> None:
        self._stop_requested.set()

        with self._process_lock:
            process = self._current_process

        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.25)
        except Exception as error:
            append_log(f"Voice output stop warning: {error}")

    def _register_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            self._current_process = process

    def _unregister_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            if self._current_process is process:
                self._current_process = None

    def _run_process_interruptibly(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float | None = None,
        source: str = "tts",
    ) -> bool:
        timeout_value = self._playback_timeout_seconds if timeout_seconds is None else max(0.1, float(timeout_seconds))
        started_at = time.monotonic()

        process: subprocess.Popen | None = None

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._register_process(process)

            if input_text is not None and process.stdin is not None:
                try:
                    process.stdin.write(input_text)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                except Exception as error:
                    append_log(f"{source} stdin warning: {error}")

            while True:
                if self._stop_requested.is_set():
                    try:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=0.25)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=0.25)
                    except Exception as error:
                        append_log(f"{source} interrupt stop warning: {error}")
                    return False

                return_code = process.poll()
                if return_code is not None:
                    return return_code == 0

                if time.monotonic() - started_at >= timeout_value:
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=0.25)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=0.25)
                    except Exception as error:
                        append_log(f"{source} timeout stop warning: {error}")

                    append_log(f"{source} process timed out after {timeout_value:.2f}s.")
                    return False

                time.sleep(0.02)

        except Exception as error:
            append_log(f"{source} process error: {error}")
            return False
        finally:
            if process is not None:
                self._unregister_process(process)

    def set_audio_coordinator(self, audio_coordinator) -> None:
        self.audio_coordinator = audio_coordinator

    @staticmethod
    def _normalize_text_for_log(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "").strip())
        return cleaned

    def _apply_brand_pronunciation(self, text: str, lang: str) -> str:
        cleaned = str(text or "")

        # Keep spelling in logs/UI as "NeXa", but force TTS pronunciation to "Neksa".
        # This works more reliably across Piper and eSpeak than leaving mixed casing.
        cleaned = re.sub(r"\bNeXa\b", "Neksa", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bNexa\b", "Neksa", cleaned, flags=re.IGNORECASE)

        # Optional extra stabilization for English TTS around self-introduction.
        if lang == "en":
            cleaned = re.sub(r"\bmy name is neksa\b", "My name is Neksa", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = re.sub(r"\bnazywam sie neksa\b", "Nazywam się Neksa", cleaned, flags=re.IGNORECASE)

        return cleaned

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        cleaned = self._apply_brand_pronunciation(cleaned, lang)

        cleaned = cleaned.replace("OLED", "O led")
        cleaned = cleaned.replace("->", " ")
        cleaned = cleaned.replace("_", " ")
        cleaned = cleaned.replace("/", " ")
        cleaned = cleaned.replace("\\", " ")

        cleaned = cleaned.replace(": ", ". ")
        cleaned = cleaned.replace("; ", ". ")

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"[.]{2,}", ".", cleaned)
        cleaned = re.sub(r"[!]{2,}", "!", cleaned)
        cleaned = re.sub(r"[?]{2,}", "?", cleaned)
        cleaned = re.sub(r"([,.!?])([A-Za-zÀ-ÿ0-9])", r"\1 \2", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if lang == "en":
            replacements = {
                r"\bi m\b": "I'm",
                r"\bi ll\b": "I'll",
                r"\bdont\b": "don't",
                r"\bcant\b": "can't",
                r"\bwont\b": "won't",
                r"\bwhats\b": "what's",
            }
            lowered = cleaned.lower()
            for pattern, replacement in replacements.items():
                lowered = re.sub(pattern, replacement.lower(), lowered)
            cleaned = lowered.strip()
            if cleaned:
                cleaned = cleaned[:1].upper() + cleaned[1:]

        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        return cleaned

    def _resolve_project_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return self._base_dir / candidate

    def _piper_model_ready(self, lang: str) -> bool:
        lang = self._normalize_language(lang)

        cached = self._piper_ready_cache.get(lang)
        if cached is not None:
            return cached

        model_info = self.piper_models.get(lang)
        if not model_info:
            self._piper_ready_cache[lang] = False
            return False

        model_path = self._resolve_project_path(model_info["model"])
        config_path = self._resolve_project_path(model_info["config"])

        ready = model_path.exists() and config_path.exists()
        self._piper_ready_cache[lang] = ready
        return ready

    @classmethod
    def _cache_key(cls, text: str, lang: str) -> str:
        digest = hashlib.sha256(f"{cls._CACHE_VERSION}|{lang}|{text}".encode("utf-8")).hexdigest()
        return digest[:24]

    def _cached_wav_path(self, text: str, lang: str) -> Path:
        return self._tts_cache_dir / f"{lang}_{self._cache_key(text, lang)}.wav"

    def _play_wav(self, wav_path: Path) -> bool:
        if not wav_path.exists():
            return False

        if self.aplay_path:
            try:
                played = self._run_process_interruptibly(
                    [self.aplay_path, str(wav_path)],
                    timeout_seconds=self._playback_timeout_seconds,
                    source="aplay_playback",
                )
                if played:
                    return True
            except Exception as error:
                append_log(f"aplay playback error: {error}")

        if self.ffplay_path:
            try:
                played = self._run_process_interruptibly(
                    [self.ffplay_path, "-autoexit", "-nodisp", str(wav_path)],
                    timeout_seconds=self._playback_timeout_seconds,
                    source="ffplay_playback",
                )
                if played:
                    return True
            except Exception as error:
                append_log(f"ffplay playback error: {error}")

        return False
        if not wav_path.exists():
            return False

        if self.aplay_path:
            try:
                result = subprocess.run(
                    [self.aplay_path, str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=self._playback_timeout_seconds,
                )
                if result.returncode == 0:
                    return True
            except Exception as error:
                append_log(f"aplay playback error: {error}")

        if self.ffplay_path:
            try:
                result = subprocess.run(
                    [self.ffplay_path, "-autoexit", "-nodisp", str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=self._playback_timeout_seconds,
                )
                if result.returncode == 0:
                    return True
            except Exception as error:
                append_log(f"ffplay playback error: {error}")

        return False

    def _synthesize_piper_to_wav(self, text: str, lang: str, wav_path: Path) -> bool:
        lang = self._normalize_language(lang)
        model_info = self.piper_models.get(lang)

        if not model_info:
            append_log(f"No Piper model config for language '{lang}'.")
            return False

        model_path = self._resolve_project_path(model_info["model"])
        config_path = self._resolve_project_path(model_info["config"])

        if not model_path.exists() or not config_path.exists():
            append_log(f"Piper model missing for language '{lang}'.")
            return False

        wav_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                [
                    self.python_path,
                    "-m",
                    "piper",
                    "-m",
                    str(model_path),
                    "-c",
                    str(config_path),
                    "-f",
                    str(wav_path),
                ],
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=self._synthesis_timeout_seconds,
            )

            if result.returncode != 0:
                append_log(f"Piper synthesis failed for language '{lang}'.")
                return False

            return wav_path.exists()

        except Exception as error:
            append_log(f"Piper synthesis error: {error}")
            return False

    def _prime_cache_entry(self, text: str, lang: str) -> None:
        if not self.enabled:
            return
        if self.preferred_engine != "piper":
            return
        if not self._piper_model_ready(lang):
            return

        cache_path = self._cached_wav_path(text, lang)
        if cache_path.exists():
            return

        success = self._synthesize_piper_to_wav(text, lang, cache_path)
        if not success and cache_path.exists():
            try:
                cache_path.unlink()
            except OSError:
                pass

    def _warm_common_cache(self) -> None:
        try:
            time.sleep(2.0)

            for lang, phrases in self._common_cache_phrases.items():
                for phrase in phrases:
                    tts_text = self._normalize_text_for_tts(phrase, lang)
                    if not tts_text:
                        continue
                    self._prime_cache_entry(tts_text, lang)
        except Exception as error:
            append_log(f"TTS cache warmup skipped: {error}")

    def _start_cache_warmup(self) -> None:
        if not self.enabled:
            return
        if self.preferred_engine != "piper":
            return

        self._cache_warmup_thread = threading.Thread(
            target=self._warm_common_cache,
            name="tts-cache-warmup",
            daemon=True,
        )
        self._cache_warmup_thread.start()

    def _speak_with_piper(self, text: str, lang: str) -> bool:
        if not self.enabled:
            return False
        if not self._piper_model_ready(lang):
            return False

        cache_path = self._cached_wav_path(text, lang)

        if cache_path.exists():
            played = self._play_wav(cache_path)
            if played:
                return True
            append_log(f"Cached Piper audio exists but playback failed for language '{lang}', retrying synthesis.")

        synthesized_to_cache = self._synthesize_piper_to_wav(text, lang, cache_path)
        if synthesized_to_cache:
            played = self._play_wav(cache_path)
            if played:
                return True
            append_log(f"Cached Piper synthesis worked but playback failed for language '{lang}', trying temporary WAV.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)

        try:
            synthesized = self._synthesize_piper_to_wav(text, lang, temp_wav_path)
            if not synthesized:
                return False

            played = self._play_wav(temp_wav_path)
            if not played:
                append_log(f"No working WAV playback command available for language '{lang}'.")
            return played

        finally:
            try:
                if temp_wav_path.exists():
                    temp_wav_path.unlink()
            except Exception:
                pass

    def _speak_with_espeak(self, text: str, lang: str) -> bool:
        if not self.espeak_path:
            append_log("eSpeak is not available.")
            return False

        voice = self.voices.get(lang)
        if not voice:
            append_log(f"No eSpeak voice configured for language '{lang}'.")
            return False

        try:
            result = subprocess.run(
                [
                    self.espeak_path,
                    "-v",
                    voice,
                    "-s",
                    str(self.speed),
                    "-p",
                    str(self.pitch),
                    "--stdin",
                ],
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=self._synthesis_timeout_seconds,
            )
            return result.returncode == 0
        except Exception as error:
            append_log(f"eSpeak output error: {error}")
            return False

    def speak(self, text: str, language: str | None = None) -> bool:
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return False

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return False

        print(f"Assistant> {cleaned_text}")
        append_log(f"Assistant said [{lang}]: {cleaned_text}")

        if not self.enabled:
            return False

        self.clear_stop_request()

        audio_coordinator = getattr(self, "audio_coordinator", None)
        coordinator_token = None
        if audio_coordinator is not None:
            coordinator_token = audio_coordinator.begin_assistant_output(
                source="tts",
                text_preview=cleaned_text,
            )

        try:
            with self._speak_lock:
                if self._stop_requested.is_set():
                    return False

                if self.preferred_engine == "piper":
                    used_piper = self._speak_with_piper(tts_text, lang)
                    if used_piper:
                        return True
                    if self._stop_requested.is_set():
                        return False

                used_espeak = self._speak_with_espeak(tts_text, lang)
                if used_espeak:
                    return True

                if self._stop_requested.is_set():
                    return False

                append_log(f"Voice output failed for language '{lang}' on all available engines.")
                return False
        finally:
            if audio_coordinator is not None:
                audio_coordinator.end_assistant_output(coordinator_token)