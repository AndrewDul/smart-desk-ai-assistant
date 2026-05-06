from __future__ import annotations

from typing import Any


class CoreAssistantFocusVisionMixin:
    """Small assistant-layer lifecycle bridge for Focus Vision Sentinel."""

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
