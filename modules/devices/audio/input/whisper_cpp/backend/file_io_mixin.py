from __future__ import annotations

import re
import subprocess
import wave
from pathlib import Path


class WhisperCppFileIOMixin:
    def _write_temp_wav(self, audio) -> Path:
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

        if self.vad_enabled and self.vad_model_path is not None and self.vad_model_path.exists():
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