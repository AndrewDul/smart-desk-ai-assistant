from __future__ import annotations


class CompanionDialogueContentHelpersMixin:
    """
    Small helpers for rotating built-in humour, riddles, and facts.
    """

    def _next_humour(self, language: str) -> str:
        bank = self._humour_bank[language]
        text = bank[self._humour_index % len(bank)]
        self._humour_index += 1
        return text

    def _next_riddle(self, language: str) -> str:
        bank = self._riddle_bank[language]
        text = bank[self._riddle_index % len(bank)]
        self._riddle_index += 1
        return text

    def _next_fact(self, language: str) -> str:
        bank = self._fact_bank[language]
        text = bank[self._fact_index % len(bank)]
        self._fact_index += 1
        return text


__all__ = ["CompanionDialogueContentHelpersMixin"]