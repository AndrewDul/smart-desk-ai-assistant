from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


class WhisperCppRuntimeMixin:
    @classmethod
    def _normalize_language(cls, language: str | None, *, allow_auto: bool = False) -> str:
        normalized = str(language or "").strip().lower()
        if allow_auto and normalized in {"", "auto"}:
            return "auto"
        if normalized in cls.SUPPORTED_LANGUAGES:
            return normalized
        return "auto" if allow_auto else "en"

    @staticmethod
    def _discover_project_root() -> Path:
        current = Path(__file__).resolve()
        for candidate in current.parents:
            if (candidate / "modules").exists() and (candidate / "config").exists():
                return candidate
        return current.parents[5]

    @classmethod
    def _resolve_project_path(cls, raw_path: str | Path) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return cls._discover_project_root() / candidate

    @classmethod
    def _resolve_whisper_cli_path(cls, whisper_cli_path: str) -> Path:
        direct_path = cls._resolve_project_path(whisper_cli_path)
        if direct_path.exists():
            return direct_path

        cli_name = Path(whisper_cli_path).name
        discovered = shutil.which(cli_name) or shutil.which("whisper-cli")
        if discovered:
            return Path(discovered)

        return direct_path

    def set_audio_coordinator(self, audio_coordinator: AssistantAudioCoordinator | None) -> None:
        self.audio_coordinator = audio_coordinator

    def _input_blocked_by_assistant_output(self) -> bool:
        if self.audio_coordinator is None:
            return False

        try:
            blocked = bool(self.audio_coordinator.input_blocked())
        except Exception:
            return False

        if blocked:
            self._last_input_blocked_monotonic = self._now()

        return blocked

    def _recently_unblocked(self) -> bool:
        if self._last_input_blocked_monotonic <= 0.0:
            return False
        return (self._now() - self._last_input_blocked_monotonic) < self.input_unblock_settle_seconds

    def _ensure_runtime_ready(self) -> None:
        if not self.whisper_cli_path.exists():
            raise FileNotFoundError(f"whisper-cli not found at: {self.whisper_cli_path}")

        if not self.model_path.exists():
            raise FileNotFoundError(f"Whisper model not found at: {self.model_path}")

        if self.vad_enabled and self.vad_model_path and not self.vad_model_path.exists():
            self.LOGGER.warning(
                "Whisper VAD model not found at '%s'. whisper.cpp will continue without CLI VAD.",
                self.vad_model_path,
            )