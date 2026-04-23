from __future__ import annotations

from typing import Any

from modules.shared.logging.logger import append_log, log_exception


class CoreAssistantAiBrokerMixin:
    """
    Stable assistant-facing wrapper for AI broker mode transitions.

    Dialogue / action / monitoring layers should request policy changes
    through these helpers instead of calling broker internals directly.
    """

    def _apply_ai_broker_transition(
        self,
        *,
        method_name: str,
        reason: str,
        log_label: str,
    ) -> dict[str, Any] | None:
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return None

        method = getattr(broker, method_name, None)
        if not callable(method):
            return None

        try:
            snapshot = method(reason=reason)
            if isinstance(snapshot, dict):
                self._last_ai_broker_snapshot = dict(snapshot)
                profile = dict(snapshot.get("profile", {}) or {})
                append_log(
                    f"AI broker transition applied: "
                    f"label={log_label}, "
                    f"mode={snapshot.get('mode', '')}, "
                    f"owner={snapshot.get('owner', '')}, "
                    f"heavy_lane={profile.get('heavy_lane_cadence_hz', '')}, "
                    f"reason={reason}"
                )
                return self._last_ai_broker_snapshot

            self._last_ai_broker_snapshot = {}
            append_log(
                f"AI broker transition applied without snapshot payload: "
                f"label={log_label}, reason={reason}"
            )
            return None
        except Exception as error:
            log_exception(
                f"Failed to apply AI broker transition: label={log_label}, reason={reason}",
                error,
            )
            return None

    def _enter_ai_broker_idle_baseline(self, *, reason: str = "") -> dict[str, Any] | None:
        return self._apply_ai_broker_transition(
            method_name="enter_idle_baseline",
            reason=reason or "idle_baseline_requested",
            log_label="idle_baseline",
        )

    def _enter_ai_broker_conversation_answer_mode(
        self,
        *,
        reason: str = "",
    ) -> dict[str, Any] | None:
        return self._apply_ai_broker_transition(
            method_name="enter_conversation_answer_mode",
            reason=reason or "conversation_answer_requested",
            log_label="conversation_answer",
        )