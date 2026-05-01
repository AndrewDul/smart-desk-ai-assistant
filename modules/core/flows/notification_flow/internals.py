from __future__ import annotations

import inspect
import time
from typing import Any

from modules.core.session.visual_shell_state_feedback import notify_visual_shell_idle, notify_visual_shell_voice_event
from modules.presentation.visual_shell.contracts import VisualEventName

from modules.core.session.voice_session import (
    VOICE_PHASE_NOTIFICATION,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
)
from modules.shared.logging.logger import append_log, log_exception


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
        notification_settings = dict(
            getattr(assistant, "settings", {}).get("notifications", {})
        )
        pre_speech_settle_seconds = max(
            float(notification_settings.get("pre_speech_settle_seconds", 0.15)),
            0.0,
        )
        post_speech_settle_seconds = max(
            float(notification_settings.get("post_speech_settle_seconds", 0.85)),
            0.0,
        )
        notification_output_hold_seconds = max(
            float(notification_settings.get("output_hold_seconds", 0.04)),
            0.0,
        )

        append_log(
            "Async notification speech starting: "
            f"detail={detail}, language={language}, "
            f"pre_settle={pre_speech_settle_seconds}, "
            f"post_settle={post_speech_settle_seconds}"
        )

        transition_to_speaking = getattr(
            assistant.voice_session,
            "transition_to_speaking",
            None,
        )
        if callable(transition_to_speaking):
            try:
                transition_to_speaking(detail=detail, phase=VOICE_PHASE_NOTIFICATION)
            except Exception as error:
                log_exception("Failed to set speaking state for notification", error)
        else:
            try:
                assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail=detail)
            except Exception as error:
                log_exception("Failed to set speaking state for notification", error)

        notify_visual_shell_voice_event(
            assistant,
            VisualEventName.SPEAKING_STARTED,
            source="notification_flow",
            detail=detail,
            payload={
                "route_kind": "notification",
                "response_source": detail,
            },
        )

        if pre_speech_settle_seconds > 0:
            time.sleep(pre_speech_settle_seconds)

        try:
            speak_method = assistant.voice_out.speak
            try:
                speak_signature = inspect.signature(speak_method)
            except (TypeError, ValueError):
                speak_signature = None

            if (
                speak_signature is not None
                and "output_hold_seconds" in speak_signature.parameters
            ):
                speak_method(
                    text,
                    language=language,
                    output_hold_seconds=notification_output_hold_seconds,
                )
            else:
                speak_method(text, language=language)
        except Exception as error:
            log_exception("Failed to speak async notification", error)
        finally:
            notify_visual_shell_voice_event(
                assistant,
                VisualEventName.SPEAKING_FINISHED,
                source="notification_flow",
                detail=f"{detail}:complete",
                payload={
                    "route_kind": "notification",
                    "response_source": detail,
                },
            )

            if post_speech_settle_seconds > 0:
                time.sleep(post_speech_settle_seconds)

            setattr(assistant, "_force_next_capture_handoff_close", True)
            append_log(
                "Async notification requested force-close on next standby capture handoff: "
                f"detail={detail}, language={language}"
            )

            transition_to_standby = getattr(
                assistant.voice_session,
                "transition_to_standby",
                None,
            )
            if callable(transition_to_standby):
                try:
                    transition_to_standby(
                        detail=f"{detail}:complete",
                        close_active_window=True,
                    )
                except Exception as error:
                    log_exception("Failed to return to standby after notification", error)
            else:
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

            notify_visual_shell_idle(
                assistant,
                source="notification_flow",
                detail=f"{detail}:complete",
            )

            append_log(
                "Async notification speech finished and standby recovery requested: "
                f"detail={detail}, language={language}"
            )


__all__ = ["NotificationFlowInternals"]