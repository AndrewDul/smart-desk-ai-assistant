from __future__ import annotations

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import (
    contains_any_phrase,
    extract_duration_minutes,
)


class IntentParserTimerMixin:
    def _parse_timer(self, normalized: str) -> IntentResult | None:
        if self._looks_like_timer_stop(normalized):
            return IntentResult.from_action(action="timer_stop")

        minutes = self._extract_duration_with_triggers(normalized, self.timer_trigger_phrases)
        if minutes is not None:
            return IntentResult.from_action(
                action="timer_start",
                data={"minutes": minutes},
            )

        if contains_any_phrase(normalized, self.timer_trigger_phrases):
            return IntentResult.from_action(action="timer_start", data={})

        return None

    def _parse_focus_or_break(self, normalized: str) -> IntentResult | None:
        if self._looks_like_focus_stop(normalized) or self._looks_like_break_stop(normalized):
            return IntentResult.from_action(action="timer_stop")

        focus_minutes = self._extract_duration_with_triggers(
            normalized,
            self.focus_trigger_phrases,
        )
        if focus_minutes is not None:
            return IntentResult.from_action(
                action="focus_start",
                data={"minutes": focus_minutes},
            )

        break_minutes = self._extract_duration_with_triggers(
            normalized,
            self.break_trigger_phrases,
        )
        if break_minutes is not None:
            return IntentResult.from_action(
                action="break_start",
                data={"minutes": break_minutes},
            )

        if contains_any_phrase(normalized, self.focus_trigger_phrases):
            return IntentResult.from_action(action="focus_start", data={})

        if contains_any_phrase(normalized, self.break_trigger_phrases):
            return IntentResult.from_action(action="break_start", data={})

        return None

    def _extract_duration_with_triggers(
        self,
        normalized: str,
        triggers: list[str],
    ) -> float | None:
        if not contains_any_phrase(normalized, triggers):
            return None
        return extract_duration_minutes(normalized)

    def _looks_like_timer_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        timer_tokens = {"timer", "timera", "minutnik"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and bool(tokens & timer_tokens)

    def _looks_like_focus_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and ("focus" in tokens or {"tryb", "skupienia"} <= tokens)

    def _looks_like_break_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and (
            "break" in tokens or "przerwe" in tokens or "przerwa" in tokens
        )