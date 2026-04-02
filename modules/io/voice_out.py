from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from modules.system.utils import BASE_DIR, CACHE_DIR, append_log


class VoiceOutput:
    def __init__(
        self,
        enabled: bool = True,
        preferred_engine: str = "piper",
        default_language: str = "pl",
        speed: int = 155,
        pitch: int = 58,
        voices: dict[str, str] | None = None,
        piper_models: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.enabled = enabled
        self.preferred_engine = preferred_engine.lower().strip()
        self.default_language = default_language.lower().strip()
        self.speed = speed
        self.pitch = pitch

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
        self._base_dir = BASE_DIR
        self._tts_cache_dir = CACHE_DIR / "tts"
        self._tts_cache_dir.mkdir(parents=True, exist_ok=True)

        self._playback_timeout_seconds = 30
        self._synthesis_timeout_seconds = 30

    def _resolve_language(self, language: str | None) -> str:
        lang = (language or self.default_language or "pl").lower().strip()
        if lang not in {"pl", "en"}:
            return self.default_language if self.default_language in {"pl", "en"} else "pl"
        return lang

    @staticmethod
    def _normalize_text_for_log(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        cleaned = text.strip()

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
            }
            lowered = cleaned.lower()
            for pattern, replacement in replacements.items():
                lowered = re.sub(pattern, replacement.lower(), lowered)
            cleaned = lowered.strip()
            if cleaned:
                cleaned = cleaned[0].upper() + cleaned[1:]

        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        return cleaned

    def _resolve_project_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return self._base_dir / candidate

    def _piper_model_ready(self, lang: str) -> bool:
        model_info = self.piper_models.get(lang)
        if not model_info:
            return False

        model_path = self._resolve_project_path(model_info["model"])
        config_path = self._resolve_project_path(model_info["config"])
        return model_path.exists() and config_path.exists()

    def _cache_key(self, text: str, lang: str) -> str:
        digest = hashlib.sha256(f"{lang}|{text}".encode("utf-8")).hexdigest()
        return digest[:24]

    def _cached_wav_path(self, text: str, lang: str) -> Path:
        return self._tts_cache_dir / f"{lang}_{self._cache_key(text, lang)}.wav"

    def _play_wav(self, wav_path: Path) -> bool:
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
                return result.returncode == 0
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
                return result.returncode == 0
            except Exception as error:
                append_log(f"ffplay playback error: {error}")

        return False

    def _synthesize_piper_to_wav(self, text: str, lang: str, wav_path: Path) -> bool:
        model_info = self.piper_models.get(lang)
        if not model_info:
            append_log(f"No Piper model config for language '{lang}'.")
            return False

        model_path = self._resolve_project_path(model_info["model"])
        config_path = self._resolve_project_path(model_info["config"])

        if not model_path.exists() or not config_path.exists():
            append_log(f"Piper model missing for language '{lang}'.")
            return False

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
            append_log(f"Piper output error: {error}")
            return False

    def _speak_with_piper(self, text: str, lang: str) -> bool:
        if not self.enabled:
            return False

        cache_path = self._cached_wav_path(text, lang)

        if cache_path.exists():
            played = self._play_wav(cache_path)
            if played:
                return True
            append_log("Cached Piper audio exists but playback failed, retrying synthesis.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_path = Path(temp_wav.name)

        try:
            synthesized = self._synthesize_piper_to_wav(text, lang, temp_wav_path)
            if not synthesized:
                return False

            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                if not cache_path.exists():
                    shutil.copy2(temp_wav_path, cache_path)
            except Exception as error:
                append_log(f"Piper cache write skipped: {error}")

            played = self._play_wav(temp_wav_path)
            if not played:
                append_log("No working WAV playback command available.")
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

        voice = self.voices.get(lang, self.voices.get(self.default_language, "pl+f3"))

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

    def speak(self, text: str, language: str | None = None) -> None:
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return

        print(f"Assistant> {cleaned_text}")
        append_log(f"Assistant said [{lang}]: {cleaned_text}")

        if not self.enabled:
            return

        with self._lock:
            if self.preferred_engine == "piper" and self._piper_model_ready(lang):
                used_piper = self._speak_with_piper(tts_text, lang)
                if used_piper:
                    return

            used_espeak = self._speak_with_espeak(tts_text, lang)
            if not used_espeak:
                append_log("Voice output failed for all available engines.")