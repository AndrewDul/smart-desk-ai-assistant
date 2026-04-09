from __future__ import annotations

import time

from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_STANDBY,
)
from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantLifecycleMixin:
    def boot(self) -> None:
        self.shutdown_requested = False
        self.last_language = "en"
        self._clear_interaction_context(close_active_window=True)

        self.state["assistant_running"] = True
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        if not self._reminder_thread.is_alive():
            self._reminder_thread.start()

        self.display.show_block(
            self.ASSISTANT_NAME,
            [
                "starting up...",
                "voice assistant ready",
            ],
            duration=self.boot_overlay_seconds,
        )
        append_log("Assistant boot sequence started.")

        time.sleep(max(self.boot_overlay_seconds, 0.8))
        self.display.clear_overlay()

        startup_text = self._startup_greeting(report_ok=self._boot_report_ok)
        self.voice_out.speak(startup_text, language="en")
        self._remember_assistant_turn(
            startup_text,
            language="en",
            metadata={
                "source": "system_boot",
                "route_kind": "system_boot",
            },
        )

        self.voice_session.set_state(VOICE_STATE_STANDBY, detail="startup_complete")
        append_log("Assistant booted.")

    def shutdown(self) -> None:
        append_log("Assistant shutdown started.")
        self._stop_background.set()
        self.request_interrupt(reason="shutdown", source="assistant.shutdown")
        self._thinking_ack_stop()

        try:
            timer_status = self._safe_timer_status()
            if timer_status.get("running"):
                stop_method = getattr(self.timer, "stop", None)
                if callable(stop_method):
                    stop_method()
        except Exception as error:
            log_exception("Failed to stop timer during shutdown", error)

        self.state["assistant_running"] = False
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        shutdown_text = self._localized(
            self.last_language,
            f"Wyłączam {self.ASSISTANT_NAME}.",
            f"Shutting down {self.ASSISTANT_NAME}.",
        )

        self.display.show_block(
            "SHUTDOWN",
            [
                "assistant stopped",
                "see you later",
            ],
            duration=2.0,
        )
        self._remember_assistant_turn(
            shutdown_text,
            language=self.last_language,
            metadata={
                "source": "system_shutdown",
                "route_kind": "system_shutdown",
            },
        )
        self.voice_out.speak(shutdown_text, language=self.last_language)

        self._safe_stop_mobility()
        self._safe_close_runtime_components()

        time.sleep(2.0)
        self.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="assistant_shutdown")
        append_log("Assistant shut down.")