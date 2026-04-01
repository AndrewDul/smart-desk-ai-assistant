from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
from pathlib import Path

from modules.utils import append_log


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

    def _resolve_language(self, language: str | None) -> str:
        lang = (language or self.default_language or "pl").lower().strip()
        if lang not in {"pl", "en"}:
            return self.default_language if self.default_language in {"pl", "en"} else "pl"
        return lang

    def _normalize_text_for_log(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        cleaned = text.strip()

        cleaned = cleaned.replace("OLED", "O led")
        cleaned = cleaned.replace("DevDul", "DevDul")
        cleaned = cleaned.replace("Smart Assistant", "Smart Assistant")

        # Remove technical leftovers that sound unnatural in speech.
        cleaned = cleaned.replace("->", " ")
        cleaned = cleaned.replace("_", " ")
        cleaned = cleaned.replace("/", " ")
        cleaned = cleaned.replace("\\", " ")

        # Collapse whitespace.
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Add a tiny speaking pause after some separators.
        cleaned = cleaned.replace(": ", ". ")
        cleaned = cleaned.replace("; ", ". ")

        # Make speech slightly more natural for short answers.
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        # Avoid weird duplicated punctuation.
        cleaned = re.sub(r"[.]{2,}", ".", cleaned)
        cleaned = re.sub(r"[!]{2,}", "!", cleaned)
        cleaned = re.sub(r"[?]{2,}", "?", cleaned)

        # Make sure there is spacing after punctuation.
        cleaned = re.sub(r"([,.!?])([A-Za-zÀ-ÿ0-9])", r"\1 \2", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # For English speech, normalize some common compact forms if needed.
        if lang == "en":
            replacements = {
                "i m ": "I'm ",
                "i ll ": "I'll ",
                "dont ": "don't ",
                "cant ": "can't ",
                "wont ": "won't ",
            }
            lowered = f" {cleaned.lower()} "
            for src, dst in replacements.items():
                lowered = lowered.replace(src, dst.lower())
            cleaned = lowered.strip()
            if cleaned:
                cleaned = cleaned[0].upper() + cleaned[1:]

        return cleaned

    def _piper_model_ready(self, lang: str) -> bool:
        model_info = self.piper_models.get(lang)
        if not model_info:
            return False

        model_path = Path(model_info["model"])
        config_path = Path(model_info["config"])
        return model_path.exists() and config_path.exists()

    def _play_wav(self, wav_path: Path) -> bool:
        if self.aplay_path:
            result = subprocess.run(
                [self.aplay_path, str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0

        if self.ffplay_path:
            result = subprocess.run(
                [self.ffplay_path, "-autoexit", "-nodisp", str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0

        return False

    def _speak_with_piper(self, text: str, lang: str) -> bool:
        if not self.enabled:
            return False

        model_info = self.piper_models.get(lang)
        if not model_info:
            append_log(f"No Piper model config for language '{lang}'.")
            return False

        model_path = Path(model_info["model"])
        config_path = Path(model_info["config"])

        if not model_path.exists() or not config_path.exists():
            append_log(f"Piper model missing for language '{lang}'.")
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            wav_path = Path(temp_wav.name)

        try:
            synth = subprocess.run(
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
            )

            if synth.returncode != 0:
                append_log(f"Piper synthesis failed for language '{lang}'.")
                return False

            played = self._play_wav(wav_path)
            if not played:
                append_log("No working WAV playback command available.")
            return played

        except Exception as error:
            append_log(f"Piper output error: {error}")
            return False

        finally:
            try:
                if wav_path.exists():
                    wav_path.unlink()
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