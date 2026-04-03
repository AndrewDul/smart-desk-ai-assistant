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
        self.default_focus_minutes = float(default_focus_minutes)
        self.default_break_minutes = float(default_break_minutes)

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
            r"\bwhat(?: s| is)? the time\b",
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
            r"\bpokaz(?: mi)? godzine\b",
            r"\bwyswietl(?: mi)? godzine\b",
            r"\bpokaz(?: mi)? czas\b",
            r"\bwyswietl(?: mi)? czas\b",
        ]

        self.date_query_patterns = [
            r"\bwhat(?: s| is)? the date\b",
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
            r"\bpokaz(?: mi)? date\b",
            r"\bwyswietl(?: mi)? date\b",
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
            r"\bpokaz(?: mi)? dzien\b",
            r"\bwyswietl(?: mi)? dzien\b",
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
            r"\bpokaz(?: mi)? rok\b",
            r"\bwyswietl(?: mi)? rok\b",
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
                "pokaz mi pomoc",
                "pokaz menu",
                "pokaz mi menu",
                "menu asystenta",
                "co potrafisz",
                "co umiesz",
                "jak mozesz mi pomoc",
                "w czym mozesz mi pomoc",
                "powiedz co potrafisz",
                "pokaz mozliwosci",
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
                "pokaz pamiec",
                "co pamietasz",
            ],
            "memory_clear": [
                "clear memory",
                "wipe memory",
                "delete all memory",
                "remove all memory",
                "forget everything",
                "wyczysc pamiec",
                "usun cala pamiec",
                "zapomnij wszystko",
                "skasuj pamiec",
            ],
            "reminders_list": [
                "reminders",
                "show reminders",
                "list reminders",
                "show my reminders",
                "przypomnienia",
                "pokaz przypomnienia",
                "pokaz moje przypomnienia",
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
                "zatrzymaj focus",
                "wylacz focus",
                "zakoncz focus",
                "zatrzymaj przerwe",
                "wylacz przerwe",
                "zakoncz przerwe",
            ],
            "introduce_self": [
                "who are you",
                "what are you",
                "what is your name",
                "what s your name",
                "tell me your name",
                "say your name",
                "introduce yourself",
                "tell me about yourself",
                "przedstaw sie",
                "kim jestes",
                "czym jestes",
                "jak sie nazywasz",
                "powiedz jak sie nazywasz",
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
                "zamknij asystenta",
                "idz spac",
                "spij",
                "odpocznij",
                "przestan sluchac",
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
                "zamknij system",
                "wylacz raspberry pi",
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
            "szesc": 6,
            "siedem": 7,
            "osiem": 8,
            "dziewiec": 9,
            "dziesiec": 10,
            "jedenascie": 11,
            "dwanascie": 12,
            "trzynascie": 13,
            "czternascie": 14,
            "pietnascie": 15,
            "szesnascie": 16,
            "siedemnascie": 17,
            "osiemnascie": 18,
            "dziewietnascie": 19,
            "dwadziescia": 20,
            "trzydziesci": 30,
            "czterdziesci": 40,
            "piecdziesiat": 50,
            "szescdziesiat": 60,
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
            "wlacz przerwe",
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
                plain = pattern.replace(r"\b", "").replace("(?: s| is)?", "").strip()
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

        if {"jak", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult(action="help")
        if {"w", "czym", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult(action="help")
        if {"co", "potrafisz"}.issubset(tokens):
            return IntentResult(action="help")
        if {"how", "can", "you", "help", "me"}.issubset(tokens):
            return IntentResult(action="help")
        if {"what", "can", "you", "do"}.issubset(tokens):
            return IntentResult(action="help")

        if "status" in tokens or ("stan" in tokens and "systemu" in tokens):
            return IntentResult(action="status")

        if {"jak", "sie", "nazywasz"}.issubset(tokens):
            return IntentResult(action="introduce_self")
        if {"kim", "jestes"}.issubset(tokens) or {"czym", "jestes"}.issubset(tokens):
            return IntentResult(action="introduce_self")
        if {"what", "is", "your", "name"}.issubset(tokens):
            return IntentResult(action="introduce_self")
        if {"who", "are", "you"}.issubset(tokens) or {"what", "are", "you"}.issubset(tokens):
            return IntentResult(action="introduce_self")

        if ("asystenta" in tokens or "asystent" in tokens) and ("wylacz" in tokens or "zamknij" in tokens):
            return IntentResult(action="exit")
        if {"idz", "spac"}.issubset(tokens) or "odpocznij" in tokens:
            return IntentResult(action="exit")
        if {"turn", "off", "assistant"}.issubset(tokens) or {"go", "to", "sleep"}.issubset(tokens):
            return IntentResult(action="exit")

        if ("system" in tokens or {"raspberry", "pi"}.issubset(tokens)) and ("wylacz" in tokens or "zamknij" in tokens):
            return IntentResult(action="shutdown")
        if "shutdown" in tokens or {"power", "off"}.issubset(tokens):
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
        if "remind" not in normalized and "przypomnij" not in normalized:
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
            "usun wszystkie przypomnienia",
        }
        normalized_clear = {self._normalize_text(item) for item in clear_phrases}
        if normalized in normalized_clear:
            return IntentResult(action="reminders_clear")

        for pattern in [
            r"^(?:delete reminder|remove reminder|cancel reminder)\s+id\s+([a-z0-9]{1,32})$",
            r"^(?:usun przypomnienie|skasuj przypomnienie)\s+id\s+([a-z0-9]{1,32})$",
        ]:
            match = re.match(pattern, normalized)
            if match:
                return IntentResult(action="reminder_delete", data={"id": match.group(1).strip()})

        for pattern in [
            r"^(?:delete reminder|remove reminder|cancel reminder)(?: about)?\s+(.+)$",
            r"^(?:usun przypomnienie|skasuj przypomnienie)(?: o)?\s+(.+)$",
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
        patterns = [
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:forget|remove|delete)\s+(.+?)\s+from\s+memory$",
            r"^(?:zapomnij o|usun z pamieci|skasuj z pamieci)\s+(.+)$",
            r"^(?:usun|skasuj)\s+(.+?)\s+z\s+pamieci$",
        ]

        for pattern in patterns:
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
        prefixes = ("about ", "to ", "o ", "ze ", "zebym ", "ze mam ", "że ", "żebym ", "że mam ")
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
        min_ratio = 0.78 if len(normalized) > 5 else 0.85

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
        wrapped = f" {normalized} "
        for phrase in phrases:
            normalized_phrase = self._normalize_text(phrase)
            if normalized == normalized_phrase:
                return True
            if f" {normalized_phrase} " in wrapped:
                return True
        return False