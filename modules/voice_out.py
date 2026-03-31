from __future__ import annotations

import shutil
import subprocess
import threading

from modules.utils import append_log


class VoiceOutput:
    def __init__(self) -> None:
        self.engine_path = shutil.which("espeak-ng")
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return

        print(f"Assistant> {cleaned_text}")
        append_log(f"Assistant said: {cleaned_text}")

        if not self.engine_path:
            return

        with self._lock:
            try:
                subprocess.run(
                    [self.engine_path, cleaned_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as error:
                append_log(f"Voice output error: {error}")
