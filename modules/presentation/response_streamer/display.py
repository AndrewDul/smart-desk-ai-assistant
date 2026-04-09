from __future__ import annotations

from typing import Any

from modules.runtime.contracts import AssistantChunk, ResponsePlan, clean_response_text

from .helpers import LOGGER, ResponseStreamerHelpers


class ResponseStreamerDisplay(ResponseStreamerHelpers):
    """Display title and line rendering helpers for response streaming."""

    display: Any
    default_display_seconds: float
    max_display_lines: int
    max_display_chars_per_line: int

    def _resolve_display_content(
        self,
        plan: ResponsePlan,
        prepared_chunks: list[AssistantChunk],
    ) -> tuple[str, list[str]]:
        metadata = dict(plan.metadata or {})

        title = clean_response_text(str(metadata.get("display_title", "")).strip())
        if not title:
            title = self._fallback_display_title(plan)

        explicit_lines = metadata.get("display_lines")
        if isinstance(explicit_lines, list):
            cleaned_lines = [
                clean_response_text(str(line))
                for line in explicit_lines
                if clean_response_text(str(line))
            ]
            if cleaned_lines:
                return title, cleaned_lines[: self.max_display_lines]

        generated_lines = self._build_display_lines_from_chunks(prepared_chunks)
        return title, generated_lines

    def _fallback_display_title(self, plan: ResponsePlan) -> str:
        route_kind = self._route_kind_value(plan)

        if route_kind == "action":
            return "ACTION"
        if route_kind == "mixed":
            return "ASSISTANT"
        if route_kind == "conversation":
            return "CHAT"
        if route_kind == "unclear":
            return "UNCLEAR"
        return "NEXA"

    def _build_display_lines_from_chunks(self, chunks: list[AssistantChunk]) -> list[str]:
        if not chunks:
            return []

        text_pool = " ".join(
            clean_response_text(chunk.text)
            for chunk in chunks
            if clean_response_text(chunk.text)
        )
        if not text_pool:
            return []

        candidate_units = self._sentence_units(text_pool)
        if not candidate_units:
            candidate_units = [text_pool]

        lines: list[str] = []
        for unit in candidate_units:
            compact = clean_response_text(unit)
            if not compact:
                continue

            if len(compact) <= self.max_display_chars_per_line:
                lines.append(compact)
            else:
                shortened = compact[: self.max_display_chars_per_line - 3].rstrip() + "..."
                lines.append(shortened)

            if len(lines) >= self.max_display_lines:
                break

        return lines

    def _show_display_block(self, title: str, lines: list[str]) -> bool:
        if not title or not lines:
            return False

        show_block = getattr(self.display, "show_block", None)
        if callable(show_block):
            try:
                show_block(title, lines, duration=self.default_display_seconds)
                return True
            except Exception as error:
                LOGGER.warning("Display show_block failed: %s", error)
                return False

        return False


__all__ = ["ResponseStreamerDisplay"]