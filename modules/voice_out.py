from __future__ import annotations

import shutil
import subprocess
import threading

from modules.utils import append_log


class VoiceOutput:
    def __init__(
        self,
        enabled: bool = True,
        preferred_engine: str = "espeak-ng",
        default_language: str = "pl",
        speed: int = 155,
        pitch: int = 58,
        voices: dict[str, str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.engine_path = None

        if enabled:
            self.engine_path = shutil.which(preferred_engine) or shutil.which("espeak")

        self.default_language = default_language
        self.speed = speed
        self.pitch = pitch
        self.voices = voices or {
            "pl": "pl+f3",
            "en": "en+f3",
        }

        self._lock = threading.Lock()

    def speak(self, text: str, language: str | None = None) -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return

        print(f"Assistant> {cleaned_text}")
        append_log(f"Assistant said: {cleaned_text}")

        if not self.enabled or not self.engine_path:
            return

        lang = (language or self.default_language or "pl").lower()
        if lang not in {"pl", "en"}:
            lang = self.default_language

        voice = self.voices.get(lang, self.voices.get(self.default_language, "pl+f3"))

        with self._lock:
            try:
                subprocess.run(
                    [
                        self.engine_path,
                        "-v",
                        voice,
                        "-s",
                        str(self.speed),
                        "-p",
                        str(self.pitch),
                        "--stdin",
                    ],
                    input=cleaned_text,
                    text=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as error:
                append_log(f"Voice output error: {error}")