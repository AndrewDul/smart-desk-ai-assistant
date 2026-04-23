from __future__ import annotations

from typing import Any

from modules.runtime.ai_broker import AiBrokerMode
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

    def _enter_ai_broker_vision_action_mode(
        self,
        *,
        reason: str = "",
    ) -> dict[str, Any] | None:
        return self._apply_ai_broker_transition(
            method_name="enter_vision_action_mode",
            reason=reason or "vision_action_requested",
            log_label="vision_action",
        )

    def _enter_ai_broker_focus_sentinel_mode(
        self,
        *,
        reason: str = "",
    ) -> dict[str, Any] | None:
        return self._apply_ai_broker_transition(
            method_name="enter_focus_sentinel_mode",
            reason=reason or "focus_sentinel_requested",
            log_label="focus_sentinel",
        )

    def _enter_ai_broker_recovery_window(
        self,
        *,
        reason: str = "",
        return_to_mode: AiBrokerMode | str = AiBrokerMode.IDLE_BASELINE,
        seconds: float | None = None,
    ) -> dict[str, Any] | None:
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return None

        method = getattr(broker, "enter_recovery_window", None)
        if not callable(method):
            return None

        resolved_mode = self._coerce_ai_broker_mode(return_to_mode)
        try:
            snapshot = method(
                reason=reason or "recovery_window_requested",
                return_to_mode=resolved_mode,
                seconds=seconds,
            )
            if isinstance(snapshot, dict):
                self._last_ai_broker_snapshot = dict(snapshot)
                profile = dict(snapshot.get("profile", {}) or {})
                append_log(
                    f"AI broker transition applied: "
                    f"label=recovery_window, "
                    f"mode={snapshot.get('mode', '')}, "
                    f"owner={snapshot.get('owner', '')}, "
                    f"heavy_lane={profile.get('heavy_lane_cadence_hz', '')}, "
                    f"reason={reason or 'recovery_window_requested'}"
                )
                return self._last_ai_broker_snapshot

            self._last_ai_broker_snapshot = {}
            append_log(
                f"AI broker recovery window applied without snapshot payload: "
                f"reason={reason or 'recovery_window_requested'}"
            )
            return None
        except Exception as error:
            log_exception(
                f"Failed to apply AI broker recovery window: reason={reason or 'recovery_window_requested'}",
                error,
            )
            return None

    def _tick_ai_broker(self) -> dict[str, Any] | None:
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return None

        tick_method = getattr(broker, "tick", None)
        if not callable(tick_method):
            return None

        try:
            snapshot = tick_method()
            if isinstance(snapshot, dict):
                self._last_ai_broker_snapshot = dict(snapshot)
                return self._last_ai_broker_snapshot
            return None
        except Exception as error:
            log_exception("Failed to tick AI broker", error)
            return None

    def _ai_broker_status_snapshot(self, *, tick: bool = False) -> dict[str, Any]:
        broker = getattr(self, "ai_broker", None)
        if broker is None:
            return dict(getattr(self, "_last_ai_broker_snapshot", {}) or {})

        if tick:
            self._tick_ai_broker()

        status_method = getattr(broker, "status", None)
        if callable(status_method):
            try:
                snapshot = status_method()
                if isinstance(snapshot, dict):
                    self._last_ai_broker_snapshot = dict(snapshot)
                    return self._last_ai_broker_snapshot
            except Exception as error:
                log_exception("Failed to read AI broker status snapshot", error)

        snapshot_method = getattr(broker, "snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                if isinstance(snapshot, dict):
                    self._last_ai_broker_snapshot = dict(snapshot)
                    return self._last_ai_broker_snapshot
            except Exception as error:
                log_exception("Failed to read AI broker snapshot", error)

        return dict(getattr(self, "_last_ai_broker_snapshot", {}) or {})

    @staticmethod
    def _coerce_ai_broker_mode(value: AiBrokerMode | str) -> AiBrokerMode:
        if isinstance(value, AiBrokerMode):
            return value

        raw = str(value or "").strip().lower()
        for candidate in AiBrokerMode:
            if candidate.value == raw:
                return candidate

        return AiBrokerMode.IDLE_BASELINE