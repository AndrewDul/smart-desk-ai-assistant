from __future__ import annotations

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import starts_with_show_intent


class IntentParserTemporalMixin:
    def _parse_temporal_query(self, normalized: str) -> IntentResult | None:
        groups = (
            ("show_time", self.time_show_patterns),
            ("ask_time", self.time_query_patterns),
            ("show_date", self.date_show_patterns),
            ("ask_date", self.date_query_patterns),
            ("show_day", self.day_show_patterns),
            ("ask_day", self.day_query_patterns),
            ("show_month", self.month_show_patterns),
            ("ask_month", self.month_query_patterns),
            ("show_year", self.year_show_patterns),
            ("ask_year", self.year_query_patterns),
        )
        for action, patterns in groups:
            if self._matches_any_pattern(normalized, patterns):
                return IntentResult.from_action(action=action)

        tokens = set(normalized.split())
        if not tokens:
            return None

        if self._looks_like_time_query(tokens):
            return IntentResult.from_action(action="ask_time")
        if self._looks_like_date_query(tokens):
            return IntentResult.from_action(action="ask_date")
        if self._looks_like_day_query(tokens):
            return IntentResult.from_action(action="ask_day")
        if self._looks_like_month_query(tokens):
            return IntentResult.from_action(action="ask_month")
        if self._looks_like_year_query(tokens):
            return IntentResult.from_action(action="ask_year")

        if starts_with_show_intent(normalized):
            if "time" in normalized or "godzin" in normalized or "czas" in normalized:
                return IntentResult.from_action(action="show_time")
            if "date" in normalized or "data" in normalized:
                return IntentResult.from_action(action="show_date")
            if "day" in normalized or "dzien" in normalized:
                return IntentResult.from_action(action="show_day")
            if "month" in normalized or "miesiac" in normalized:
                return IntentResult.from_action(action="show_month")
            if "year" in normalized or "rok" in normalized:
                return IntentResult.from_action(action="show_year")

        return None

    def _looks_like_time_query(self, tokens: set[str]) -> bool:
        if "time" in tokens and "it" in tokens:
            return True
        if {"what", "time"}.issubset(tokens):
            return True
        if {"current", "time"}.issubset(tokens):
            return True
        if {"tell", "time"}.issubset(tokens):
            return True
        if "godzina" in tokens or "godzine" in tokens or "czas" in tokens:
            return True
        if {"ktora", "godzina"}.issubset(tokens):
            return True
        if {"ktora", "jest", "godzina"}.issubset(tokens):
            return True
        return False

    def _looks_like_date_query(self, tokens: set[str]) -> bool:
        if "date" in tokens and ("what" in tokens or "today" in tokens or "current" in tokens):
            return True
        if {"what", "date"}.issubset(tokens):
            return True
        if "data" in tokens:
            return True
        return False

    def _looks_like_day_query(self, tokens: set[str]) -> bool:
        if {"what", "day"}.issubset(tokens):
            return True
        if {"which", "day"}.issubset(tokens):
            return True
        if "dzien" in tokens and ("dzisiaj" in tokens or "jaki" in tokens or "ktory" in tokens):
            return True
        return False

    def _looks_like_month_query(self, tokens: set[str]) -> bool:
        if {"what", "month"}.issubset(tokens):
            return True
        if {"which", "month"}.issubset(tokens):
            return True
        if "miesiac" in tokens:
            return True
        return False

    def _looks_like_year_query(self, tokens: set[str]) -> bool:
        if {"what", "year"}.issubset(tokens):
            return True
        if {"which", "year"}.issubset(tokens):
            return True
        if "rok" in tokens:
            return True
        return False