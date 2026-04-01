from __future__ import annotations

import json
import queue
import re
import time
from pathlib import Path
from typing import Optional

import sounddevice as sd
from vosk import KaldiRecognizer, Model


class VoiceInput:
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[int] = 2,
        use_grammar: bool = False,
    ) -> None:
        project_root = Path(__file__).resolve().parent.parent

        if model_path is None:
            model_path = str(project_root / "models" / "vosk-model-small-en-us-0.15")

        self.model_path = model_path
        self.device = device
        self.use_grammar = use_grammar
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.command_aliases = {
            "help": "help",
            "show help": "help",
            "what can you do": "help",
            "show commands": "help",

            "show menu": "show menu",
            "open menu": "show menu",
            "menu": "show menu",

            "status": "status",
            "show status": "status",

            "memory": "memory",
            "show memory": "memory",

            "reminders": "reminders",
            "show reminders": "reminders",
            "list reminders": "reminders",

            "stop timer": "stop timer",

            "exit": "exit",
            "quit": "exit",
            "quit assistant": "exit",
            "exit assistant": "exit",
            "close assistant": "exit",
        }

        self.grammar = list(self.command_aliases.keys()) + ["[unk]"]

        model_dir = Path(self.model_path)
        if not model_dir.exists():
            raise FileNotFoundError(
                f"Vosk model not found at: {model_dir}. "
                "Make sure the model folder exists in models/."
            )

        self.model = Model(str(model_dir))

        input_info = sd.query_devices(self.device, "input")
        self.device_name = input_info["name"]
        default_samplerate = input_info.get("default_samplerate", 16000)
        self.sample_rate = int(default_samplerate) if default_samplerate else 16000

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"Audio status: {status}")
        self.audio_queue.put(bytes(indata))

    def _create_recognizer(self) -> KaldiRecognizer:
        if self.use_grammar:
            return KaldiRecognizer(
                self.model,
                self.sample_rate,
                json.dumps(self.grammar),
            )
        return KaldiRecognizer(self.model, self.sample_rate)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.lower().strip()
        text = text.replace(" equals ", " = ")
        text = text.replace(" equal ", " = ")
        text = re.sub(r"[^a-z0-9\s=\.]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _map_to_command(self, text: str) -> Optional[str]:
        cleaned = self._clean_text(text)

        if not cleaned:
            return None

        if cleaned in self.command_aliases:
            return self.command_aliases[cleaned]

        if cleaned.startswith("recall "):
            return cleaned

        if cleaned.startswith("remember "):
            return cleaned

        focus_match = re.match(r"^focus(?: for)? (\d+(?:\.\d+)?)(?: minutes?)?$", cleaned)
        if focus_match:
            return f"focus {focus_match.group(1)}"

        break_match = re.match(r"^break(?: for)? (\d+(?:\.\d+)?)(?: minutes?)?$", cleaned)
        if break_match:
            return f"break {break_match.group(1)}"

        remind_match = re.match(
            r"^remind(?: me)?(?: in)? (\d+) seconds? (?:that |to )?(.+)$",
            cleaned,
        )
        if remind_match:
            seconds = remind_match.group(1)
            message = remind_match.group(2).strip()
            return f"remind {seconds} | {message}"

        return None

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        recognizer = self._create_recognizer()
        self.audio_queue = queue.Queue()

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8000,
            device=self.device,
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        ):
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    data = self.audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()

                    if debug and text:
                        print(f"Raw recognized: {text}")

                    command = self._map_to_command(text)
                    if command:
                        return command
                else:
                    if debug:
                        partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                        if partial:
                            print(f"Partial: {partial}")

            final_result = json.loads(recognizer.FinalResult())
            final_text = final_result.get("text", "").strip()

            if debug:
                print(f"Final raw recognized: {final_text}")

            return self._map_to_command(final_text)

    def listen(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        return self.listen_once(timeout=timeout, debug=debug)

    @staticmethod
    def list_audio_devices() -> None:
        print(sd.query_devices())


class TextVoiceInput:
    def listen(self, timeout: float = 0.0, debug: bool = False) -> Optional[str]:
        try:
            return input(">> ").strip()
        except EOFError:
            return None
