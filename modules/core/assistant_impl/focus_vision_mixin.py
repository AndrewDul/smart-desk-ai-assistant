from __future__ import annotations

from typing import Any


class CoreAssistantFocusVisionMixin:
    """Small assistant-layer lifecycle bridge for Focus Vision Sentinel."""

    def _bind_focus_vision_reminder_delivery(self) -> dict[str, Any]:
        service = getattr(self, "focus_vision", None)
        if service is None:
            return {"available": False, "bound": False}

        bind_method = getattr(service, "set_reminder_handler", None)
        if not callable(bind_method):
            return {
                "available": True,
                "bound": False,
                "detail": "set_reminder_handler is not available.",
            }

        try:
            bind_method(self._deliver_focus_vision_reminder)
            return {"available": True, "bound": True}
        except Exception as error:
            return {
                "available": True,
                "bound": False,
                "error": f"{error.__class__.__name__}: {error}",
            }

    def _deliver_focus_vision_reminder(self, reminder: Any) -> None:
        language = self._normalize_lang(getattr(reminder, "language", self.last_language))
        spoken_text = str(getattr(reminder, "text", "") or "").strip()
        if not spoken_text:
            return

        kind = getattr(reminder, "kind", "focus_vision")
        kind_value = str(getattr(kind, "value", kind) or "focus_vision")
        snapshot = getattr(reminder, "snapshot", None)
        current_state = getattr(snapshot, "current_state", None)
        state_value = str(getattr(current_state, "value", current_state) or "unknown")
        stable_seconds = float(getattr(snapshot, "stable_seconds", 0.0) or 0.0)

        self._deliver_async_notification(
            lang=language,
            spoken_text=spoken_text,
            display_title="FOCUS",
            display_lines=self._display_lines(spoken_text),
            source="focus_vision_sentinel",
            route_kind="focus_vision_reminder",
            action=f"focus_vision:{kind_value}",
            extra_metadata={
                "focus_vision_kind": kind_value,
                "focus_vision_state": state_value,
                "focus_vision_stable_seconds": stable_seconds,
                "focus_vision_dry_run": bool(getattr(reminder, "dry_run", True)),
            },
        )

    def _start_focus_vision_sentinel(
        self,
        *,
        language: str = "en",
        reason: str = "",
    ) -> dict[str, Any]:
        service = getattr(self, "focus_vision", None)
        if service is None:
            return {
                "available": False,
                "started": False,
                "reason": reason,
                "detail": "Focus Vision Sentinel service is not available.",
            }

        try:
            started = bool(service.start(language=language))
            status_method = getattr(service, "status", None)
            status = status_method() if callable(status_method) else {}
            return {
                "available": True,
                "started": started,
                "reason": reason,
                "status": dict(status or {}),
            }
        except Exception as error:
            return {
                "available": True,
                "started": False,
                "reason": reason,
                "error": f"{error.__class__.__name__}: {error}",
            }

    def _stop_focus_vision_sentinel(self, *, reason: str = "") -> dict[str, Any]:
        service = getattr(self, "focus_vision", None)
        if service is None:
            return {
                "available": False,
                "stopped": False,
                "reason": reason,
                "detail": "Focus Vision Sentinel service is not available.",
            }

        try:
            stop_method = getattr(service, "stop", None)
            if callable(stop_method):
                stop_method()
            status_method = getattr(service, "status", None)
            status = status_method() if callable(status_method) else {}
            return {
                "available": True,
                "stopped": True,
                "reason": reason,
                "status": dict(status or {}),
            }
        except Exception as error:
            return {
                "available": True,
                "stopped": False,
                "reason": reason,
                "error": f"{error.__class__.__name__}: {error}",
            }

    def _focus_vision_status_snapshot(self) -> dict[str, Any]:
        service = getattr(self, "focus_vision", None)
        if service is None:
            return {"available": False}
        status_method = getattr(service, "status", None)
        if not callable(status_method):
            return {"available": True, "status_available": False}
        try:
            return {"available": True, **dict(status_method() or {})}
        except Exception as error:
            return {
                "available": True,
                "status_available": False,
                "error": f"{error.__class__.__name__}: {error}",
            }


__all__ = ["CoreAssistantFocusVisionMixin"]
