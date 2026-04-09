from __future__ import annotations

import math
import re

from .models import DialogueReply


class CompanionDialogueDeterministicMixin:
    """
    Fast deterministic replies that do not require the local LLM.
    """

    def _try_deterministic_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
        topics: list[str],
    ) -> DialogueReply | None:
        del user_profile

        math_reply = self._try_math_reply(normalized_text, language)
        if math_reply is not None:
            return math_reply

        if "low_energy" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Brzmisz na zmęczonego. Mogę pomóc ci wejść w tryb focus albo zaproponować krótką przerwę, jeśli tego potrzebujesz.",
                    "You sound tired. I can help you enter focus mode or suggest a short break if you need it.",
                ),
                follow_up_text=self._text(
                    language,
                    "Jeśli chcesz, mogę uruchomić focus albo krótką przerwę.",
                    "If you want, I can start focus mode or a short break.",
                ),
                suggested_actions=["focus_start", "break_start"],
                display_title=self._text(language, "ENERGIA", "ENERGY"),
                source="template_low_energy",
            )

        if "focus_struggle" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Rozumiem. Gdy trudno się skupić, dobrze zacząć od jednego małego kroku i ograniczyć rozproszenia.",
                    "I understand. When it is hard to focus, it helps to start with one small step and reduce distractions.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus mode albo krótką przerwę, jeśli chcesz.",
                    "I can start focus mode or a short break if you want.",
                ),
                suggested_actions=["focus_start", "break_start"],
                display_title=self._text(language, "SKUPIENIE", "FOCUS"),
                source="template_focus_struggle",
            )

        if "overwhelmed" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Brzmi to jak przeciążenie. Dobrze będzie rozbić to na jeden mały krok i nie próbować ogarniać wszystkiego naraz.",
                    "That sounds like overload. It would help to reduce this to one small step instead of trying to handle everything at once.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus, przerwę albo przypomnienie do konkretnego zadania.",
                    "I can start focus mode, a break, or a reminder for one specific task.",
                ),
                suggested_actions=["focus_start", "break_start", "reminder_create"],
                display_title=self._text(language, "PLAN", "PLAN"),
                source="template_overwhelmed",
            )

        if "study_help" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Jasne. Najlepiej zacząć od jednego konkretnego celu na najbliższe kilkanaście minut.",
                    "Sure. The best start is one clear goal for the next several minutes.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus mode albo przypomnienie do następnego kroku.",
                    "I can start focus mode or create a reminder for the next step.",
                ),
                suggested_actions=["focus_start", "reminder_create"],
                display_title=self._text(language, "NAUKA", "STUDY"),
                source="template_study_help",
            )

        if "encouragement" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Nie musisz zrobić wszystkiego idealnie od razu. Wystarczy, że ruszysz z jednym małym krokiem.",
                    "You do not need to do everything perfectly right away. One small step is enough to begin.",
                ),
                follow_up_text=self._text(
                    language,
                    "Jeśli chcesz, mogę pomóc ci wejść w focus mode.",
                    "If you want, I can help you enter focus mode.",
                ),
                suggested_actions=["focus_start"],
                display_title=self._text(language, "MOTYWACJA", "MOTIVATION"),
                source="template_encouragement",
            )

        if "small_talk" in topics:
            partner_name = self._conversation_partner_name(user_profile, language)
            return self._reply(
                language,
                self._text(
                    language,
                    f"Jasne{partner_name}. Jestem tutaj. Powiedz, co najbardziej siedzi ci teraz w głowie.",
                    f"Of course{partner_name}. I am here. Tell me what is on your mind right now.",
                ),
                display_title=self._text(language, "ROZMOWA", "CHAT"),
                source="template_small_talk",
            )

        return None

    def _try_math_reply(self, normalized_text: str, language: str) -> DialogueReply | None:
        expression = normalized_text.strip()

        replacements = {
            "plus": "+",
            "minus": "-",
            "times": "*",
            "multiplied by": "*",
            "x": "*",
            "divided by": "/",
            "dodac": "+",
            "dodać": "+",
            "razy": "*",
            "podzielic przez": "/",
            "podzielić przez": "/",
        }

        compact = f" {expression} "
        for source, target in replacements.items():
            compact = compact.replace(f" {source} ", f" {target} ")
        compact = " ".join(compact.split()).strip()

        prefixes = (
            "how much is ",
            "ile to jest ",
            "what is ",
            "oblicz ",
            "policz ",
        )
        for prefix in prefixes:
            if compact.startswith(prefix):
                compact = compact[len(prefix) :].strip()
                break

        if not re.fullmatch(r"\d+(?:\.\d+)?\s*[\+\-\*/]\s*\d+(?:\.\d+)?", compact):
            return None

        left, operator, right = re.split(r"\s*([\+\-\*/])\s*", compact)
        a = float(left)
        b = float(right)

        if operator == "+":
            result = a + b
        elif operator == "-":
            result = a - b
        elif operator == "*":
            result = a * b
        else:
            if math.isclose(b, 0.0):
                text = self._text(
                    language,
                    "Nie można dzielić przez zero.",
                    "You cannot divide by zero.",
                )
                return self._reply(
                    language,
                    text,
                    display_title=self._text(language, "MATEMATYKA", "MATH"),
                    source="deterministic_math",
                )
            result = a / b

        pretty_result = self._format_number(result)
        text = self._text(
            language,
            f"Wynik to {pretty_result}.",
            f"The result is {pretty_result}.",
        )
        return self._reply(
            language,
            text,
            display_title=self._text(language, "MATEMATYKA", "MATH"),
            source="deterministic_math",
        )


__all__ = ["CompanionDialogueDeterministicMixin"]