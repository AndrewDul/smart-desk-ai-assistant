from __future__ import annotations

from typing import Any

from .models import DialogueReply


class CompanionDialogueTextHelpersMixin:
    """
    Helpers for building clean dialogue replies and display text.
    """

    def _reply(
        self,
        language: str,
        spoken_text: str,
        *,
        follow_up_text: str = "",
        suggested_actions: list[str] | None = None,
        display_title: str = "",
        display_lines: list[str] | None = None,
        source: str = "template",
    ) -> DialogueReply:
        cleaned_spoken = self._clean_text(spoken_text)
        cleaned_follow_up = self._clean_text(follow_up_text)

        lines = list(display_lines or [])
        if not lines and cleaned_spoken:
            lines = self._default_display_lines(cleaned_spoken)

        return DialogueReply(
            language=self._normalize_language(language),
            spoken_text=cleaned_spoken,
            follow_up_text=cleaned_follow_up,
            suggested_actions=list(suggested_actions or []),
            display_title=self._clean_text(display_title),
            display_lines=lines,
            source=source,
        )

    def _default_display_lines(self, text: str) -> list[str]:
        compact = self._clean_text(text)
        if not compact:
            return []

        max_chars = int(
            self.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )
        if len(compact) <= max_chars:
            return [compact]

        first = compact[:max_chars].rstrip()
        second = compact[max_chars : max_chars * 2].strip()
        if second:
            return [first, second[:max_chars]]
        return [first]

    def _conversation_partner_name(
        self,
        user_profile: dict[str, Any] | None,
        language: str,
    ) -> str:
        profile = dict(user_profile or {})
        partner = str(profile.get("conversation_partner_name", "")).strip()
        if not partner:
            return ""
        return f", {partner}," if language == "en" else f", {partner},"

    def _human_action_name(self, action: str, language: str) -> str:
        mapping = {
            "focus_start": self._text(language, "uruchomienie focus mode", "starting focus mode"),
            "break_start": self._text(language, "uruchomienie przerwy", "starting a break"),
            "reminder_create": self._text(language, "ustawienie przypomnienia", "setting a reminder"),
            "memory_store": self._text(language, "zapamiętanie informacji", "remembering information"),
            "timer_start": self._text(language, "ustawienie timera", "setting a timer"),
        }
        return mapping.get(action, "")

    def _join_human_list(self, items: list[str], language: str) -> str:
        clean_items = [self._clean_text(item) for item in items if self._clean_text(item)]
        if not clean_items:
            return ""

        if len(clean_items) == 1:
            return clean_items[0]
        if len(clean_items) == 2:
            joiner = " i " if language == "pl" else " and "
            return f"{clean_items[0]}{joiner}{clean_items[1]}"

        joiner = ", "
        tail = " i " if language == "pl" else " and "
        return f"{joiner.join(clean_items[:-1])}{tail}{clean_items[-1]}"


__all__ = ["CompanionDialogueTextHelpersMixin"]