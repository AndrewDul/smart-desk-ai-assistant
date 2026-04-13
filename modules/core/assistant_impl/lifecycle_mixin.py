from __future__ import annotations

import time

from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_STANDBY,
)
from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantLifecycleMixin:
    def _mark_runtime_state(self, method_name: str, reason: str) -> None:
        runtime_product = getattr(self, "runtime_product", None)
        if runtime_product is None:
            return

        method = getattr(runtime_product, method_name, None)
        if not callable(method):
            return

        try:
            method(reason=reason)
        except Exception as error:
            log_exception(f"Failed to update runtime product state via {method_name}", error)

    def _warmup_local_llm_backend(self) -> None:
        dialogue = getattr(self, "dialogue", None)
        local_llm = getattr(dialogue, "local_llm", None)
        if local_llm is None:
            return

        warmup_method = getattr(local_llm, "warmup_backend_if_enabled", None)
        if not callable(warmup_method):
            return

        append_log("Local LLM warmup requested during boot.")
        try:
            warmed = bool(warmup_method())
            if warmed:
                append_log("Local LLM warmup completed during boot.")
                return

            last_warmup_error = str(getattr(local_llm, "_last_warmup_error", "") or "").strip()
            if last_warmup_error:
                append_log(f"Local LLM warmup did not complete: {last_warmup_error}")
            else:
                append_log("Local LLM warmup did not complete.")
        except Exception as error:
            log_exception("Local LLM warmup failed during boot", error)

    def boot(self) -> None:
        self.shutdown_requested = False
        self.last_language = "en"
        self._clear_interaction_context(close_active_window=True)
        self._mark_runtime_state("mark_booting", "assistant boot sequence started")

        self.state["assistant_running"] = True
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        if not self._reminder_thread.is_alive():
            self._reminder_thread.start()

        self.display.show_block(
            self.ASSISTANT_NAME,
            self._runtime_overlay_lines(),
            duration=self.boot_overlay_seconds,
        )
        append_log("Assistant boot sequence started.")

        overlay_started_at = time.perf_counter()
        self._warmup_local_llm_backend()

        min_boot_visual_seconds = max(self.boot_overlay_seconds, 0.8)
        elapsed_since_overlay = time.perf_counter() - overlay_started_at
        if elapsed_since_overlay < min_boot_visual_seconds:
            time.sleep(min_boot_visual_seconds - elapsed_since_overlay)

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

        if self._boot_report_ok:
            self._mark_runtime_state("mark_ready", "assistant boot completed")
        else:
            snapshot = self._runtime_status_snapshot()
            reason = str(
                snapshot.get("status_message", "") or "assistant boot completed in degraded mode"
            ).strip()
            self._mark_runtime_state("mark_degraded", reason)

        self.voice_session.set_state(VOICE_STATE_STANDBY, detail="startup_complete")
        append_log("Assistant booted.")

    def shutdown(self) -> None:
        append_log("Assistant shutdown started.")
        self._mark_runtime_state("mark_shutting_down", "assistant shutdown started")
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

        try:
            self.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="assistant_shutdown")
        except Exception as error:
            log_exception("Failed to update voice session during shutdown", error)

        self._mark_runtime_state("mark_stopped", "assistant shut down")
        append_log("Assistant shut down.")