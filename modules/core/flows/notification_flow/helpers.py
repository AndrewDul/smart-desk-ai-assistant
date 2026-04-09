from __future__ import annotations

from typing import Any


class NotificationFlowHelpers:
    """Small text and display helpers for async notifications."""

    assistant: Any

    def _fallback_display_lines(self, text: str) -> list[str]:
        display_lines_method = getattr(self.assistant, "_display_lines", None)
        if callable(display_lines_method):
            try:
                return list(display_lines_method(text))
            except Exception:
                pass

        compact = self._clean_text(text)
        if not compact:
            return [""]

        max_chars = int(
            getattr(self.assistant, "settings", {})
            .get("streaming", {})
            .get("max_display_chars_per_line", 20)
        )

        if len(compact) <= max_chars:
            return [compact]

        first = compact[:max_chars].rstrip()
        second = compact[max_chars : max_chars * 2].strip()
        return [first, second] if second else [first]

    @staticmethod
    def _clean_text(text: Any) -> str:
        return " ".join(str(text or "").split()).strip()

    def _clean_lines(self, lines: list[Any]) -> list[str]:
        cleaned = [self._clean_text(line) for line in lines]
        cleaned = [line for line in cleaned if line]
        if not cleaned:
            return []

        max_lines = int(
            getattr(self.assistant, "settings", {})
            .get("streaming", {})
            .get("max_display_lines", 2)
        )
        return cleaned[: max(1, max_lines)]


__all__ = ["NotificationFlowHelpers"]