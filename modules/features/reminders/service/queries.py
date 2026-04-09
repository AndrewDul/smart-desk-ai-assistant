from __future__ import annotations

import copy
from difflib import SequenceMatcher
from typing import Any

from .models import ReminderMatch


class ReminderServiceQueries:
    """Read and matching queries for reminders."""

    def list_all(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        reminders.sort(key=self._sort_key)
        return reminders

    def list_pending(self) -> list[dict[str, Any]]:
        return [item for item in self.list_all() if item.get("status") == "pending"]

    def count(self) -> int:
        return len(self._load_reminders())

    def has_any(self) -> bool:
        return bool(self._load_reminders())

    def find_by_id(self, reminder_id: str) -> dict[str, Any] | None:
        clean_id = str(reminder_id or "").strip()
        if not clean_id:
            return None

        for reminder in self._load_reminders():
            if str(reminder.get("id", "")).strip() == clean_id:
                return copy.deepcopy(reminder)
        return None

    def find_by_message(self, query: str) -> dict[str, Any] | None:
        reminders = self._load_reminders()
        if not reminders:
            return None

        match = self.match_by_message(query)
        if match is None:
            return None

        return copy.deepcopy(match.reminder)

    def match_by_message(self, query: str) -> ReminderMatch | None:
        reminders = self._load_reminders()
        if not reminders:
            return None

        query_clean = self._normalize_text(query)
        if not query_clean:
            return None

        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if message == query_clean:
                return ReminderMatch(
                    reminder=copy.deepcopy(reminder),
                    score=1.0,
                    exact=True,
                )

        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if query_clean in message or message in query_clean:
                return ReminderMatch(
                    reminder=copy.deepcopy(reminder),
                    score=0.92,
                    exact=False,
                )

        query_tokens = self._tokenize(query_clean)
        best_match: dict[str, Any] | None = None
        best_score = 0.0

        for reminder in reminders:
            raw_message = str(reminder.get("message", ""))
            normalized_message = self._normalize_text(raw_message)
            message_tokens = self._tokenize(normalized_message)

            overlap_score = self._token_overlap_score(query_tokens, message_tokens)
            similarity_score = SequenceMatcher(None, query_clean, normalized_message).ratio()
            combined_score = max(overlap_score, similarity_score)

            if combined_score > best_score:
                best_score = combined_score
                best_match = reminder

        if best_match is not None and best_score >= 0.58:
            return ReminderMatch(
                reminder=copy.deepcopy(best_match),
                score=best_score,
                exact=False,
            )

        return None


__all__ = ["ReminderServiceQueries"]