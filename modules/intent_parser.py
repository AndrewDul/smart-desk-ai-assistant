from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


@dataclass
class IntentResult:
    action: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    needs_confirmation: bool = False
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    normalized_text: str = ""


class IntentParser:
    def __init__(self, default_focus_minutes: float = 25, default_break_minutes: float = 5) -> None:
        self.default_focus_minutes = default_focus_minutes
        self.default_break_minutes = default_break_minutes

        self.confirm_yes = {
            "yes", "yeah", "yep", "correct", "tak", "zgadza sie", "zgadza się",
            "dokladnie", "dokładnie", "potwierdzam",
        }
        self.confirm_no = {
            "no", "nope", "nie", "cancel", "anuluj",
        }

        self.action_phrases: dict[str, list[str]] = {
            "help": [
                "help", "show help", "open help", "what can you do", "commands",
                "pomoc", "pokaz pomoc", "pokaż pomoc", "co potrafisz", "komendy",
            ],
            "show_menu": [
                "menu", "show menu", "open menu", "show commands",
                "pokaz menu", "pokaż menu", "otworz menu", "otwórz menu",
                "pokaz komendy", "pokaż komendy",
            ],
            "status": [
                "status", "show status", "system status",
                "stan", "pokaz stan", "pokaż stan", "status systemu",
            ],
            "memory_list": [
                "memory", "show memory", "list memory",
                "pamiec", "pamięć", "pokaz pamiec", "pokaż pamięć", "co pamietasz", "co pamiętasz",
            ],
            "reminders_list": [
                "reminders", "show reminders", "list reminders",
                "przypomnienia", "pokaz przypomnienia", "pokaż przypomnienia",
            ],
            "timer_stop": [
                "stop timer", "stop the timer", "cancel timer",
                "zatrzymaj timer", "stop timera", "anuluj timer",
            ],
            "introduce_self": [
                "introduce yourself",
                "who are you",
                "what are you",
                "tell me about yourself",
                "przedstaw sie",
                "przedstaw się",
                "kim jestes",
                "kim jesteś",
                "powiedz o sobie",
                "jak sie nazywasz",
                "jak się nazywasz",
            ],
            "ask_time": [
                "what time is it",
                "tell me the time",
                "current time",
                "time now",
                "ktora godzina",
                "która godzina",
                "ktora jest godzina",
                "która jest godzina",
                "podaj godzine",
                "podaj godzinę",
                "jaka jest godzina",
            ],
            "exit": [
                "exit", "quit", "close assistant", "exit assistant", "goodbye",
                "wyjdz", "wyjdź", "zamknij asystenta", "wylacz asystenta", "wyłącz asystenta",
            ],
        }

        self.action_labels = {
            "help": "help / pomoc",
            "show_menu": "menu",
            "status": "status / stan",
            "memory_list": "memory / pamięć",
            "reminders_list": "reminders / przypomnienia",
            "timer_stop": "stop timer",
            "introduce_self": "introduce yourself / przedstaw się",
            "ask_time": "time / godzina",
            "exit": "exit / wyjście",
        }

        self.fuzzy_candidates: list[tuple[str, str]] = []
        for action, phrases in self.action_phrases.items():
            for phrase in phrases:
                self.fuzzy_candidates.append((self._normalize_text(phrase), action))

    def parse(self, text: str) -> IntentResult:
        normalized = self._normalize_text(text)
        if not normalized:
            return IntentResult(action="unknown", confidence=0.0, normalized_text=normalized)

        if normalized in {self._normalize_text(item) for item in self.confirm_yes}:
            return IntentResult(action="confirm_yes", normalized_text=normalized)

        if normalized in {self._normalize_text(item) for item in self.confirm_no}:
            return IntentResult(action="confirm_no", normalized_text=normalized)

        direct_action = self._match_direct_action(normalized)
        if direct_action:
            return IntentResult(action=direct_action, normalized_text=normalized)

        reminder_result = self._parse_reminder(normalized)
        if reminder_result:
            reminder_result.normalized_text = normalized
            return reminder_result

        focus_result = self._parse_focus_or_break(normalized)
        if focus_result:
            focus_result.normalized_text = normalized
            return focus_result

        recall_result = self._parse_memory_recall(normalized)
        if recall_result:
            recall_result.normalized_text = normalized
            return recall_result

        remember_result = self._parse_memory_store(normalized)
        if remember_result:
            remember_result.normalized_text = normalized
            return remember_result

        suggestions = self._get_fuzzy_suggestions(normalized)
        if suggestions:
            return IntentResult(
                action="unclear",
                confidence=suggestions[0]["score"],
                needs_confirmation=True,
                suggestions=suggestions,
                normalized_text=normalized,
            )

        return IntentResult(action="unknown", confidence=0.0, normalized_text=normalized)

    def find_action_in_text(self, text: str, allowed_actions: list[str] | None = None) -> str | None:
        normalized = self._normalize_text(text)
        if not normalized:
            return None

        direct_action = self._match_direct_action(normalized)
        if direct_action and (allowed_actions is None or direct_action in allowed_actions):
            return direct_action

        suggestions = self._get_fuzzy_suggestions(normalized, allowed_actions=allowed_actions)
        if suggestions:
            return suggestions[0]["action"]

        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _match_direct_action(self, normalized: str) -> str | None:
        for action, phrases in self.action_phrases.items():
            for phrase in phrases:
                if normalized == self._normalize_text(phrase):
                    return action
        return None

    def _parse_focus_or_break(self, normalized: str) -> IntentResult | None:
        focus_number = self._extract_duration(
            normalized,
            triggers=["focus", "focus mode", "start focus", "skupienie", "tryb skupienia"],
        )
        if focus_number is not None:
            return IntentResult(action="focus_start", data={"minutes": focus_number})

        break_number = self._extract_duration(
            normalized,
            triggers=["break", "start break", "przerwa", "tryb przerwy"],
        )
        if break_number is not None:
            return IntentResult(action="break_start", data={"minutes": break_number})

        if normalized in {"focus", "start focus", "skupienie", "tryb skupienia"}:
            return IntentResult(action="focus_start", data={"minutes": self.default_focus_minutes})

        if normalized in {"break", "start break", "przerwa", "tryb przerwy"}:
            return IntentResult(action="break_start", data={"minutes": self.default_break_minutes})

        return None

    def _extract_duration(self, normalized: str, triggers: list[str]) -> float | None:
        duration_match = re.search(
            r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sekunda|sekundy|sekund|minuta|minuty|minut|minute|minutes)?",
            normalized,
        )
        if not duration_match:
            return None

        trigger_hit = any(trigger in normalized for trigger in triggers)
        if not trigger_hit:
            return None

        value = float(duration_match.group(1).replace(",", "."))
        unit = (duration_match.group(2) or "minutes").strip()

        if unit.startswith("sec") or unit.startswith("sek"):
            return round(value / 60.0, 2)

        return value

    def _parse_reminder(self, normalized: str) -> IntentResult | None:
        if not any(token in normalized for token in ["remind", "przypomnij"]):
            return None

        match = re.search(
            r"(?:remind(?: me)?|przypomnij(?: mi)?)"
            r"(?: in| za)?\s+"
            r"(\d+)\s*"
            r"(seconds?|minutes?|sekunda|sekundy|sekund|minuta|minuty|minut)"
            r"(?:\s+(?:that|to|abym|zebym|zebys|zeby|żebym|żeby))?\s+(.+)$",
            normalized,
        )
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)
        message = match.group(3).strip()

        if not message:
            return None

        if unit.startswith("sec") or unit.startswith("sek"):
            seconds = amount
        else:
            seconds = amount * 60

        return IntentResult(action="reminder_create", data={"seconds": seconds, "message": message})

    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        recall_patterns = [
            r"^(?:where are|where is) (?:my )?(.+)$",
            r"^gdzie (?:sa|jest) (?:moje |moj |moja )?(.+)$",
            r"^recall (.+)$",
            r"^co pamietasz o (.+)$",
            r"^what do you remember about (.+)$",
        ]

        for pattern in recall_patterns:
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult(action="memory_recall", data={"key": key})

        return None

    def _parse_memory_store(self, normalized: str) -> IntentResult | None:
        prefixes = [
            "remember that ", "remember ",
            "zapamietaj ze ", "zapamietaj ",
            "pamietaj ze ", "pamietaj ",
        ]

        candidate = normalized
        for prefix in prefixes:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip()
                break

        relation_patterns = [
            r"^(.+?)\s+(?:is|are|jest|sa)\s+(.+)$",
            r"^(.+?)\s+(?:in|on|at|under|inside|obok|w|na|pod|przy)\s+(.+)$",
        ]

        for pattern in relation_patterns:
            match = re.match(pattern, candidate)
            if match:
                subject = self._cleanup_subject(match.group(1))
                predicate = match.group(2).strip()
                if subject and predicate:
                    return IntentResult(
                        action="memory_store",
                        data={"key": subject, "value": predicate},
                    )

        return None

    def _cleanup_subject(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^(my|moje|moj|moja)\s+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _get_fuzzy_suggestions(
        self,
        normalized: str,
        allowed_actions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []

        for phrase, action in self.fuzzy_candidates:
            if allowed_actions is not None and action not in allowed_actions:
                continue

            ratio = SequenceMatcher(None, normalized, phrase).ratio()
            if ratio >= 0.55:
                scores.append(
                    {
                        "action": action,
                        "label": self.action_labels.get(action, action),
                        "score": round(ratio, 3),
                    }
                )

        unique: dict[str, dict[str, Any]] = {}
        for item in sorted(scores, key=lambda x: x["score"], reverse=True):
            unique.setdefault(item["action"], item)

        return list(unique.values())[:2]