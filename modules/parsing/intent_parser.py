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

        self.normalized_confirm_yes = {self._normalize_text(item) for item in self.confirm_yes}
        self.normalized_confirm_no = {self._normalize_text(item) for item in self.confirm_no}

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
            "memory_clear": [
                "clear memory",
                "wipe memory",
                "delete all memory",
                "remove all memory",
                "wyczysc pamiec",
                "wyczyść pamięć",
                "usun cala pamiec",
                "usuń całą pamięć",
                "skasuj pamiec",
                "skasuj pamięć",
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
                "zamknij program",
            ],
            "shutdown": [
                "shutdown",
                "power off",
                "turn off system",
                "shut down",
                "wylacz system",
                "wyłącz system",
                "zamknij system",
                "wylacz raspberry pi",
                "wyłącz raspberry pi",
            ],
        }

        self.action_labels = {
            "help": "help / pomoc",
            "status": "status / stan",
            "memory_list": "memory / pamięć",
            "memory_clear": "clear memory / wyczyść pamięć",
            "reminders_list": "reminders / przypomnienia",
            "reminder_delete": "delete reminder / usuń przypomnienie",
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
            "memory_forget": "forget / zapomnij",
            "exit": "exit / wyjście",
            "shutdown": "shutdown / wyłącz system",
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

        self.number_words_en = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
        }

        self.number_words_pl = {
            "zero": 0,
            "jeden": 1,
            "jedna": 1,
            "jedno": 1,
            "dwa": 2,
            "dwie": 2,
            "trzy": 3,
            "cztery": 4,
            "piec": 5,
            "pięć": 5,
            "szesc": 6,
            "sześć": 6,
            "siedem": 7,
            "osiem": 8,
            "dziewiec": 9,
            "dziewięć": 9,
            "dziesiec": 10,
            "dziesięć": 10,
            "jedenascie": 11,
            "jedenaście": 11,
            "dwanascie": 12,
            "dwanaście": 12,
            "trzynascie": 13,
            "trzynaście": 13,
            "czternascie": 14,
            "czternaście": 14,
            "pietnascie": 15,
            "piętnaście": 15,
            "szesnascie": 16,
            "szesnaście": 16,
            "siedemnascie": 17,
            "siedemnaście": 17,
            "osiemnascie": 18,
            "osiemnaście": 18,
            "dziewietnascie": 19,
            "dziewiętnaście": 19,
            "dwadziescia": 20,
            "dwadzieścia": 20,
            "trzydziesci": 30,
            "trzydzieści": 30,
            "czterdziesci": 40,
            "czterdzieści": 40,
            "piecdziesiat": 50,
            "pięćdziesiąt": 50,
            "szescdziesiat": 60,
            "sześćdziesiąt": 60,
        }

        self.duration_units = {
            "second",
            "seconds",
            "sec",
            "sekunda",
            "sekundy",
            "sekund",
            "minute",
            "minutes",
            "min",
            "minuta",
            "minuty",
            "minut",
        }

        self.direct_action_map: dict[str, str] = {}
        for action, phrases in self.action_phrases.items():
            for phrase in phrases:
                self.direct_action_map[self._normalize_text(phrase)] = action

        self.time_ask_set = self._normalize_set(self.time_ask_patterns)
        self.time_show_set = self._normalize_set(self.time_show_patterns)
        self.date_ask_set = self._normalize_set(self.date_ask_patterns)
        self.date_show_set = self._normalize_set(self.date_show_patterns)
        self.day_ask_set = self._normalize_set(self.day_ask_patterns)
        self.day_show_set = self._normalize_set(self.day_show_patterns)
        self.year_ask_set = self._normalize_set(self.year_ask_patterns)
        self.year_show_set = self._normalize_set(self.year_show_patterns)

        self.fuzzy_candidates: list[tuple[str, str]] = []
        for action, phrases in self.action_phrases.items():
            if action in {"exit", "shutdown", "memory_clear"}:
                continue
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

        if normalized in self.normalized_confirm_yes:
            return IntentResult(action="confirm_yes", normalized_text=normalized)

        if normalized in self.normalized_confirm_no:
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

        reminder_delete_result = self._parse_reminder_delete(normalized)
        if reminder_delete_result:
            reminder_delete_result.normalized_text = normalized
            return reminder_delete_result

        reminder_result = self._parse_reminder(normalized)
        if reminder_result:
            reminder_result.normalized_text = normalized
            return reminder_result

        focus_result = self._parse_focus_or_break(normalized)
        if focus_result:
            focus_result.normalized_text = normalized
            return focus_result

        forget_result = self._parse_memory_forget(normalized)
        if forget_result:
            forget_result.normalized_text = normalized
            return forget_result

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
        lowered = lowered.replace("-", " ")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _normalize_set(self, values: list[str]) -> set[str]:
        return {self._normalize_text(value) for value in values}

    def _match_direct_action(self, normalized: str) -> str | None:
        return self.direct_action_map.get(normalized)

    def _parse_temporal_query(self, normalized: str) -> IntentResult | None:
        if normalized in self.time_show_set:
            return IntentResult(action="show_time")
        if normalized in self.time_ask_set:
            return IntentResult(action="ask_time")

        if normalized in self.date_show_set:
            return IntentResult(action="show_date")
        if normalized in self.date_ask_set:
            return IntentResult(action="ask_date")

        if normalized in self.day_show_set:
            return IntentResult(action="show_day")
        if normalized in self.day_ask_set:
            return IntentResult(action="ask_day")

        if normalized in self.year_show_set:
            return IntentResult(action="show_year")
        if normalized in self.year_ask_set:
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
        normalized_triggers = [self._normalize_text(trigger) for trigger in triggers]
        if not any(trigger in normalized for trigger in normalized_triggers):
            return None

        digit_match = re.search(
            r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sec|sekunda|sekundy|sekund|minuta|minuty|minut|minute|minutes|min)?",
            normalized,
        )
        if digit_match:
            value = float(digit_match.group(1).replace(",", "."))
            unit = (digit_match.group(2) or "minutes").strip()
            if unit.startswith("sec") or unit.startswith("sek"):
                return round(value / 60.0, 2)
            return value

        tokens = normalized.split()
        for index, token in enumerate(tokens):
            if token not in self.duration_units:
                continue

            number_value = self._extract_spoken_number_before_index(tokens, index)
            if number_value is None:
                continue

            if token.startswith("sec") or token.startswith("sek"):
                return round(number_value / 60.0, 2)
            return float(number_value)

        return None

    def _extract_spoken_number_before_index(self, tokens: list[str], unit_index: int) -> int | None:
        start = max(0, unit_index - 3)
        candidate_tokens = tokens[start:unit_index]

        if not candidate_tokens:
            return None

        for size in range(min(3, len(candidate_tokens)), 0, -1):
            chunk = candidate_tokens[-size:]
            parsed = self._parse_spoken_number_tokens(chunk)
            if parsed is not None:
                return parsed

        return None

    def _parse_spoken_number_tokens(self, tokens: list[str]) -> int | None:
        if not tokens:
            return None

        if len(tokens) == 1 and tokens[0].isdigit():
            return int(tokens[0])

        total = 0
        for token in tokens:
            if token in self.number_words_en:
                total += self.number_words_en[token]
            elif token in self.number_words_pl:
                total += self.number_words_pl[token]
            else:
                return None

        return total if total > 0 else None

    def _parse_reminder(self, normalized: str) -> IntentResult | None:
        if not any(token in normalized for token in ["remind", "przypomnij"]):
            return None

        patterns = [
            r"^(?:remind(?: me)?)(?: to| about)?\s+(.+?)\s+(?:in|after)\s+(.+?)\s*(second|seconds|sec|minute|minutes|min)$",
            r"^(?:remind(?: me)?)(?: in|after)\s+(.+?)\s*(second|seconds|sec|minute|minutes|min)\s+(?:to|about)?\s+(.+)$",
            r"^(?:przypomnij(?: mi)?)\s+(.+?)\s+za\s+(.+?)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)$",
            r"^(?:przypomnij(?: mi)?)\s+za\s+(.+?)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)\s+(.+)$",
        ]

        for index, pattern in enumerate(patterns):
            match = re.match(pattern, normalized)
            if not match:
                continue

            if index in {0, 2}:
                raw_message = match.group(1).strip()
                amount_text = match.group(2).strip()
                unit = match.group(3)
            else:
                amount_text = match.group(1).strip()
                unit = match.group(2)
                raw_message = match.group(3).strip()

            amount = self._parse_amount_text(amount_text)
            if amount is None or amount <= 0:
                continue

            message = self._cleanup_reminder_message(raw_message)
            if not message:
                return None

            seconds = amount if unit.startswith("sec") or unit.startswith("sek") else amount * 60
            return IntentResult(action="reminder_create", data={"seconds": seconds, "message": message})

        return None

    def _parse_reminder_delete(self, normalized: str) -> IntentResult | None:
        clear_phrases = {
            "clear reminders",
            "delete all reminders",
            "remove all reminders",
            "wyczysc przypomnienia",
            "wyczyść przypomnienia",
            "usun wszystkie przypomnienia",
            "usuń wszystkie przypomnienia",
        }
        if normalized in {self._normalize_text(item) for item in clear_phrases}:
            return IntentResult(action="reminders_clear")

        explicit_id_patterns = [
            r"^(?:delete reminder|remove reminder|cancel reminder)\s+id\s+([a-z0-9]{1,32})$",
            r"^(?:usun przypomnienie|usuń przypomnienie|skasuj przypomnienie)\s+id\s+([a-z0-9]{1,32})$",
        ]
        for pattern in explicit_id_patterns:
            match = re.match(pattern, normalized)
            if not match:
                continue

            reminder_id = match.group(1).strip()
            if reminder_id:
                return IntentResult(action="reminder_delete", data={"id": reminder_id})

        message_patterns = [
            r"^(?:delete reminder|remove reminder|cancel reminder)(?: about)?\s+(.+)$",
            r"^(?:usun przypomnienie|usuń przypomnienie|skasuj przypomnienie)(?: o)?\s+(.+)$",
        ]
        for pattern in message_patterns:
            match = re.match(pattern, normalized)
            if not match:
                continue

            message = self._cleanup_reminder_message(match.group(1))
            if message:
                return IntentResult(action="reminder_delete", data={"message": message})

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

    def _parse_memory_forget(self, normalized: str) -> IntentResult | None:
        forget_patterns = [
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:zapomnij o|usun z pamieci|usuń z pamięci)\s+(.+)$",
        ]

        for pattern in forget_patterns:
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult(action="memory_forget", data={"key": key})

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

    def _parse_amount_text(self, text: str) -> int | None:
        text = text.strip()
        if not text:
            return None

        if re.fullmatch(r"\d+", text):
            return int(text)

        tokens = text.split()
        return self._parse_spoken_number_tokens(tokens)

    def _cleanup_reminder_message(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())

        prefixes = ("about ", "to ", "o ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True

        return cleaned

    def _cleanup_subject(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())

        prefixes = ("my ", "the ", "moje ", "moj ", "moja ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True

        return cleaned

    def _get_fuzzy_suggestions(
        self,
        normalized: str,
        allowed_actions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []

        min_ratio = 0.72
        if len(normalized) <= 5:
            min_ratio = 0.8

        for phrase, action in self.fuzzy_candidates:
            if allowed_actions is not None and action not in allowed_actions:
                continue

            ratio = SequenceMatcher(None, normalized, phrase).ratio()
            if ratio >= min_ratio:
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