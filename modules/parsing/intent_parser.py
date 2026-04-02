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
            "sure",
            "of course",
            "correct",
            "do it",
            "show it",
            "display it",
            "tak",
            "jasne",
            "pewnie",
            "dokladnie",
            "dokładnie",
            "zgadza sie",
            "zgadza się",
            "potwierdzam",
            "zrob to",
            "zrób to",
            "pokaz",
            "pokaż",
            "wyswietl",
            "wyświetl",
        }
        self.confirm_no = {
            "no",
            "nope",
            "cancel",
            "stop",
            "leave it",
            "do not",
            "do not show it",
            "dont show it",
            "never mind",
            "nie",
            "nie teraz",
            "anuluj",
            "zostaw to",
            "niewazne",
            "nieważne",
            "nie pokazuj",
            "nie wyswietlaj",
            "nie wyświetlaj",
        }
        self.normalized_confirm_yes = {self._normalize_text(item) for item in self.confirm_yes}
        self.normalized_confirm_no = {self._normalize_text(item) for item in self.confirm_no}

        self.time_query_patterns = [
            r"\bwhat(?:'s| is)? the time\b",
            r"\bwhat time is it\b",
            r"\btell me the time\b",
            r"\bcurrent time\b",
            r"\btime now\b",
            r"\bktora jest godzina\b",
            r"\bktora godzina\b",
            r"\bjaka jest godzina\b",
            r"\bpodaj godzine\b",
            r"\bjaki jest czas\b",
        ]
        self.time_show_patterns = [
            r"\bshow(?: me)? the time\b",
            r"\bdisplay(?: me)? the time\b",
            r"\bshow time\b",
            r"\bdisplay time\b",
            r"\bpokaz godzine\b",
            r"\bpokaż godzinę\b",
            r"\bwyswietl godzine\b",
            r"\bwyświetl godzinę\b",
            r"\bpokaz czas\b",
            r"\bpokaż czas\b",
        ]

        self.date_query_patterns = [
            r"\bwhat(?:'s| is)? the date\b",
            r"\bwhat date is it\b",
            r"\btell me the date\b",
            r"\bjaka jest data\b",
            r"\bpodaj date\b",
        ]
        self.date_show_patterns = [
            r"\bshow(?: me)? the date\b",
            r"\bdisplay(?: me)? the date\b",
            r"\bshow date\b",
            r"\bdisplay date\b",
            r"\bpokaz date\b",
            r"\bpokaż datę\b",
            r"\bwyswietl date\b",
            r"\bwyświetl datę\b",
        ]

        self.day_query_patterns = [
            r"\bwhat day is it\b",
            r"\bwhat day is today\b",
            r"\btell me the day\b",
            r"\bjaki jest dzisiaj dzien\b",
            r"\bjaki mamy dzisiaj dzien\b",
            r"\bktory dzien mamy dzisiaj\b",
            r"\bpodaj dzien\b",
        ]
        self.day_show_patterns = [
            r"\bshow(?: me)? the day\b",
            r"\bdisplay(?: me)? the day\b",
            r"\bshow day\b",
            r"\bdisplay day\b",
            r"\bpokaz dzien\b",
            r"\bpokaż dzień\b",
            r"\bwyswietl dzien\b",
            r"\bwyświetl dzień\b",
        ]

        self.year_query_patterns = [
            r"\bwhat year is it\b",
            r"\btell me the year\b",
            r"\bjaki jest rok\b",
            r"\bktory mamy rok\b",
            r"\bpodaj rok\b",
        ]
        self.year_show_patterns = [
            r"\bshow(?: me)? the year\b",
            r"\bdisplay(?: me)? the year\b",
            r"\bshow year\b",
            r"\bdisplay year\b",
            r"\bpokaz rok\b",
            r"\bpokaż rok\b",
            r"\bwyswietl rok\b",
            r"\bwyświetl rok\b",
        ]

        self.direct_action_phrases: dict[str, list[str]] = {
            "help": [
                "help",
                "show help",
                "open help",
                "show menu",
                "open menu",
                "assistant menu",
                "what can you do",
                "what do you do",
                "how can you help me",
                "what can you help me with",
                "tell me how you can help",
                "what can i ask you",
                "how do you help me",
                "list your features",
                "list your functions",
                "show capabilities",
                "assistant capabilities",
                "i need help",
                "i need assistance",
                "pomoc",
                "pokaz pomoc",
                "pokaż pomoc",
                "pokaz menu",
                "pokaż menu",
                "menu asystenta",
                "co potrafisz",
                "co umiesz",
                "jak mozesz mi pomoc",
                "jak możesz mi pomóc",
                "w czym mozesz mi pomoc",
                "w czym możesz mi pomóc",
                "powiedz co potrafisz",
                "pokaz mozliwosci",
                "pokaż możliwości",
                "komendy",
            ],
            "status": [
                "status",
                "show status",
                "assistant status",
                "system status",
                "device status",
                "show assistant status",
                "stan",
                "pokaz stan",
                "pokaż stan",
                "status systemu",
                "stan systemu",
            ],
            "memory_list": [
                "memory",
                "show memory",
                "list memory",
                "what do you remember",
                "show what you remember",
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
                "forget everything",
                "wyczysc pamiec",
                "wyczyść pamięć",
                "usun cala pamiec",
                "usuń całą pamięć",
                "zapomnij wszystko",
                "skasuj pamiec",
                "skasuj pamięć",
            ],
            "reminders_list": [
                "reminders",
                "show reminders",
                "list reminders",
                "show my reminders",
                "przypomnienia",
                "pokaz przypomnienia",
                "pokaż przypomnienia",
                "pokaz moje przypomnienia",
                "pokaż moje przypomnienia",
            ],
            "timer_stop": [
                "stop timer",
                "stop the timer",
                "cancel timer",
                "end timer",
                "turn off timer",
                "stop focus",
                "stop focus mode",
                "end focus",
                "end focus session",
                "turn off focus",
                "stop break",
                "stop break mode",
                "end break",
                "end break mode",
                "zatrzymaj timer",
                "stop timera",
                "anuluj timer",
                "wylacz timer",
                "wyłącz timer",
                "zatrzymaj focus",
                "wylacz focus",
                "wyłącz focus",
                "zakoncz focus",
                "zakończ focus",
                "zatrzymaj przerwe",
                "zatrzymaj przerwę",
                "wylacz przerwe",
                "wyłącz przerwę",
                "zakoncz przerwe",
                "zakończ przerwę",
            ],
            "introduce_self": [
                "who are you",
                "what are you",
                "what is your name",
                "what's your name",
                "tell me your name",
                "say your name",
                "introduce yourself",
                "tell me about yourself",
                "przedstaw sie",
                "przedstaw się",
                "kim jestes",
                "kim jesteś",
                "jak sie nazywasz",
                "jak się nazywasz",
                "powiedz jak sie nazywasz",
                "powiedz jak się nazywasz",
                "powiedz o sobie",
            ],
            "exit": [
                "exit",
                "quit",
                "close assistant",
                "exit assistant",
                "turn off assistant",
                "switch off assistant",
                "stop assistant",
                "stop listening",
                "go to sleep",
                "sleep now",
                "rest now",
                "take a rest",
                "goodbye",
                "bye",
                "bye bye",
                "wylacz asystenta",
                "wyłącz asystenta",
                "zamknij asystenta",
                "idz spac",
                "idź spać",
                "spij",
                "śpij",
                "odpocznij",
                "przestan sluchac",
                "przestań słuchać",
            ],
            "shutdown": [
                "shutdown",
                "shut down",
                "power off",
                "power off system",
                "turn off system",
                "turn off raspberry pi",
                "power off raspberry pi",
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
            "reminders_clear": "clear reminders / wyczyść przypomnienia",
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
        self.timer_trigger_phrases = [
            "timer",
            "set timer",
            "start timer",
            "countdown",
            "ustaw timer",
            "wlacz timer",
            "włącz timer",
            "uruchom timer",
            "minutnik",
        ]
        self.focus_trigger_phrases = [
            "focus",
            "focus mode",
            "focus session",
            "start focus",
            "start focus mode",
            "study session",
            "skupienie",
            "tryb skupienia",
            "sesja focus",
            "sesja nauki",
            "zacznij focus",
            "wlacz focus",
            "włącz focus",
        ]
        self.break_trigger_phrases = [
            "break",
            "break mode",
            "start break",
            "start break mode",
            "take a break",
            "przerwa",
            "tryb przerwy",
            "zacznij przerwe",
            "zacznij przerwę",
            "wlacz przerwe",
            "włącz przerwę",
        ]

        self.direct_action_map: dict[str, str] = {}
        self.fuzzy_candidates: list[tuple[str, str, set[str]]] = []
        for action, phrases in self.direct_action_phrases.items():
            for phrase in phrases:
                normalized_phrase = self._normalize_text(phrase)
                self.direct_action_map[normalized_phrase] = action
                if action not in {"exit", "shutdown", "memory_clear"}:
                    self.fuzzy_candidates.append((normalized_phrase, action, set(normalized_phrase.split())))

        for action, patterns in {
            "ask_time": self.time_query_patterns,
            "show_time": self.time_show_patterns,
            "ask_date": self.date_query_patterns,
            "show_date": self.date_show_patterns,
            "ask_day": self.day_query_patterns,
            "show_day": self.day_show_patterns,
            "ask_year": self.year_query_patterns,
            "show_year": self.year_show_patterns,
        }.items():
            for pattern in patterns:
                plain = pattern.replace(r"\b", "").replace("(?:'s| is)?", "").strip()
                normalized_phrase = self._normalize_text(plain)
                if normalized_phrase:
                    self.fuzzy_candidates.append((normalized_phrase, action, set(normalized_phrase.split())))

    def parse(self, text: str) -> IntentResult:
        normalized = self._normalize_text(text)
        if not normalized:
            return IntentResult(action="unknown", confidence=0.0, normalized_text=normalized)

        if normalized in self.normalized_confirm_yes:
            return IntentResult(action="confirm_yes", normalized_text=normalized)
        if normalized in self.normalized_confirm_no:
            return IntentResult(action="confirm_no", normalized_text=normalized)

        for parser in (
            self._parse_direct_action,
            self._parse_temporal_query,
            self._parse_timer,
            self._parse_focus_or_break,
            self._parse_reminder_delete,
            self._parse_reminder,
            self._parse_memory_forget,
            self._parse_memory_recall,
            self._parse_memory_store,
        ):
            result = parser(normalized)
            if result is not None:
                result.normalized_text = normalized
                return result

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
        result = self.parse(text)
        if result.action in {"unknown", "unclear", "confirm_yes", "confirm_no"}:
            if result.action == "unclear" and result.suggestions:
                candidate = result.suggestions[0]["action"]
                if allowed_actions is None or candidate in allowed_actions:
                    return candidate
            return None

        if allowed_actions is not None and result.action not in allowed_actions:
            return None
        return result.action

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = lowered.replace("-", " ")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        if not lowered:
            return ""

        deduped_tokens: list[str] = []
        for token in lowered.split():
            if not deduped_tokens or deduped_tokens[-1] != token:
                deduped_tokens.append(token)
        return " ".join(deduped_tokens)

    def _parse_direct_action(self, normalized: str) -> IntentResult | None:
        direct = self.direct_action_map.get(normalized)
        if direct:
            return IntentResult(action=direct)

        tokens = set(normalized.split())
        if not tokens:
            return None

        if {"what", "can", "you", "do"}.issubset(tokens):
            return IntentResult(action="help")
        if "pomoc" in tokens or "commands" in tokens or "komendy" in tokens:
            return IntentResult(action="help")
        if {"how", "can", "you", "help", "me"}.issubset(tokens):
            return IntentResult(action="help")
        if {"co", "potrafisz"}.issubset(tokens) or {"jak", "mozesz", "pomoc"}.issubset(tokens):
            return IntentResult(action="help")

        if "status" in tokens or ("stan" in tokens and "systemu" in tokens):
            return IntentResult(action="status")

        if {"what", "is", "your", "name"}.issubset(tokens) or {"who", "are", "you"}.issubset(tokens):
            return IntentResult(action="introduce_self")
        if {"jak", "sie", "nazywasz"}.issubset(tokens) or {"kim", "jestes"}.issubset(tokens):
            return IntentResult(action="introduce_self")

        if "assistant" in tokens and ({"turn", "off"}.issubset(tokens) or {"stop"}.issubset(tokens)):
            return IntentResult(action="exit")
        if {"go", "sleep"}.issubset(tokens) or {"rest", "now"}.issubset(tokens):
            return IntentResult(action="exit")
        if ("asystenta" in tokens or "asystent" in tokens) and (
            "wylacz" in tokens or "wyłącz" in tokens or "zamknij" in tokens
        ):
            return IntentResult(action="exit")
        if ("spac" in tokens or "spać" in tokens or "odpocznij" in tokens) and (
            "idz" in tokens or "idź" in tokens or "spij" in tokens or "śpij" in tokens or "odpocznij" in tokens
        ):
            return IntentResult(action="exit")

        if "shutdown" in tokens or ("system" in tokens and {"turn", "off"}.issubset(tokens)):
            return IntentResult(action="shutdown")
        if ("system" in tokens or {"raspberry", "pi"}.issubset(tokens)) and (
            "wylacz" in tokens or "wyłącz" in tokens or "zamknij" in tokens or {"power", "off"}.issubset(tokens)
        ):
            return IntentResult(action="shutdown")

        return None

    def _parse_temporal_query(self, normalized: str) -> IntentResult | None:
        for action, patterns in (
            ("show_time", self.time_show_patterns),
            ("ask_time", self.time_query_patterns),
            ("show_date", self.date_show_patterns),
            ("ask_date", self.date_query_patterns),
            ("show_day", self.day_show_patterns),
            ("ask_day", self.day_query_patterns),
            ("show_year", self.year_show_patterns),
            ("ask_year", self.year_query_patterns),
        ):
            if self._matches_any_pattern(normalized, patterns):
                return IntentResult(action=action)
        return None

    def _parse_timer(self, normalized: str) -> IntentResult | None:
        minutes = self._extract_duration(normalized, self.timer_trigger_phrases)
        if minutes is not None:
            return IntentResult(action="timer_start", data={"minutes": minutes})

        if self._contains_any_phrase(normalized, self.timer_trigger_phrases):
            return IntentResult(action="timer_start", data={})

        return None

    def _parse_focus_or_break(self, normalized: str) -> IntentResult | None:
        focus_minutes = self._extract_duration(normalized, self.focus_trigger_phrases)
        if focus_minutes is not None:
            return IntentResult(action="focus_start", data={"minutes": focus_minutes})

        break_minutes = self._extract_duration(normalized, self.break_trigger_phrases)
        if break_minutes is not None:
            return IntentResult(action="break_start", data={"minutes": break_minutes})

        if self._contains_any_phrase(normalized, self.focus_trigger_phrases):
            return IntentResult(action="focus_start", data={})
        if self._contains_any_phrase(normalized, self.break_trigger_phrases):
            return IntentResult(action="break_start", data={})

        return None

    def _extract_duration(self, normalized: str, triggers: list[str]) -> float | None:
        if not self._contains_any_phrase(normalized, triggers):
            return None

        digit_match = re.search(
            r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sec|sekunda|sekundy|sekund|minute|minutes|min|minuta|minuty|minut)?",
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
        candidates = tokens[start:unit_index]
        if not candidates:
            return None

        for size in range(min(3, len(candidates)), 0, -1):
            parsed = self._parse_spoken_number_tokens(candidates[-size:])
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
        if not any(word in normalized for word in {"remind", "przypomnij"}):
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
                continue

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

        for pattern in [
            r"^(?:delete reminder|remove reminder|cancel reminder)\s+id\s+([a-z0-9]{1,32})$",
            r"^(?:usun przypomnienie|usuń przypomnienie|skasuj przypomnienie)\s+id\s+([a-z0-9]{1,32})$",
        ]:
            match = re.match(pattern, normalized)
            if match:
                return IntentResult(action="reminder_delete", data={"id": match.group(1).strip()})

        for pattern in [
            r"^(?:delete reminder|remove reminder|cancel reminder)(?: about)?\s+(.+)$",
            r"^(?:usun przypomnienie|usuń przypomnienie|skasuj przypomnienie)(?: o)?\s+(.+)$",
        ]:
            match = re.match(pattern, normalized)
            if match:
                message = self._cleanup_reminder_message(match.group(1))
                if message:
                    return IntentResult(action="reminder_delete", data={"message": message})

        return None

    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        for pattern in [
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
        ]:
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult(action="memory_recall", data={"key": key})
        return None

    def _parse_memory_forget(self, normalized: str) -> IntentResult | None:
        for pattern in [
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:zapomnij o|usun z pamieci|usuń z pamięci)\s+(.+)$",
        ]:
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

        for pattern in [
            r"^(.+?)\s+(?:is|are|jest|sa)\s+(.+)$",
            r"^(.+?)\s+(?:in|on|at|under|inside|obok|w|na|pod|przy)\s+(.+)$",
        ]:
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
        return self._parse_spoken_number_tokens(text.split())

    @staticmethod
    def _cleanup_reminder_message(text: str) -> str:
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

    @staticmethod
    def _cleanup_subject(text: str) -> str:
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
        normalized_tokens = set(normalized.split())
        scores: list[dict[str, Any]] = []
        min_ratio = 0.72 if len(normalized) > 5 else 0.80

        for phrase, action, phrase_tokens in self.fuzzy_candidates:
            if allowed_actions is not None and action not in allowed_actions:
                continue

            sequence_ratio = SequenceMatcher(None, normalized, phrase).ratio()
            token_ratio = self._token_overlap_ratio(normalized_tokens, phrase_tokens)
            combined_ratio = max(sequence_ratio, token_ratio)
            if combined_ratio >= min_ratio:
                scores.append(
                    {
                        "action": action,
                        "label": self.action_labels.get(action, action),
                        "score": round(combined_ratio, 3),
                    }
                )

        unique: dict[str, dict[str, Any]] = {}
        for item in sorted(scores, key=lambda x: x["score"], reverse=True):
            unique.setdefault(item["action"], item)
        return list(unique.values())[:2]

    @staticmethod
    def _token_overlap_ratio(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / max(len(left), len(right))

    def _matches_any_pattern(self, normalized: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, normalized) for pattern in patterns)

    def _contains_any_phrase(self, normalized: str, phrases: list[str]) -> bool:
        for phrase in phrases:
            normalized_phrase = self._normalize_text(phrase)
            if normalized == normalized_phrase:
                return True
            if f" {normalized_phrase} " in f" {normalized} ":
                return True
        return False