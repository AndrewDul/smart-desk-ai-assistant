from __future__ import annotations

import re
import unicodedata
from typing import Any


class ReminderServiceHelpers:
    """Small shared helper methods for reminder persistence and matching."""

    @staticmethod
    def _sort_key(reminder: dict[str, Any]) -> tuple[int, str]:
        status = str(reminder.get("status", "pending"))
        due_at = str(reminder.get("due_at", ""))
        return (0 if status == "pending" else 1, due_at)

    @staticmethod
    def _clean_message(message: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(message or "").strip())

        prefixes = ("about ", "to ", "o ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True

        return cleaned

    @staticmethod
    def _normalize_status(status: Any) -> str:
        normalized = str(status or "pending").strip().lower()
        if normalized not in {"pending", "done"}:
            return "pending"
        return normalized

    @staticmethod
    def _normalize_language(language: Any) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.split() if token]

    @staticmethod
    def _token_overlap_score(left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0

        left_set = set(left_tokens)
        right_set = set(right_tokens)
        common = left_set & right_set

        if not common:
            return 0.0

        return float(len(common) / max(len(left_set), len(right_set)))

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["ReminderServiceHelpers"]