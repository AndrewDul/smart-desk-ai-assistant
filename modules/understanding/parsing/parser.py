from __future__ import annotations

import re
from difflib import SequenceMatcher

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import (
    NO_PHRASES,
    YES_PHRASES,
    clean_text,
    contains_any_phrase,
    extract_duration_minutes,
    normalize_text,
    parse_spoken_number,
    starts_with_show_intent,
    strip_leading_fillers,
    token_overlap_score,
)


class IntentParser:
    """
    Premium rule-based intent parser for NeXa.

    Design goals:
    - stay fast and deterministic on Raspberry Pi
    - cover the highest-value natural command shapes
    - emit payloads that match the new action flow directly
    - provide conservative fuzzy suggestions when confidence is not enough
    """

    def __init__(
        self,
        default_focus_minutes: float = 25,
        default_break_minutes: float = 5,
    ) -> None:
        self.default_focus_minutes = float(default_focus_minutes)
        self.default_break_minutes = float(default_break_minutes)

        self.normalized_confirm_yes = {normalize_text(item) for item in YES_PHRASES}
        self.normalized_confirm_no = {normalize_text(item) for item in NO_PHRASES}

        self.time_query_patterns = [
            r"\bwhat(?: s| is)? the time\b",
            r"\bwhat time is it\b",
            r"\bwhat time it is\b",
            r"\bwhat(?: s| is)? time is it\b",
            r"\btell me the time\b",
            r"\bcurrent time\b",
            r"\btime now\b",
            r"\btime is it\b",
            r"\btime please\b",
            r"\bktora jest godzina\b",
            r"\bktora godzina\b",
            r"\bjaka jest godzina\b",
            r"\bpodaj godzine\b",
            r"\bjaki jest czas\b",
            r"\bpowiedz godzine\b",
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
            r"\bdate today\b",
            r"\bjaka jest data\b",
            r"\bpodaj date\b",
            r"\bpowiedz date\b",
        ]
        self.date_show_patterns = [
            r"\bshow(?: me)? the date\b",
            r"\bdisplay(?: me)? the date\b",
            r"\bshow date\b",
            r"\bdisplay date\b",
            r"\bpokaz(?: mi)? date\b",
            r"\bwyswietl(?: mi)? date\b",
            r"\bpokaz(?: mi)? data\b",
            r"\bwyswietl(?: mi)? data\b",
        ]

        self.day_query_patterns = [
            r"\bwhat day is it\b",
            r"\bwhat day is today\b",
            r"\btell me the day\b",
            r"\bwhich day is it\b",
            r"\bjaki jest dzisiaj dzien\b",
            r"\bjaki mamy dzisiaj dzien\b",
            r"\bktory dzien mamy dzisiaj\b",
            r"\bpodaj dzien\b",
            r"\bpowiedz dzien\b",
        ]
        self.day_show_patterns = [
            r"\bshow(?: me)? the day\b",
            r"\bdisplay(?: me)? the day\b",
            r"\bshow day\b",
            r"\bdisplay day\b",
            r"\bpokaz(?: mi)? dzien\b",
            r"\bwyswietl(?: mi)? dzien\b",
        ]

        self.month_query_patterns = [
            r"\bwhat month is it\b",
            r"\bwhat month is today\b",
            r"\btell me the month\b",
            r"\bwhich month is it\b",
            r"\bjaki jest miesiac\b",
            r"\bjaki mamy miesiac\b",
            r"\bktory mamy miesiac\b",
            r"\bpodaj miesiac\b",
            r"\bpowiedz miesiac\b",
        ]
        self.month_show_patterns = [
            r"\bshow(?: me)? the month\b",
            r"\bdisplay(?: me)? the month\b",
            r"\bshow month\b",
            r"\bdisplay month\b",
            r"\bpokaz(?: mi)? miesiac\b",
            r"\bwyswietl(?: mi)? miesiac\b",
        ]

        self.year_query_patterns = [
            r"\bwhat year is it\b",
            r"\btell me the year\b",
            r"\bwhich year is it\b",
            r"\bjaki jest rok\b",
            r"\bktory mamy rok\b",
            r"\bpodaj rok\b",
            r"\bpowiedz rok\b",
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
            "reminders_clear": [
                "clear reminders",
                "delete all reminders",
                "remove all reminders",
                "wyczysc przypomnienia",
                "usun wszystkie przypomnienia",
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
                "turn off nexa",
                "switch off nexa",
                "close nexa",
                "stop nexa",
                "wylacz asystenta",
                "zamknij asystenta",
                "wylacz nexa",
                "zamknij nexa",
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
                "shutdown system",
                "shut down system",
                "wylacz system",
                "zamknij system",
                "wylacz raspberry pi",
                "wylacz komputer",
            ],
        }

        self.action_labels = {
            "help": "help / pomoc",
            "status": "status / stan",
            "memory_list": "memory / pamięć",
            "memory_clear": "clear memory / wyczyść pamięć",
            "memory_store": "remember / zapamiętaj",
            "memory_recall": "recall / przypomnij sobie",
            "memory_forget": "forget / zapomnij",
            "reminders_list": "reminders / przypomnienia",
            "reminders_clear": "clear reminders / wyczyść przypomnienia",
            "reminder_create": "create reminder / utwórz przypomnienie",
            "reminder_delete": "delete reminder / usuń przypomnienie",
            "timer_start": "start timer / ustaw timer",
            "timer_stop": "stop timer / wyłącz timer",
            "focus_start": "focus mode / focus mode",
            "break_start": "break mode / tryb przerwy",
            "introduce_self": "introduce yourself / przedstaw się",
            "ask_time": "time / godzina",
            "show_time": "show time / pokaż godzinę",
            "ask_date": "date / data",
            "show_date": "show date / pokaż datę",
            "ask_day": "day / dzień",
            "show_day": "show day / pokaż dzień",
            "ask_month": "month / miesiąc",
            "show_month": "show month / pokaż miesiąc",
            "ask_year": "year / rok",
            "show_year": "show year / pokaż rok",
            "exit": "exit / wyjście",
            "shutdown": "shutdown / wyłącz system",
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
                normalized_phrase = normalize_text(phrase)
                self.direct_action_map[normalized_phrase] = action
                if action not in {"exit", "shutdown", "memory_clear", "reminders_clear"}:
                    self.fuzzy_candidates.append(
                        (normalized_phrase, action, set(normalized_phrase.split()))
                    )

        temporal_groups = {
            "ask_time": self.time_query_patterns,
            "show_time": self.time_show_patterns,
            "ask_date": self.date_query_patterns,
            "show_date": self.date_show_patterns,
            "ask_day": self.day_query_patterns,
            "show_day": self.day_show_patterns,
            "ask_month": self.month_query_patterns,
            "show_month": self.month_show_patterns,
            "ask_year": self.year_query_patterns,
            "show_year": self.year_show_patterns,
        }
        for action, patterns in temporal_groups.items():
            for pattern in patterns:
                plain = (
                    pattern
                    .replace(r"\b", "")
                    .replace("(?: s| is)?", "")
                    .replace("(?: me)?", "")
                    .strip()
                )
                normalized_phrase = normalize_text(plain)
                if normalized_phrase:
                    self.fuzzy_candidates.append(
                        (normalized_phrase, action, set(normalized_phrase.split()))
                    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, text: str) -> IntentResult:
        normalized = normalize_text(text)
        if not normalized:
            return IntentResult.unknown(normalized_text=normalized)

        if normalized in self.normalized_confirm_yes:
            return IntentResult.confirmation(
                action="confirm_yes",
                normalized_text=normalized,
            )

        if normalized in self.normalized_confirm_no:
            return IntentResult.confirmation(
                action="confirm_no",
                normalized_text=normalized,
            )

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
            return IntentResult.unclear(
                suggestions=suggestions,
                normalized_text=normalized,
                confidence=suggestions[0]["score"],
            )

        return IntentResult.unknown(normalized_text=normalized)

    def find_action_in_text(
        self,
        text: str,
        allowed_actions: list[str] | None = None,
    ) -> str | None:
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

    # ------------------------------------------------------------------
    # Direct actions
    # ------------------------------------------------------------------

    def _parse_direct_action(self, normalized: str) -> IntentResult | None:
        direct = self.direct_action_map.get(normalized)
        if direct:
            return IntentResult.from_action(action=direct)

        tokens = set(normalized.split())
        if not tokens:
            return None

        if {"jak", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"w", "czym", "mozesz", "mi", "pomoc"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"co", "potrafisz"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"how", "can", "you", "help", "me"}.issubset(tokens):
            return IntentResult.from_action(action="help")
        if {"what", "can", "you", "do"}.issubset(tokens):
            return IntentResult.from_action(action="help")

        if "status" in tokens or ("stan" in tokens and "systemu" in tokens):
            return IntentResult.from_action(action="status")

        if {"jak", "sie", "nazywasz"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"kim", "jestes"}.issubset(tokens) or {"czym", "jestes"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"what", "is", "your", "name"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")
        if {"who", "are", "you"}.issubset(tokens) or {"what", "are", "you"}.issubset(tokens):
            return IntentResult.from_action(action="introduce_self")

        assistant_target = self._mentions_assistant_target(tokens)
        system_target = self._mentions_system_target(tokens)
        off_or_close = self._mentions_off_or_close(tokens)

        if assistant_target and off_or_close:
            return IntentResult.from_action(action="exit")
        if {"idz", "spac"}.issubset(tokens) or "odpocznij" in tokens or "spij" in tokens:
            return IntentResult.from_action(action="exit")
        if {"go", "to", "sleep"}.issubset(tokens) or {"stop", "listening"}.issubset(tokens):
            return IntentResult.from_action(action="exit")

        if system_target and off_or_close:
            return IntentResult.from_action(action="shutdown")
        if "shutdown" in tokens or ({"shut", "down"}.issubset(tokens) and system_target):
            return IntentResult.from_action(action="shutdown")

        if {"power", "off"}.issubset(tokens):
            if assistant_target and not system_target:
                return IntentResult.from_action(action="exit")
            return IntentResult.from_action(action="shutdown")

        return None

    # ------------------------------------------------------------------
    # Temporal
    # ------------------------------------------------------------------

    def _parse_temporal_query(self, normalized: str) -> IntentResult | None:
        groups = (
            ("show_time", self.time_show_patterns),
            ("ask_time", self.time_query_patterns),
            ("show_date", self.date_show_patterns),
            ("ask_date", self.date_query_patterns),
            ("show_day", self.day_show_patterns),
            ("ask_day", self.day_query_patterns),
            ("show_month", self.month_show_patterns),
            ("ask_month", self.month_query_patterns),
            ("show_year", self.year_show_patterns),
            ("ask_year", self.year_query_patterns),
        )
        for action, patterns in groups:
            if self._matches_any_pattern(normalized, patterns):
                return IntentResult.from_action(action=action)

        tokens = set(normalized.split())
        if not tokens:
            return None

        if self._looks_like_time_query(tokens):
            return IntentResult.from_action(action="ask_time")
        if self._looks_like_date_query(tokens):
            return IntentResult.from_action(action="ask_date")
        if self._looks_like_day_query(tokens):
            return IntentResult.from_action(action="ask_day")
        if self._looks_like_month_query(tokens):
            return IntentResult.from_action(action="ask_month")
        if self._looks_like_year_query(tokens):
            return IntentResult.from_action(action="ask_year")

        if starts_with_show_intent(normalized):
            if "time" in normalized or "godzin" in normalized or "czas" in normalized:
                return IntentResult.from_action(action="show_time")
            if "date" in normalized or "data" in normalized:
                return IntentResult.from_action(action="show_date")
            if "day" in normalized or "dzien" in normalized:
                return IntentResult.from_action(action="show_day")
            if "month" in normalized or "miesiac" in normalized:
                return IntentResult.from_action(action="show_month")
            if "year" in normalized or "rok" in normalized:
                return IntentResult.from_action(action="show_year")

        return None

    def _looks_like_time_query(self, tokens: set[str]) -> bool:
        if "time" in tokens and "it" in tokens:
            return True
        if {"what", "time"}.issubset(tokens):
            return True
        if {"current", "time"}.issubset(tokens):
            return True
        if {"tell", "time"}.issubset(tokens):
            return True
        if "godzina" in tokens or "godzine" in tokens or "czas" in tokens:
            return True
        if {"ktora", "godzina"}.issubset(tokens):
            return True
        if {"ktora", "jest", "godzina"}.issubset(tokens):
            return True
        return False

    def _looks_like_date_query(self, tokens: set[str]) -> bool:
        if "date" in tokens and ("what" in tokens or "today" in tokens or "current" in tokens):
            return True
        if {"what", "date"}.issubset(tokens):
            return True
        if "data" in tokens:
            return True
        return False

    def _looks_like_day_query(self, tokens: set[str]) -> bool:
        if {"what", "day"}.issubset(tokens):
            return True
        if {"which", "day"}.issubset(tokens):
            return True
        if "dzien" in tokens and ("dzisiaj" in tokens or "jaki" in tokens or "ktory" in tokens):
            return True
        return False

    def _looks_like_month_query(self, tokens: set[str]) -> bool:
        if {"what", "month"}.issubset(tokens):
            return True
        if {"which", "month"}.issubset(tokens):
            return True
        if "miesiac" in tokens:
            return True
        return False

    def _looks_like_year_query(self, tokens: set[str]) -> bool:
        if {"what", "year"}.issubset(tokens):
            return True
        if {"which", "year"}.issubset(tokens):
            return True
        if "rok" in tokens:
            return True
        return False

    # ------------------------------------------------------------------
    # Timer / focus / break
    # ------------------------------------------------------------------

    def _parse_timer(self, normalized: str) -> IntentResult | None:
        if self._looks_like_timer_stop(normalized):
            return IntentResult.from_action(action="timer_stop")

        minutes = self._extract_duration_with_triggers(normalized, self.timer_trigger_phrases)
        if minutes is not None:
            return IntentResult.from_action(
                action="timer_start",
                data={"minutes": minutes},
            )

        if contains_any_phrase(normalized, self.timer_trigger_phrases):
            return IntentResult.from_action(action="timer_start", data={})

        return None

    def _parse_focus_or_break(self, normalized: str) -> IntentResult | None:
        if self._looks_like_focus_stop(normalized) or self._looks_like_break_stop(normalized):
            return IntentResult.from_action(action="timer_stop")

        focus_minutes = self._extract_duration_with_triggers(
            normalized,
            self.focus_trigger_phrases,
        )
        if focus_minutes is not None:
            return IntentResult.from_action(
                action="focus_start",
                data={"minutes": focus_minutes},
            )

        break_minutes = self._extract_duration_with_triggers(
            normalized,
            self.break_trigger_phrases,
        )
        if break_minutes is not None:
            return IntentResult.from_action(
                action="break_start",
                data={"minutes": break_minutes},
            )

        if contains_any_phrase(normalized, self.focus_trigger_phrases):
            return IntentResult.from_action(action="focus_start", data={})

        if contains_any_phrase(normalized, self.break_trigger_phrases):
            return IntentResult.from_action(action="break_start", data={})

        return None

    def _extract_duration_with_triggers(
        self,
        normalized: str,
        triggers: list[str],
    ) -> float | None:
        if not contains_any_phrase(normalized, triggers):
            return None
        return extract_duration_minutes(normalized)

    def _looks_like_timer_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        timer_tokens = {"timer", "timera", "minutnik"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and bool(tokens & timer_tokens)

    def _looks_like_focus_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and ("focus" in tokens or {"tryb", "skupienia"} <= tokens)

    def _looks_like_break_stop(self, normalized: str) -> bool:
        stop_tokens = {"stop", "cancel", "end", "zatrzymaj", "anuluj", "wylacz", "zakoncz"}
        tokens = set(normalized.split())
        return bool(tokens & stop_tokens) and (
            "break" in tokens or "przerwe" in tokens or "przerwa" in tokens
        )

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def _parse_reminder(self, normalized: str) -> IntentResult | None:
        reminder_triggers = {"remind", "przypomnij", "reminder", "przypomnienie"}
        if not any(trigger in normalized for trigger in reminder_triggers):
            return None

        for pattern in (
            r"^(?:set )?(?:a )?reminder(?: to)?\s+(?:in|after)\s+(.+?)\s*(second|seconds|sec|minute|minutes|min)\s+(?:to|about)?\s+(.+)$",
            r"^(?:remind(?: me)?)\s+(?:in|after)\s+(.+?)\s*(second|seconds|sec|minute|minutes|min)\s+(?:to|about)?\s+(.+)$",
            r"^(?:remind(?: me)?)\s+(?:to|about)?\s+(.+?)\s+(?:in|after)\s+(.+?)\s*(second|seconds|sec|minute|minutes|min)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                if pattern.endswith(r"(second|seconds|sec|minute|minutes|min)$"):
                    message_raw = match.group(1).strip()
                    amount_text = match.group(2).strip()
                    unit = match.group(3).strip()
                else:
                    amount_text = match.group(1).strip()
                    unit = match.group(2).strip()
                    message_raw = match.group(3).strip()
                seconds = self._amount_and_unit_to_seconds(amount_text, unit)
                message = self._cleanup_reminder_message(message_raw)
                if seconds is not None and message:
                    return IntentResult.from_action(
                        action="reminder_create",
                        data={"seconds": seconds, "message": message},
                    )

        for pattern in (
            r"^(?:ustaw )?(?:przypomnienie|przypomnij(?: mi)?)\s+za\s+(.+?)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)\s+(.+)$",
            r"^(?:przypomnij(?: mi)?)\s+(.+?)\s+za\s+(.+?)\s*(sekunda|sekundy|sekund|minuta|minuty|minut)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                if pattern.endswith(r"(sekunda|sekundy|sekund|minuta|minuty|minut)$"):
                    message_raw = match.group(1).strip()
                    amount_text = match.group(2).strip()
                    unit = match.group(3).strip()
                else:
                    amount_text = match.group(1).strip()
                    unit = match.group(2).strip()
                    message_raw = match.group(3).strip()
                seconds = self._amount_and_unit_to_seconds(amount_text, unit)
                message = self._cleanup_reminder_message(message_raw)
                if seconds is not None and message:
                    return IntentResult.from_action(
                        action="reminder_create",
                        data={"seconds": seconds, "message": message},
                    )

        if "remind" in normalized or "przypomnij" in normalized:
            maybe_seconds = self._extract_seconds_from_text(normalized)
            maybe_message = self._extract_reminder_message_fallback(normalized)
            data: dict[str, object] = {}
            if maybe_seconds is not None:
                data["seconds"] = maybe_seconds
            if maybe_message:
                data["message"] = maybe_message
            if data:
                return IntentResult.from_action(action="reminder_create", data=data)

        return None

    def _parse_reminder_delete(self, normalized: str) -> IntentResult | None:
        if normalized in {normalize_text(item) for item in self.direct_action_phrases["reminders_clear"]}:
            return IntentResult.from_action(action="reminders_clear")

        for pattern in (
            r"^(?:delete reminder|remove reminder|cancel reminder)\s+id\s+([a-z0-9]{1,32})$",
            r"^(?:usun przypomnienie|skasuj przypomnienie)\s+id\s+([a-z0-9]{1,32})$",
        ):
            match = re.match(pattern, normalized)
            if match:
                return IntentResult.from_action(
                    action="reminder_delete",
                    data={"id": match.group(1).strip()},
                )

        for pattern in (
            r"^(?:delete reminder|remove reminder|cancel reminder)(?: about)?\s+(.+)$",
            r"^(?:usun przypomnienie|skasuj przypomnienie)(?: o)?\s+(.+)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                message = self._cleanup_reminder_message(match.group(1))
                if message:
                    return IntentResult.from_action(
                        action="reminder_delete",
                        data={"message": message},
                    )

        return None

    def _amount_and_unit_to_seconds(self, amount_text: str, unit: str) -> int | None:
        amount = self._parse_amount_text(amount_text)
        if amount is None or amount <= 0:
            return None

        safe_unit = normalize_text(unit)
        if safe_unit.startswith("sec") or safe_unit.startswith("sek"):
            return int(amount)

        return int(amount * 60)

    def _extract_seconds_from_text(self, normalized: str) -> int | None:
        seconds_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:second|seconds|sec|sekunda|sekundy|sekund)\b",
            normalized,
        )
        if seconds_match:
            try:
                return max(1, int(float(seconds_match.group(1).replace(",", "."))))
            except ValueError:
                return None

        minutes_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:minute|minutes|min|minuta|minuty|minut)\b",
            normalized,
        )
        if minutes_match:
            try:
                return max(1, int(float(minutes_match.group(1).replace(",", ".")) * 60))
            except ValueError:
                return None

        spoken_number = parse_spoken_number(normalized)
        if spoken_number is not None and spoken_number > 0:
            if any(token in normalized for token in ("second", "seconds", "sec", "sekunda", "sekundy", "sekund")):
                return int(spoken_number)
            if any(token in normalized for token in ("minute", "minutes", "min", "minuta", "minuty", "minut")):
                return int(spoken_number * 60)

        return None

    def _extract_reminder_message_fallback(self, normalized: str) -> str:
        candidate = normalized

        prefixes = (
            "set a reminder ",
            "set reminder ",
            "remind me ",
            "remind ",
            "przypomnij mi ",
            "przypomnij ",
            "ustaw przypomnienie ",
        )
        for prefix in prefixes:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix) :].strip()
                break

        candidate = re.sub(
            r"\b(?:in|after|za)\s+\d+(?:[.,]\d+)?\s*(?:second|seconds|sec|minute|minutes|min|sekunda|sekundy|sekund|minuta|minuty|minut)\b",
            " ",
            candidate,
        )
        candidate = self._cleanup_reminder_message(candidate)
        return candidate

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def _parse_memory_recall(self, normalized: str) -> IntentResult | None:
        for pattern in (
            r"^(?:where are|where is) (?:my )?(.+)$",
            r"^where did i put (?:my )?(.+)$",
            r"^what do you remember about (.+)$",
            r"^do you remember (.+)$",
            r"^recall (.+)$",
            r"^remember (?:where|what) (.+)$",
            r"^gdzie (?:sa|jest) (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylem (?:moje |moj |moja )?(.+)$",
            r"^gdzie polozylam (?:moje |moj |moja )?(.+)$",
            r"^co pamietasz o (.+)$",
            r"^czy pamietasz (.+)$",
        ):
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult.from_action(
                        action="memory_recall",
                        data={"key": key},
                    )
        return None

    def _parse_memory_forget(self, normalized: str) -> IntentResult | None:
        for pattern in (
            r"^(?:forget|remove from memory|delete from memory)\s+(.+)$",
            r"^(?:forget|remove|delete)\s+(.+?)\s+from\s+memory$",
            r"^(?:zapomnij o|usun z pamieci|skasuj z pamieci)\s+(.+)$",
            r"^(?:usun|skasuj)\s+(.+?)\s+z\s+pamieci$",
        ):
            match = re.match(pattern, normalized)
            if match:
                key = self._cleanup_subject(match.group(1))
                if key:
                    return IntentResult.from_action(
                        action="memory_forget",
                        data={"key": key},
                    )
        return None

    def _parse_memory_store(self, normalized: str) -> IntentResult | None:
        prefixes = (
            "remember that ",
            "remember ",
            "zapamietaj ze ",
            "zapamietaj ",
            "pamietaj ze ",
            "pamietaj ",
        )

        candidate = normalized
        matched_prefix = False

        for prefix in prefixes:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix) :].strip()
                matched_prefix = True
                break

        if not matched_prefix or not candidate:
            return None

        for pattern in (
            r"^(.+?)\s+(?:is|are|jest|sa)\s+(.+)$",
        ):
            match = re.match(pattern, candidate)
            if match:
                subject = self._cleanup_subject(match.group(1))
                predicate = clean_text(match.group(2))
                if subject and predicate:
                    return IntentResult.from_action(
                        action="memory_store",
                        data={
                            "key": subject,
                            "value": predicate,
                            "memory_text": candidate,
                        },
                    )

        location_markers = (
            " in ",
            " on ",
            " at ",
            " under ",
            " inside ",
            " beside ",
            " near ",
            " obok ",
            " w ",
            " na ",
            " pod ",
            " przy ",
        )
        for marker in location_markers:
            if marker in candidate:
                left, right = candidate.split(marker, 1)
                subject = self._cleanup_subject(left)
                predicate = clean_text(f"{marker.strip()} {right}")
                if subject and right.strip():
                    return IntentResult.from_action(
                        action="memory_store",
                        data={
                            "key": subject,
                            "value": predicate,
                            "memory_text": candidate,
                        },
                    )

        return IntentResult.from_action(
            action="memory_store",
            data={"memory_text": candidate},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_amount_text(self, text: str) -> int | None:
        cleaned = clean_text(text)
        if not cleaned:
            return None
        if re.fullmatch(r"\d+", cleaned):
            return int(cleaned)

        spoken = parse_spoken_number(cleaned)
        return int(spoken) if spoken is not None else None

    @staticmethod
    def _cleanup_reminder_message(text: str) -> str:
        cleaned = clean_text(text)
        prefixes = (
            "about ",
            "to ",
            "o ",
            "ze ",
            "zebym ",
            "ze mam ",
            "że ",
            "żebym ",
            "że mam ",
        )
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                normalized_cleaned = normalize_text(cleaned)
                normalized_prefix = normalize_text(prefix)
                if normalized_cleaned.startswith(normalized_prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True
        return clean_text(cleaned)

    @staticmethod
    def _cleanup_subject(text: str) -> str:
        cleaned = clean_text(text)
        prefixes = ("my ", "the ", "moje ", "moj ", "moja ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                normalized_cleaned = normalize_text(cleaned)
                normalized_prefix = normalize_text(prefix)
                if normalized_cleaned.startswith(normalized_prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True
        return strip_leading_fillers(cleaned)

    def _get_fuzzy_suggestions(
        self,
        normalized: str,
        allowed_actions: list[str] | None = None,
    ) -> list[dict[str, object]]:
        scores: list[dict[str, object]] = []
        min_ratio = 0.78 if len(normalized) > 5 else 0.85

        for phrase, action, _phrase_tokens in self.fuzzy_candidates:
            if allowed_actions is not None and action not in allowed_actions:
                continue

            sequence_ratio = SequenceMatcher(None, normalized, phrase).ratio()
            overlap_ratio = token_overlap_score(normalized, phrase)
            combined_ratio = max(sequence_ratio, overlap_ratio)

            if combined_ratio >= min_ratio:
                scores.append(
                    {
                        "action": action,
                        "label": self.action_labels.get(action, action),
                        "score": round(combined_ratio, 3),
                    }
                )

        unique: dict[str, dict[str, object]] = {}
        for item in sorted(scores, key=lambda x: float(x["score"]), reverse=True):
            unique.setdefault(str(item["action"]), item)

        return list(unique.values())[:2]

    @staticmethod
    def _matches_any_pattern(normalized: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, normalized) for pattern in patterns)

    @staticmethod
    def _mentions_assistant_target(tokens: set[str]) -> bool:
        return bool({"assistant", "asystenta", "asystent", "nexa"} & tokens)

    @staticmethod
    def _mentions_system_target(tokens: set[str]) -> bool:
        return "system" in tokens or {"raspberry", "pi"}.issubset(tokens) or "komputer" in tokens

    @staticmethod
    def _mentions_off_or_close(tokens: set[str]) -> bool:
        if "shutdown" in tokens:
            return True
        if {"shut", "down"}.issubset(tokens):
            return True
        if {"turn", "off"}.issubset(tokens):
            return True
        if {"switch", "off"}.issubset(tokens):
            return True
        if {"power", "off"}.issubset(tokens):
            return True
        if "wylacz" in tokens or "zamknij" in tokens:
            return True
        return False


__all__ = ["IntentParser"]