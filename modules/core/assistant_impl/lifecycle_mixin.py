from __future__ import annotations

import time
from typing import Any

from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_STANDBY,
)
from modules.runtime.startup_gate import StartupGateService
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
        self._boot_report_ok = StartupGateService().is_boot_ready(self._runtime_startup_snapshot)

        llm_snapshot = dict(warmup_result or {})
        llm_health = dict(llm_snapshot.get("snapshot", {}) or {})

        append_log(
            "Runtime startup snapshot refreshed after LLM warmup: "
            f"startup_mode={self._runtime_startup_snapshot.get('startup_mode', '')}, "
            f"premium_ready={bool(self._runtime_startup_snapshot.get('premium_ready', False))}, "
            f"primary_ready={bool(self._runtime_startup_snapshot.get('primary_ready', False))}, "
            f"premium_blockers={list(self._runtime_startup_snapshot.get('premium_blockers', []) or [])}, "
            f"llm_state={self._runtime_startup_snapshot.get('llm_state', '')}, "
            f"llm_available={bool(self._runtime_startup_snapshot.get('llm_available', False))}, "
            f"llm_warmup_ready={bool(self._runtime_startup_snapshot.get('llm_warmup_ready', False))}, "
            f"warmup_attempted={bool(llm_snapshot.get('attempted', False))}, "
            f"warmup_ok={bool(llm_snapshot.get('ok', False))}, "
            f"health_reason={llm_health.get('health_reason', '')}"
        )


    def _start_vision_backend(self) -> None:
        """
        Start the vision backend lifecycle if it exposes a start() hook.
        Never raises — vision failure must not block assistant boot.
        """
        vision = getattr(self, "vision", None)
        if vision is None:
            return

        start_method = getattr(vision, "start", None)
        if not callable(start_method):
            return

        try:
            start_method()
            append_log("Vision backend started.")
        except Exception as error:
            log_exception("Failed to start vision backend during boot", error)

    def _apply_ai_broker_boot_baseline(self) -> None:
        """
        Apply the broker-owned idle baseline after the vision backend starts.

        This makes the broker the central ownership authority from boot onward,
        while keeping the runtime behavior conservative and low-risk.
        """
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return

        enter_method = getattr(broker, "enter_idle_baseline", None)
        if not callable(enter_method):
            return

        try:
            snapshot = enter_method(reason="assistant_boot_idle_baseline")
            if isinstance(snapshot, dict):
                profile = dict(snapshot.get("profile", {}) or {})
                append_log(
                    "AI broker idle baseline applied during boot: "
                    f"mode={snapshot.get('mode', '')}, "
                    f"owner={snapshot.get('owner', '')}, "
                    f"heavy_lane={profile.get('heavy_lane_cadence_hz', '')}"
                )
            else:
                append_log("AI broker idle baseline applied during boot.")
        except Exception as error:
            log_exception("Failed to apply AI broker idle baseline during boot", error)

    def _close_ai_broker(self) -> None:
        """
        Close the AI broker lifecycle if it exposes a close() hook.
        Never raises — shutdown must complete even if broker cleanup fails.
        """
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return

        close_method = getattr(broker, "close", None)
        if not callable(close_method):
            return

        try:
            close_method()
            append_log("AI broker closed.")
        except Exception as error:
            log_exception("Failed to close AI broker during shutdown", error)

    def _close_vision_backend(self) -> None:
        """
        Close the vision backend lifecycle if it exposes a close() hook.
        Never raises — shutdown must complete even if vision cleanup fails.
        """
        vision = getattr(self, "vision", None)
        if vision is None:
            return

        close_method = getattr(vision, "close", None)
        if not callable(close_method):
            return

        try:
            close_method()
            append_log("Vision backend closed.")
        except Exception as error:
            log_exception("Failed to close vision backend during shutdown", error)

    def boot(self) -> None:
        self.shutdown_requested = False


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

        self._start_vision_backend()
        self._apply_ai_broker_boot_baseline()

        self._clear_developer_overlay()
        self.display.show_block(
            self.ASSISTANT_NAME,
            self._runtime_overlay_lines(),
            duration=self.boot_overlay_seconds,
        )
        append_log("Assistant boot sequence started.")

        wake_ack_service = getattr(self, "wake_ack_service", None)
        prefetched_wake_ack_phrases: tuple[str, ...] = tuple()
        if wake_ack_service is not None:
            try:
                prefetched_wake_ack_phrases = tuple(
                    wake_ack_service.prefetch_boot_inventory(languages=("en", "pl"))
                )
            except Exception as error:
                log_exception("Failed to prefetch wake acknowledgement inventory", error)

        if prefetched_wake_ack_phrases:
            append_log(
                "Wake acknowledgement inventory prefetched during boot: "
                f"count={len(prefetched_wake_ack_phrases)}"
            )

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

        snapshot = self._runtime_status_snapshot()
        lifecycle_decision = StartupGateService().decide_post_boot_lifecycle(snapshot)
        self._mark_runtime_state(lifecycle_decision.method_name, lifecycle_decision.reason)

        self.voice_session.set_state(VOICE_STATE_STANDBY, detail="startup_complete")
        self._refresh_developer_overlay(reason="boot")
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

        self._clear_developer_overlay()

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

        self._close_ai_broker()
        self._close_vision_backend()

        self._mark_runtime_state("mark_stopped", "assistant shut down")
        append_log("Assistant shut down.")