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

        stop_stream = getattr(self, "_stop_active_output_stream", None)
        if callable(stop_stream):
            try:
                stop_stream()
            except Exception:
                pass

        with self._process_lock:
            processes = list(self._active_processes)

        for process in processes:
            self._terminate_process(process, reason="stop_request")

    def _resolve_output_hold_seconds(
        self,
        *,
        interrupted: bool,
        success: bool,
        spoken_text: str,
        output_hold_override: float | None = None,
    ) -> float:
        if not success:
            return 0.0

        if output_hold_override is not None:
            try:
                return max(0.0, float(output_hold_override))
            except (TypeError, ValueError):
                pass

        if interrupted:
            return max(
                0.0,
                float(getattr(self, "_interrupted_output_hold_seconds", 0.10)),
            )

        short_response_max_chars = int(
            getattr(self, "_short_response_output_hold_max_chars", 48)
        )
        if len(str(spoken_text or "").strip()) <= short_response_max_chars:
            return max(
                0.0,
                float(getattr(self, "_short_response_output_hold_seconds", 0.18)),
            )

        coordinator = getattr(self, "audio_coordinator", None)
        if coordinator is not None:
            value = getattr(coordinator, "post_speech_hold_seconds", None)
            if value is not None:
                try:
                    return max(0.0, float(value))
                except (TypeError, ValueError):
                    pass

        return 0.32


__all__ = ["TTSPipelineControlMixin"]