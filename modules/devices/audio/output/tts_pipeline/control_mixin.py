from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


class TTSPipelineControlMixin:
    """
    Public control helpers for language resolution and playback interruption.
    """

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    def _resolve_language(self, language: str | None) -> str:
        normalized = self._normalize_language(language)
        return normalized if normalized in {"pl", "en"} else self.default_language

    def set_audio_coordinator(
        self,
        audio_coordinator: AssistantAudioCoordinator | None,
    ) -> None:
        self.audio_coordinator = audio_coordinator

    def clear_stop_request(self) -> None:
        self._stop_requested.clear()

    def stop_playback(self) -> None:
        self._stop_requested.set()

        with self._process_lock:
            processes = list(self._active_processes)

        for process in processes:
            self._terminate_process(process, reason="stop_request")


__all__ = ["TTSPipelineControlMixin"]