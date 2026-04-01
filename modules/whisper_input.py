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

from modules.utils import append_log


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
    ) -> None:
        self.whisper_cli_path = str(Path(whisper_cli_path).expanduser())
        self.model_path = str(Path(model_path).expanduser())
        self.vad_enabled = vad_enabled
        self.vad_model_path = str(Path(vad_model_path).expanduser()) if vad_model_path else None
        self.language = language

        self.max_record_seconds = float(max_record_seconds)
        self.silence_threshold = float(silence_threshold)
        self.end_silence_seconds = float(end_silence_seconds)
        self.pre_roll_seconds = float(pre_roll_seconds)
        self.threads = int(threads)

        self.blocksize = 1024
        self.channels = 1
        self.dtype = "int16"
        self.audio_queue: queue.Queue[bytes] = queue.Queue()

        self.device = self._resolve_input_device(device_index, device_name_contains)
        input_info = sd.query_devices(self.device, "input")
        self.device_name = input_info["name"]
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
                if wanted in device["name"].lower():
                    return index
            raise ValueError(f"Input device containing '{device_name_contains}' was not found.")

        return device_index

    def _resolve_supported_sample_rate(self, preferred_sample_rate: Optional[int]) -> int:
        candidates: list[int] = []

        if preferred_sample_rate:
            candidates.append(int(preferred_sample_rate))

        candidates.extend([
            self.device_default_sample_rate,
            48000,
            44100,
            32000,
            16000,
        ])

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
            print(f"Audio status: {status}")
        self.audio_queue.put(bytes(indata))

    def _record_until_silence(self, timeout: float, debug: bool = False) -> bytes | None:
        self.audio_queue = queue.Queue()
        pre_roll = deque(maxlen=max(1, int((self.pre_roll_seconds * self.sample_rate) / self.blocksize)))
        recorded_chunks: list[bytes] = []

        speech_started = False
        speech_start_time = 0.0
        silence_started_at: float | None = None
        listen_started_at = time.time()

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            dtype=self.dtype,
            channels=self.channels,
            callback=self._audio_callback,
        ):
            while True:
                try:
                    chunk = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if not speech_started and (time.time() - listen_started_at) >= timeout:
                        if debug:
                            print("No speech detected before timeout.")
                        return None

                    if speech_started and (time.time() - speech_start_time) >= self.max_record_seconds:
                        break
                    continue

                audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0

                if debug:
                    print(f"RMS: {rms:.2f}")

                if not speech_started:
                    pre_roll.append(chunk)

                    if rms >= self.silence_threshold:
                        speech_started = True
                        speech_start_time = time.time()
                        recorded_chunks.extend(pre_roll)
                        recorded_chunks.append(chunk)
                        silence_started_at = None

                        if debug:
                            print("Speech started.")
                    else:
                        if (time.time() - listen_started_at) >= timeout:
                            if debug:
                                print("Timeout reached without speech.")
                            return None
                    continue

                recorded_chunks.append(chunk)

                if rms < self.silence_threshold:
                    if silence_started_at is None:
                        silence_started_at = time.time()
                    elif (time.time() - silence_started_at) >= self.end_silence_seconds:
                        if debug:
                            print("Detected end-of-speech silence.")
                        break
                else:
                    silence_started_at = None

                if (time.time() - speech_start_time) >= self.max_record_seconds:
                    if debug:
                        print("Max record duration reached.")
                    break

        if not recorded_chunks:
            return None

        return b"".join(recorded_chunks)

    def _write_wav(self, pcm_bytes: bytes) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="smartdesk_whisper_"))
        wav_path = temp_dir / "utterance.wav"

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_bytes)

        return wav_path

    def _transcribe(self, wav_path: Path, debug: bool = False) -> str:
        output_prefix = wav_path.with_suffix("")
        cmd = [
            self.whisper_cli_path,
            "--model", self.model_path,
            "--file", str(wav_path),
            "--language", self.language,
            "--threads", str(self.threads),
            "--output-txt",
            "--output-file", str(output_prefix),
            "--no-timestamps",
            "--no-prints",
        ]

        if self.vad_enabled and self.vad_model_path:
            cmd.extend(["--vad", "--vad-model", self.vad_model_path])

        if debug:
            print(f"Using input device: {self.device_name}")
            print(f"Using sample rate: {self.sample_rate}")
            print("Whisper command:")
            print(" ".join(cmd))

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                "Whisper transcription failed.\n"
                f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
            )

        transcript_path = output_prefix.with_suffix(".txt")
        if not transcript_path.exists():
            return ""

        return transcript_path.read_text(encoding="utf-8").strip()

    def _normalize_text(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered.strip()

    def _cleanup_transcript(self, transcript: str, debug: bool = False) -> str | None:
        if not transcript:
            return None

        cleaned = transcript.strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return None

        normalized = self._normalize_text(cleaned)

        blank_markers = {
            "",
            "[blank_audio]",
            "blank_audio",
            "[silence]",
            "silence",
            "no speech",
            "no speech recognized",
            "[noise]",
            "noise",
            "...",
            ".",
        }

        # Common whisper hallucinations after silence / empty capture.
        hallucination_markers = {
            "thank you",
            "thanks for watching",
            "you",
            "bye",
            "okay",
            "ok",
        }

        if normalized in blank_markers:
            if debug:
                print(f"Ignored blank marker transcript: {cleaned}")
            return None

        if normalized in hallucination_markers:
            if debug:
                print(f"Ignored likely silence hallucination: {cleaned}")
            append_log(f"Ignored likely silence hallucination: {cleaned}")
            return None

        # Ignore transcripts that are only punctuation-like brackets or separators.
        stripped_symbols = re.sub(r"[\[\](){}<>\-_=~.,!?\"'`]", "", cleaned).strip()
        if not stripped_symbols:
            if debug:
                print(f"Ignored symbol-only transcript: {cleaned}")
            return None

        return cleaned

    def _cleanup_temp_files(self, wav_path: Path) -> None:
        try:
            output_prefix = wav_path.with_suffix("")
            txt_path = output_prefix.with_suffix(".txt")
            srt_path = output_prefix.with_suffix(".srt")
            vtt_path = output_prefix.with_suffix(".vtt")
            json_path = output_prefix.with_suffix(".json")
            lrc_path = output_prefix.with_suffix(".lrc")

            for path in [wav_path, txt_path, srt_path, vtt_path, json_path, lrc_path]:
                if path.exists():
                    path.unlink()

            temp_dir = wav_path.parent
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as error:
            append_log(f"Temp cleanup warning: {error}")

    def listen(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        pcm_bytes = self._record_until_silence(timeout=timeout, debug=debug)
        if not pcm_bytes:
            return None

        wav_path = self._write_wav(pcm_bytes)

        try:
            transcript = self._transcribe(wav_path, debug=debug)
            cleaned = self._cleanup_transcript(transcript, debug=debug)

            if debug and cleaned:
                print(f"Whisper transcript: {cleaned}")

            return cleaned

        finally:
            self._cleanup_temp_files(wav_path)

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> Optional[str]:
        return self.listen(timeout=timeout, debug=debug)

    @staticmethod
    def list_audio_devices() -> None:
        print(sd.query_devices())