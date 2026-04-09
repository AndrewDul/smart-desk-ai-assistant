from __future__ import annotations

import time
from typing import Any, Iterable


class DisplayServiceOverlay:
    """Overlay and status API for the display service."""

    is_color: bool
    _lock: Any
    _overlay_title: str
    _overlay_lines: list[str]
    _overlay_until: float
    _overlay_style: str

    def show_block(self, title: str, lines: Iterable[str], duration: float = 10.0) -> None:
        max_chars = 28 if self.is_color else 20
        max_lines = 7 if self.is_color else 5

        expanded_lines: list[str] = []
        for line in lines:
            expanded_lines.extend(self._wrap_text(str(line), max_chars))

        safe_title = self._trim_text(str(title or ""), max_chars)
        safe_lines = expanded_lines[:max_lines]
        style = "brand" if self._normalize_text(safe_title) == "devdul" else "standard"

        with self._lock:
            self._overlay_title = safe_title
            self._overlay_lines = safe_lines
            self._overlay_until = time.time() + max(float(duration), 0.1)
            self._overlay_style = style

        self._print_block(safe_title, safe_lines)

    def clear_overlay(self) -> None:
        with self._lock:
            self._overlay_until = 0.0
            self._overlay_title = ""
            self._overlay_lines = []
            self._overlay_style = "standard"

    def show_status(
        self,
        state: dict,
        timer_status: dict,
        duration: float = 10.0,
    ) -> None:
        lines = [
            f"focus: {'ON' if state.get('focus_mode') else 'OFF'}",
            f"break: {'ON' if state.get('break_mode') else 'OFF'}",
            f"timer: {state.get('current_timer') or 'none'}",
            f"run: {'ON' if timer_status.get('running') else 'OFF'}",
        ]
        self.show_block("STATUS", lines, duration=duration)


__all__ = ["DisplayServiceOverlay"]