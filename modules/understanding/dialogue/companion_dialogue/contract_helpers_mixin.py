from __future__ import annotations

import math
from typing import Any

from modules.runtime.contracts import ChunkKind, RouteKind, StreamMode


class CompanionDialogueContractHelpersMixin:
    """
    Shared helpers for contract normalization and small text utilities.
    """

    def _resolve_stream_mode(self, raw_value: Any) -> StreamMode:
        normalized = str(raw_value or StreamMode.SENTENCE.value).strip().lower()
        for member in StreamMode:
            if member.value == normalized:
                return member
        return StreamMode.SENTENCE

    def _resolve_route_kind(self, raw_value: str | RouteKind) -> RouteKind:
        if isinstance(raw_value, RouteKind):
            return raw_value

        normalized = str(raw_value or "").strip().lower()
        for member in RouteKind:
            if member.value == normalized:
                return member
        return RouteKind.CONVERSATION

    def _primary_chunk_kind_for_route(self, route_kind: str | RouteKind) -> ChunkKind:
        normalized = self._route_kind_value(route_kind)
        if normalized == RouteKind.UNCLEAR.value:
            return ChunkKind.FOLLOW_UP
        if normalized == RouteKind.MIXED.value:
            return ChunkKind.CONTENT
        if normalized == RouteKind.ACTION.value:
            return ChunkKind.TOOL_STATUS
        return ChunkKind.CONTENT

    @staticmethod
    def _route_kind_value(route_kind: str | RouteKind) -> str:
        if isinstance(route_kind, RouteKind):
            return route_kind.value
        return str(route_kind or "").strip().lower()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized.startswith("pl"):
            return "pl"
        return "en"

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _format_number(value: float) -> str:
        if math.isclose(value, round(value)):
            return str(int(round(value)))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _text(language: str, polish_text: str, english_text: str) -> str:
        return polish_text if language == "pl" else english_text


__all__ = ["CompanionDialogueContractHelpersMixin"]