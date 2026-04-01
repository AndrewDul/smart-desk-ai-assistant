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
            "yes",
            "yeah",
            "yep",
            "correct",
            "show it",
            "display it",
            "tak",
            "zgadza sie",
            "zgadza się",
            "dokladnie",
            "dokładnie",
            "potwierdzam",
            "pokaz",
            "pokaż",
            "wyswietl",
            "wyświetl",
        }
        self.confirm_no = {
            "no",
            "nope",
            "cancel",
            "dont show it",
            "do not show it",
            "nie",
            "anuluj",
            "nie pokazuj",
            "nie wyswietlaj",
            "nie wyświetlaj",
        }

        self.action_phrases: dict[str, list[str]] = {
            "help": [
                "help",
                "show help",
                "open help",
                "what can you do",
                "how can you help me",
                "what can you help me with",
                "tell me how you can help",
                "commands",
                "pomoc",
                "pokaz pomoc",
                "pokaż pomoc",
                "co potrafisz",
                "jak mozesz mi pomoc",
                "jak możesz mi pomóc",
                "w czym mozesz pomoc",
                "w czym możesz pomóc",
                "komendy",
            ],
            "status": [
                "status",
                "show status",
                "system status",
                "stan",
                "pokaz stan",
                "pokaż stan",
                "status systemu",
            ],
            "memory_list": [
                "memory",
                "show memory",
                "list memory",
                "what do you remember",
                "pamiec",
                "pamięć",
                "pokaz pamiec",
                "pokaż pamięć",
                "co pamietasz",
                "co pamiętasz",
            ],
            "reminders_list": [
                "reminders",
                "show reminders",
                "list reminders",
                "przypomnienia",
                "pokaz przypomnienia",
                "pokaż przypomnienia",
            ],
            "timer_stop": [
                "stop timer",
                "stop the timer",
                "cancel timer",
                "stop focus",
                "focus off",
                "turn off focus",
                "stop break",
                "break off",
                "end work",
                "finish work",
                "i am not studying now",
                "zatrzymaj timer",
                "stop timera",
                "anuluj timer",
                "wylacz timer",
                "wyłącz timer",
                "wylacz focus",
                "wyłącz focus",
                "focus off",
                "koniec pracy",
                "nie ucze sie teraz",
                "nie uczę się teraz",
                "wylacz przerwe",
                "wyłącz przerwę",
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
            "exit": [
                "exit",
                "quit",
                "close assistant",
                "exit assistant",
                "goodbye",
                "wyjdz",
                "wyjdź",
                "zamknij asystenta",
                "wylacz asystenta",
                "wyłącz asystenta",
            ],
        }

        self.action_labels = {
            "help": "help / pomoc",
            "status": "status / stan",
            "memory_list": "memory / pamięć",
            "reminders_list": "reminders / przypomnienia",
            "timer_stop": "stop timer / wyłącz timer",
            "introduce_self": "introduce yourself / przedstaw się",
            "ask_time": "time / godzina",
            "show_time": "show time / pokaż godzinę",
            "ask_date": "date / data",
            "show_date": "show date / pokaż datę",
            "ask_day": "day / dzień",
            "show_day": "show day / pokaż dzień",
            "ask_year": "year / rok",
            "show_year": "show year / pokaż rok",
            "timer_start": "start timer / ustaw timer",
            "focus_start": "focus mode / focus mode",
            "break_start": "break mode / tryb przerwy",
            "memory_store": "remember / zapamiętaj",
            "memory_recall": "recall / przypomnij sobie",
            "exit": "exit / wyjście",
        }

        self.time_ask_patterns = [
            "what time is it",
            "tell me the time",
            "current time",
            "time now",
            "ktora godzina",
            "ktora jest godzina",
            "podaj godzine",
            "jaka jest godzina",
            "jaki jest czas",
        ]
        self.time_show_patterns = [
            "show time",
            "display time",
            "show the time",
            "display the time",
            "pokaz godzine",
            "pokaż godzinę",
            "wyswietl godzine",
            "wyświetl godzinę",
            "pokaz czas",
            "pokaż czas",
        ]

        self.date_ask_patterns = [
            "what date is it",
            "what is the date",
            "tell me the date",
            "jaka jest data",
            "podaj date",
        ]
        self.date_show_patterns = [
            "show date",
            "display date",
            "pokaz date",
            "pokaż datę",
            "wyswietl date",
            "wyświetl datę",
        ]

        self.day_ask_patterns = [
            "what day is it",
            "what day is today",
            "tell me the day",
            "jaki jest dzisiaj dzien",
            "jaki mamy dzisiaj dzien",
            "ktory dzien mamy dzisiaj",
            "podaj dzien",
        ]
        self.day_show_patterns = [
            "show day",
            "display day",
            "pokaz dzien",
            "pokaż dzień",
            "wyswietl dzien",
            "wyświetl dzień",
        ]

        self.year_ask_patterns = [
            "what year is it",
            "tell me the year",
            "jaki jest rok",
            "ktory mamy rok",
            "podaj rok",
        ]
        self.year_show_patterns = [
            "show year",
            "display year",
            "pokaz rok",
            "pokaż rok",
            "wyswietl rok",
            "wyświetl rok",
        ]

        self.fuzzy_candidates: list[tuple[str, str]] = []
        for action, phrases in self.action_phrases.items():
            for phrase in phrases:
                self.fuzzy_candidates.append((self._normalize_text(phrase), action))

        for action, phrases in {
            "ask_time": self.time_ask_patterns,
            "show_time": self.time_show_patterns,
            "ask_date": self.date_ask_patterns,
            "show_date": self.date_show_patterns,
            "ask_day": self.day_ask_patterns,
            "show_day": self.day_show_patterns,
            "ask_year": self.year_ask_patterns,
            "show_year": self.year_show_patterns,
        }.items():
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

        timer_result = self._parse_timer(normalized)
        if timer_result:
            timer_result.normalized_text = normalized
            return timer_result

        temporal_result = self._parse_temporal_query(normalized)
        if temporal_result:
            temporal_result.normalized_text = normalized
            return temporal_result

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

        timer_result = self._parse_timer(normalized)
        if timer_result and (allowed_actions is None or timer_result.action in allowed_actions):
            return timer_result.action

        temporal_result = self._parse_temporal_query(normalized)
        if temporal_result and (allowed_actions is None or temporal_result.action in allowed_actions):
            return temporal_result.action

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

    def _parse_temporal_query(self, normalized: str) -> IntentResult | None:
        if self._matches_any(normalized, self.time_show_patterns):
            return IntentResult(action="show_time")
        if self._matches_any(normalized, self.time_ask_patterns):
            return IntentResult(action="ask_time")

        if self._matches_any(normalized, self.date_show_patterns):
            return IntentResult(action="show_date")
        if self._matches_any(normalized, self.date_ask_patterns):
            return IntentResult(action="ask_date")

        if self._matches_any(normalized, self.day_show_patterns):
            return IntentResult(action="show_day")
        if self._matches_any(normalized, self.day_ask_patterns):
            return IntentResult(action="ask_day")

        if self._matches_any(normalized, self.year_show_patterns):
            return IntentResult(action="show_year")
        if self._matches_any(normalized, self.year_ask_patterns):
            return IntentResult(action="ask_year")

        return None

    def _parse_timer(self, normalized: str) -> IntentResult | None:
        timer_triggers = [
            "timer",
            "set timer",
            "start timer",
            "ustaw timer",
            "wlacz timer",
            "włącz timer",
            "uruchom timer",
            "minutnik",
        ]
        minutes = self._extract_duration(normalized, triggers=timer_triggers)
        if minutes is not None:
            return IntentResult(action="timer_start", data={"minutes": minutes})

        if normalized in {"timer", "set timer", "start timer", "ustaw timer", "uruchom timer", "minutnik"}:
            return IntentResult(action="timer_start", data={})

        return None

    def _parse_focus_or_break(self, normalized: str) -> IntentResult | None:
        focus_number = self._extract_duration(
            normalized,
            triggers=["focus", "focus mode", "start focus", "skupienie", "tryb skupienia", "sesja nauki"],
        )
        if focus_number is not None:
            return IntentResult(action="focus_start", data={"minutes": focus_number})

        break_number = self._extract_duration(
            normalized,
            triggers=["break", "start break", "przerwa", "tryb przerwy", "session break"],
        )
        if break_number is not None:
            return IntentResult(action="break_start", data={"minutes": break_number})

        if normalized in {"focus", "focus mode", "start focus", "skupienie", "tryb skupienia", "sesja nauki"}:
            return IntentResult(action="focus_start", data={})

        if normalized in {"break", "start break", "przerwa", "tryb przerwy"}:
            return IntentResult(action="break_start", data={})

        return None

    def _extract_duration(self, normalized: str, triggers: list[str]) -> float | None:
        duration_match = re.search(
            r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sec|sekunda|sekundy|sekund|minuta|minuty|minut|minute|minutes|min)?",
            normalized,
        )
        if not duration_match:
            return None

        if not any(trigger in normalized for trigger in triggers):
            return None

        value = float(duration_match.group(1).replace(",", "."))
        unit = (duration_match.group(2) or "minutes").strip()

        if unit.startswith("sec") or unit.startswith("sek"):
            return round(value / 60.0, 2)

        return value

    def _parse_reminder(self, normalized: str) -> IntentResult | None:
        if not any(token in normalized for token in ["remind", "przypomnij"]):
            return None

        patterns = [
            r"^(?:remind(?: me)?)(?: to| about)?\s+(.+?)\s+(?:in|after)\s+(\d+)\s*(seconds?|minutes?)$",
            r"^(?:remind(?: me)?)(?: in|after)\s+(\d+)\s*(seconds?|minutes?)\s+(?:to|about)?\s+(.+)$",
            r"^(?:przypomnij(?: mi)?)\s+(.+?)\s+za\s+(\d+)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)$",
            r"^(?:przypomnij(?: mi)?)\s+za\s+(\d+)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)\s+(.+)$",
        ]

        for index, pattern in enumerate(patterns):
            match = re.match(pattern, normalized)
            if not match:
                continue

            if index in {0, 2}:
                message = match.group(1).strip()
                amount = int(match.group(2))
                unit = match.group(3)
            else:
                amount = int(match.group(1))
                unit = match.group(2)
                message = match.group(3).strip()

            if not message:
                return None

            seconds = amount if unit.startswith("sec") or unit.startswith("sek") else amount * 60
            return IntentResult(action="reminder_create", data={"seconds": seconds, "message": message})

        return None

    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        recall_patterns = [
            r"^(?:where are|where is) (?:my )?(.+)$",
            r"^where did i put (?:my )?(.+)$",
            r"^what do you remember about (.+)$",
            r"^do you remember (.+)$",
            r"^recall (.+)$",
            r"^gdzie (?:sa|jest) (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylem (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylam (?:moje |moj |moja )?(.+)$",
            r"^co pamietasz o (.+)$",
            r"^czy pamietasz (.+)$",
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
            "remember that ",
            "remember ",
            "zapamietaj ze ",
            "zapamietaj ",
            "pamietaj ze ",
            "pamietaj ",
        ]

        candidate = normalized
        matched_prefix = False

        for prefix in prefixes:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip()
                matched_prefix = True
                break

        if not matched_prefix or not candidate:
            return None

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
                        data={
                            "key": subject,
                            "value": predicate,
                            "memory_text": candidate,
                        },
                    )

        return IntentResult(action="memory_store", data={"memory_text": candidate})

    def _cleanup_subject(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^(my|moje|moj|moja)\s+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _matches_any(self, normalized: str, patterns: list[str]) -> bool:
        normalized_patterns = {self._normalize_text(item) for item in patterns}
        return normalized in normalized_patterns

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