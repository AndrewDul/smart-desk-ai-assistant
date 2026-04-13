from __future__ import annotations

import time
from typing import Any

from modules.core.session.voice_session import VOICE_STATE_STANDBY
from modules.shared.logging.logger import append_log, log_exception


class NotificationFlowContext:
    """Interaction context reset helpers for async notifications."""

    assistant: Any
    interrupt_settle_seconds: float

    def clear_interaction_context(
        self,
        *,
        reason: str,
        close_active_window: bool = True,
        interrupt_output: bool = True,
    ) -> None:
        assistant = self.assistant

        had_pending_confirmation = assistant.pending_confirmation is not None
        had_pending_follow_up = assistant.pending_follow_up is not None

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

        if interrupt_output:
            self._request_interrupt(reason=reason)
            self._stop_current_playback()
            if self.interrupt_settle_seconds > 0:
                time.sleep(self.interrupt_settle_seconds)

        transition_to_standby = getattr(assistant.voice_session, "transition_to_standby", None)
        if callable(transition_to_standby):
            try:
                transition_to_standby(
                    detail=reason,
                    close_active_window=close_active_window,
                )
            except Exception as error:
                log_exception("Failed to set standby state before notification", error)
        else:
            if close_active_window:
                try:
                    assistant.voice_session.close_active_window()
                except Exception as error:
                    log_exception("Failed to close active voice window for notification", error)

            try:
                assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail=reason)
            except Exception as error:
                log_exception("Failed to set standby state before notification", error)

        if had_pending_confirmation or had_pending_follow_up:
            append_log(
                "Interaction context cleared for notification: "
                f"reason={reason}, "
                f"had_pending_confirmation={had_pending_confirmation}, "
                f"had_pending_follow_up={had_pending_follow_up}"
            )


__all__ = ["NotificationFlowContext"]