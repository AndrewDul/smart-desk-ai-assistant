from __future__ import annotations

from typing import Callable


class BaseActionResponseBuilder:
    def __init__(
        self,
        *,
        localize_text: Callable[[str, str, str], str],
        localize_lines: Callable[[str, list[str], list[str]], list[str]],
        display_lines: Callable[[str], list[str]],
        trim_text: Callable[[str, int], str],
        duration_text: Callable[[int, str], str],
    ) -> None:
        self._localize_text = localize_text
        self._localize_lines = localize_lines
        self._display_lines = display_lines
        self._trim_text = trim_text
        self._duration_text = duration_text

    def localized(self, language: str, polish_text: str, english_text: str) -> str:
        return self._localize_text(language, polish_text, english_text)

    def localized_lines(self, language: str, polish_lines: list[str], english_lines: list[str]) -> list[str]:
        return self._localize_lines(language, polish_lines, english_lines)

    def display_lines(self, text: str) -> list[str]:
        return self._display_lines(text)

    def trim_text(self, text: str, max_len: int) -> str:
        return self._trim_text(text, max_len)

    def duration_text(self, seconds: int, language: str) -> str:
        return self._duration_text(seconds, language)