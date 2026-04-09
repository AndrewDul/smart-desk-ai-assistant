from __future__ import annotations

from typing import Any

from modules.core.session.voice_session import (
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
)
from modules.shared.logging.logger import log_exception


class NotificationFlowInternals:
    """Internal helper methods for async notification delivery."""

    assistant: Any

    def _request_interrupt(self, *, reason: str) -> None:
        request_interrupt = getattr(self.assistant, "request_interrupt", None)
        if not callable(request_interrupt):
            return

        try:
            request_interrupt(
                reason=f"notification:{reason}",
                source="notification_flow",
                metadata={"reason": reason},
            )
        except TypeError:
            try:
                request_interrupt()
            except Exception as error:
                log_exception("Failed to request interrupt for notification", error)
        except Exception as error:
            log_exception("Failed to request interrupt for notification", error)

    def _stop_current_playback(self) -> None:
        voice_out = getattr(self.assistant, "voice_out", None)
        if voice_out is None:
            return

        stop_method = getattr(voice_out, "stop_playback", None)
        if not callable(stop_method):
            return

        try:
            stop_method()
        except Exception as error:
            log_exception("Failed to stop current playback for notification", error)

    def _remember_notification_turn(
        self,
        *,
        text: str,
        language: str,
        metadata: dict[str, Any],
    ) -> None:
        remember_method = getattr(self.assistant, "_remember_assistant_turn", None)
        if not callable(remember_method):
            return

        try:
            remember_method(text, language=language, metadata=metadata)
        except TypeError:
            try:
                remember_method(text, language, metadata)
            except Exception as error:
                log_exception("Failed to remember async notification turn", error)
        except Exception as error:
            log_exception("Failed to remember async notification turn", error)

    def _show_display_block(
        self,
        *,
        title: str,
        lines: list[str],
        duration: float | None,
    ) -> None:
        display = getattr(self.assistant, "display", None)
        if display is None:
            return

        show_block = getattr(display, "show_block", None)
        if not callable(show_block):
            return

        safe_title = self._clean_text(title) or "NEXA"
        safe_duration = (
            float(duration)
            if duration is not None
            else float(getattr(self.assistant, "default_overlay_seconds", 8.0))
        )

        try:
            show_block(safe_title, lines, duration=safe_duration)
        except Exception as error:
            log_exception("Failed to show async notification display block", error)

    def _speak_notification(
        self,
        *,
        text: str,
        language: str,
        detail: str,
    ) -> None:
        assistant = self.assistant

        try:
            assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail=detail)
        except Exception as error:
            log_exception("Failed to set speaking state for notification", error)

        try:
            assistant.voice_out.speak(text, language=language)
        except Exception as error:
            log_exception("Failed to speak async notification", error)
        finally:
            try:
                assistant.voice_session.close_active_window()
            except Exception as error:
                log_exception("Failed to close active window after notification", error)

            try:
                assistant.voice_session.set_state(
                    VOICE_STATE_STANDBY,
                    detail=f"{detail}:complete",
                )
            except Exception as error:
                log_exception("Failed to return to standby after notification", error)


__all__ = ["NotificationFlowInternals"]