from __future__ import annotations

import time
from typing import Any

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

    def _warmup_local_llm_backend(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "attempted": False,
            "ok": False,
            "snapshot": {},
            "error": "",
        }

        dialogue = getattr(self, "dialogue", None)
        local_llm = getattr(dialogue, "local_llm", None)
        if local_llm is None:
            return result

        ensure_method = getattr(local_llm, "ensure_backend_ready", None)
        warmup_method = getattr(local_llm, "warmup_backend_if_enabled", None)

        append_log("Local LLM warmup requested during boot.")

        try:
            if callable(warmup_method):
                result["attempted"] = True
                result["ok"] = bool(warmup_method())
            elif callable(ensure_method):
                snapshot = ensure_method(auto_recover=False)
                if isinstance(snapshot, dict):
                    result["snapshot"] = dict(snapshot)
                    result["ok"] = bool(snapshot.get("warmup_ready", snapshot.get("available", False)))
        except Exception as error:
            result["error"] = str(error)
            log_exception("Local LLM warmup failed during boot", error)

        if callable(ensure_method):
            try:
                snapshot = ensure_method(auto_recover=False)
                if isinstance(snapshot, dict):
                    result["snapshot"] = dict(snapshot)
                    result["ok"] = bool(
                        result["ok"]
                        or snapshot.get("warmup_ready", False)
                        or (
                            snapshot.get("available", False)
                            and not snapshot.get("warmup_required", False)
                        )
                    )
            except Exception as error:
                if not result["error"]:
                    result["error"] = str(error)
                log_exception("Failed to collect Local LLM health snapshot after boot warmup", error)

        snapshot = dict(result.get("snapshot", {}) or {})
        if result["ok"]:
            append_log(
                "Local LLM warmup completed during boot: "
                f"state={snapshot.get('state', '')}, "
                f"available={bool(snapshot.get('available', False))}, "
                f"warmup_ready={bool(snapshot.get('warmup_ready', False))}"
            )
        else:
            error_text = (
                str(snapshot.get("last_error", "") or "").strip()
                or str(snapshot.get("health_reason", "") or "").strip()
                or str(result.get("error", "") or "").strip()
            )
            if error_text:
                append_log(f"Local LLM warmup did not complete: {error_text}")
            else:
                append_log("Local LLM warmup did not complete.")

        return result

    def _refresh_runtime_startup_snapshot_after_llm_warmup(
        self,
        *,
        warmup_result: dict[str, Any] | None = None,
    ) -> None:
        runtime_product = getattr(self, "runtime_product", None)
        if runtime_product is None:
            return

        evaluate_startup = getattr(runtime_product, "evaluate_startup", None)
        if not callable(evaluate_startup):
            return

        startup_allowed = bool(getattr(self, "_runtime_startup_allowed", self._boot_report_ok))
        runtime_warnings = list(getattr(self, "_runtime_startup_runtime_warnings", []))

        try:
            snapshot = evaluate_startup(
                startup_allowed=startup_allowed,
                runtime_warnings=runtime_warnings,
            )
        except Exception as error:
            log_exception("Failed to refresh runtime startup snapshot after LLM warmup", error)
            return

        self._runtime_startup_snapshot = dict(snapshot or {}) if isinstance(snapshot, dict) else {}
        self._boot_report_ok = bool(self._runtime_startup_snapshot.get("ready", False))

        llm_snapshot = dict(warmup_result or {})
        llm_health = dict(llm_snapshot.get("snapshot", {}) or {})

        append_log(
            "Runtime startup snapshot refreshed after LLM warmup: "
            f"premium_ready={bool(self._runtime_startup_snapshot.get('premium_ready', False))}, "
            f"primary_ready={bool(self._runtime_startup_snapshot.get('primary_ready', False))}, "
            f"llm_state={self._runtime_startup_snapshot.get('llm_state', '')}, "
            f"llm_available={bool(self._runtime_startup_snapshot.get('llm_available', False))}, "
            f"llm_warmup_ready={bool(self._runtime_startup_snapshot.get('llm_warmup_ready', False))}, "
            f"warmup_attempted={bool(llm_snapshot.get('attempted', False))}, "
            f"warmup_ok={bool(llm_snapshot.get('ok', False))}, "
            f"health_reason={llm_health.get('health_reason', '')}"
        )

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
        warmup_result = self._warmup_local_llm_backend()
        self._refresh_runtime_startup_snapshot_after_llm_warmup(
            warmup_result=warmup_result,
        )

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