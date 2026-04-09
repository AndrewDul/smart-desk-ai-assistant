from __future__ import annotations

from typing import Any

from .models import DialogueReply


class CompanionDialogueTemplatesMixin:
    """
    Template-based dialogue replies for conversation, mixed, unclear,
    and action-bridge flows.
    """

    def _build_conversation_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
        topics: list[str],
    ) -> DialogueReply:
        del topics

        partner_name = self._conversation_partner_name(user_profile, language)

        if normalized_text:
            if language == "pl":
                spoken = (
                    f"Rozumiem{partner_name}. "
                    "Powiedz mi trochę więcej, a postaram się odpowiedzieć jak najbardziej konkretnie."
                )
            else:
                spoken = (
                    f"I understand{partner_name}. "
                    "Tell me a little more, and I will try to respond as clearly as I can."
                )
        else:
            spoken = self._text(
                language,
                "Jestem tutaj. Powiedz, o czym chcesz porozmawiać.",
                "I am here. Tell me what you want to talk about.",
            )

        return self._reply(
            language,
            spoken,
            display_title=self._text(language, "ROZMOWA", "CHAT"),
            source="template_conversation",
        )

    def _build_mixed_reply(
        self,
        *,
        route: Any,
        language: str,
        user_profile: dict | None,
        topics: list[str],
        suggested_actions: list[str],
    ) -> DialogueReply:
        del route, user_profile, topics

        human_action_names = [self._human_action_name(item, language) for item in suggested_actions]
        human_action_names = [item for item in human_action_names if item]

        if human_action_names:
            joined = self._join_human_list(human_action_names, language)
            spoken = self._text(
                language,
                f"Rozumiem. Mogę pomóc ci praktycznie — na przykład przez {joined}.",
                f"I understand. I can help in a practical way — for example by {joined}.",
            )
            follow_up = self._text(
                language,
                "Powiedz tylko, od czego chcesz zacząć.",
                "Just tell me what you want to start with.",
            )
        else:
            spoken = self._text(
                language,
                "Rozumiem. Brzmi to jak coś, przy czym mogę pomóc praktycznie.",
                "I understand. This sounds like something I can help with practically.",
            )
            follow_up = self._text(
                language,
                "Powiedz mi, co mam zrobić jako pierwszy krok.",
                "Tell me what you want me to do as the first step.",
            )

        return self._reply(
            language,
            spoken,
            follow_up_text=follow_up,
            suggested_actions=suggested_actions,
            display_title=self._text(language, "POMOC", "SUPPORT"),
            source="template_mixed",
        )

    def _build_unclear_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        del user_profile

        if normalized_text and len(normalized_text.split()) <= 3:
            return self._reply(
                language,
                self._text(
                    language,
                    "Nie złapałam jeszcze dokładnie sensu tej komendy. Powiedz to trochę pełniej.",
                    "I did not catch the meaning of that command yet. Say it a little more fully.",
                ),
                display_title=self._text(language, "NIEJASNE", "UNCLEAR"),
                source="template_unclear_short",
            )

        return None

    def _build_unclear_generic_reply(self, language: str) -> DialogueReply:
        return self._reply(
            language,
            self._text(
                language,
                "Nie złapałam jeszcze dokładnie, o co chodzi. Powiedz to jeszcze raz trochę inaczej.",
                "I did not catch exactly what you meant yet. Say it again a little differently.",
            ),
            display_title=self._text(language, "NIEJASNE", "UNCLEAR"),
            source="template_unclear_generic",
        )

    def _build_action_bridge_reply(self, *, language: str) -> DialogueReply:
        return self._reply(
            language,
            self._text(
                language,
                "Rozumiem. Powiedz mi proszę jeszcze raz, co dokładnie mam zrobić.",
                "Understood. Please tell me again exactly what you want me to do.",
            ),
            display_title=self._text(language, "AKCJA", "ACTION"),
            source="template_action_bridge",
        )


__all__ = ["CompanionDialogueTemplatesMixin"]