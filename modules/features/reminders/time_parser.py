from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.understanding.parsing.normalization import normalize_text, parse_spoken_number


@dataclass(slots=True)
class ReminderTimeParseResult:
    seconds: int
    due_at: datetime
    normalized_phrase: str
    display_phrase: str
    mode: str


class ReminderTimeParser:
    """Deterministic parser for guided reminder time answers."""

    _POLISH_UNITS = {
        "zero": 0,
        "jeden": 1,
        "jedna": 1,
        "jedno": 1,
        "dwa": 2,
        "dwie": 2,
        "dwaj": 2,
        "trzy": 3,
        "cztery": 4,
        "piec": 5,
        "szesc": 6,
        "siedem": 7,
        "osiem": 8,
        "dziewiec": 9,
    }

    _POLISH_TEENS = {
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
    }

    _POLISH_TENS = {
        "dwadziescia": 20,
        "trzydziesci": 30,
        "czterdziesci": 40,
        "piecdziesiat": 50,
        "szescdziesiat": 60,
    }

    _ENGLISH_UNITS = {
        "zero": 0,
        "one": 1,
        "a": 1,
        "an": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
    }

    _ENGLISH_TEENS = {
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
    }

    _ENGLISH_TENS = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
    }

    def parse(
        self,
        text: str,
        *,
        now: datetime | None = None,
        language: str = "en",
    ) -> ReminderTimeParseResult | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        current = now or datetime.now()
        normalized = normalize_text(raw)
        if not normalized:
            return None

        normalized = self._apply_asr_corrections(normalized, language=language)

        relative = self._parse_relative(
            normalized,
            now=current,
            language=language,
        )
        if relative is not None:
            return relative

        absolute = self._parse_absolute(
            normalized,
            now=current,
            language=language,
        )
        if absolute is not None:
            return absolute

        return None

    def _apply_asr_corrections(self, normalized: str, *, language: str) -> str:
        """Correct common short reminder-time ASR mistakes.

        Guided reminder time answers are very short, so ASR often turns Polish
        time phrases into English-looking or phonetically similar fragments.
        These corrections are intentionally limited to the reminder time parser.
        """

        clean = normalize_text(normalized)
        if not clean:
            return clean

        clean = clean.replace("sekend", "second")
        clean = clean.replace("sekonds", "seconds")
        clean = clean.replace("sekont", "second")
        clean = clean.replace("sekonts", "seconds")

        replacements = {
            "po osiem seconds": "osiem sekund",
            "po osiem second": "osiem sekund",
            "po 8 sekund": "8 sekund",
            "po osiem sekund": "osiem sekund",
            "trzy seconds": "trzy sekundy",
            "trzy second": "trzy sekundy",
            "czy sekund": "trzy sekundy",
            "czy sekundy": "trzy sekundy",
            "szi sekund": "trzy sekundy",
            "szi sekundy": "trzy sekundy",
            "szy sekund": "trzy sekundy",
            "szy sekundy": "trzy sekundy",
            # Common ASR for "za 10 sekund" / "za ten seconds".
            "jason second": "za 10 sekund",
            "jason seconds": "za 10 sekund",
            "json second": "za 10 sekund",
            "json seconds": "za 10 sekund",
            "ja son second": "za 10 sekund",
            "ja son seconds": "za 10 sekund",
            "za ten second": "za 10 sekund",
            "za ten seconds": "za 10 sekund",

            # Common ASR for "cztery sekundy".
            "kteri sekundy": "cztery sekundy",
            "ktery sekundy": "cztery sekundy",
            "który sekundy": "cztery sekundy",
            "ktory sekundy": "cztery sekundy",
            "kteri sekund": "cztery sekundy",
            "ktery sekund": "cztery sekundy",

            # Common ASR for "dwanaście".
            "dlonascie": "dwanascie sekund",
            "dłonaście": "dwanascie sekund",
            "dlo nascie": "dwanascie sekund",
            "dlo naście": "dwanascie sekund",
            "do nascie": "dwanascie sekund",
            "donascie": "dwanascie sekund",

            # Common ASR for "osiem sekund" where the unit is dropped.
            "ocean": "osiem sekund",
            "osian": "osiem sekund",
            "osien": "osiem sekund",
        }

        if clean in replacements:
            return replacements[clean]

        phrase_replacements = (
            (" seconds", " sekund"),
            (" second", " sekund"),
            (" sec", " sekund"),
            (" minutes", " minut"),
            (" minute", " minut"),
            (" hours", " godzin"),
            (" hour", " godzin"),
        )

        if str(language or "").lower().startswith("pl"):
            for old, new in phrase_replacements:
                clean = clean.replace(old, new)

            clean = re.sub(r"\bsekunds\b", "sekund", clean)
            clean = re.sub(r"\bminuts\b", "minut", clean)
            clean = re.sub(r"\bgodzins\b", "godzin", clean)

        return clean


    def _parse_relative(
        self,
        normalized: str,
        *,
        now: datetime,
        language: str,
    ) -> ReminderTimeParseResult | None:
        if any(
            phrase in normalized
            for phrase in (
                "za pol sekundy",
                "za pol sekunde",
                "half a second",
                "in half a second",
            )
        ):
            return self._build_relative_result(
                seconds=1,
                now=now,
                normalized=normalized,
                language=language,
            )

        if any(
            phrase in normalized
            for phrase in (
                "za sekunde",
                "za jedna sekunde",
                "sekunde",
                "jedna sekunde",
                "in a second",
                "in one second",
                "one second",
                "a second",
            )
        ):
            return self._build_relative_result(
                seconds=1,
                now=now,
                normalized=normalized,
                language=language,
            )

        if any(
            phrase in normalized
            for phrase in (
                "za pol minuty",
                "za pol minute",
                "in half a minute",
            )
        ):
            return self._build_relative_result(
                seconds=30,
                now=now,
                normalized=normalized,
                language=language,
            )

        if any(
            phrase in normalized
            for phrase in (
                "za minute",
                "za jedna minute",
                "minute",
                "jedna minute",
                "in a minute",
                "in one minute",
                "one minute",
                "a minute",
            )
        ):
            return self._build_relative_result(
                seconds=60,
                now=now,
                normalized=normalized,
                language=language,
            )

        if any(
            phrase in normalized
            for phrase in (
                "za pol godziny",
                "za polgodziny",
                "in half an hour",
                "half an hour",
            )
        ):
            return self._build_relative_result(
                seconds=30 * 60,
                now=now,
                normalized=normalized,
                language=language,
            )

        if re.search(
            r"\b(?:za\s+)?(?:godzine|jedna godzine|godzina)\b"
            r"|\b(?:in\s+)?(?:an hour|one hour|hour)\b",
            normalized,
        ):
            return self._build_relative_result(
                seconds=60 * 60,
                now=now,
                normalized=normalized,
                language=language,
            )

        unit_patterns = [
            (
                r"\b(?:za|in|after)?\s*(.+?)\s*"
                r"(sekunde|sekunda|sekundy|sekund|second|seconds|sec)\b",
                1,
            ),
            (
                r"\b(?:za|in|after)?\s*(.+?)\s*"
                r"(minute|minuta|minuty|minut|minute|minutes|min)\b",
                60,
            ),
            (
                r"\b(?:za|in|after)?\s*(.+?)\s*"
                r"(godzine|godzina|godziny|godzin|hour|hours|h)\b",
                3600,
            ),
        ]

        for pattern, multiplier in unit_patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue

            amount_text = self._clean_amount_text(match.group(1))
            amount = self._parse_amount(amount_text)
            if amount is None or amount <= 0:
                continue

            return self._build_relative_result(
                seconds=max(1, int(amount * multiplier)),
                now=now,
                normalized=normalized,
                language=language,
            )

        return None

    def _parse_absolute(
        self,
        normalized: str,
        *,
        now: datetime,
        language: str,
    ) -> ReminderTimeParseResult | None:
        day_offset = 0
        explicit_today = False

        if re.search(r"\b(?:jutro|tomorrow)\b", normalized):
            day_offset = 1
        elif re.search(r"\b(?:dzisiaj|today)\b", normalized):
            explicit_today = True

        match = re.search(
            r"\b(?:o|at)\s+(\d{1,2})(?:[: .](\d{1,2}))?\s*(am|pm)?\b",
            normalized,
        )
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = str(match.group(3) or "").strip().lower()

        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        if hour > 23 or minute > 59:
            return None

        due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        due_at = due_at + timedelta(days=day_offset)

        if due_at <= now:
            if explicit_today:
                return None
            due_at += timedelta(days=1)

        seconds = max(1, int((due_at - now).total_seconds()))
        return ReminderTimeParseResult(
            seconds=seconds,
            due_at=due_at,
            normalized_phrase=normalized,
            display_phrase=self._format_due_at(due_at, language=language),
            mode="absolute",
        )

    def _clean_amount_text(self, text: str) -> str:
        clean = str(text or "").strip()
        clean = re.sub(r"^(?:za|in|after)\s+", "", clean)
        clean = re.sub(r"\b(?:okolo|około|about|around)\b", "", clean)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()

    def _parse_amount(self, text: str) -> float | None:
        clean = str(text or "").strip().replace(",", ".")
        if not clean:
            return None

        number_match = re.search(r"\d+(?:\.\d+)?", clean)
        if number_match:
            try:
                return float(number_match.group(0))
            except ValueError:
                return None

        spoken = parse_spoken_number(clean)
        if spoken is not None:
            return float(spoken)

        phrase_number = self._parse_small_spoken_number(clean)
        if phrase_number is not None:
            return float(phrase_number)

        return None

    def _parse_small_spoken_number(self, text: str) -> int | None:
        clean = normalize_text(text)
        clean = clean.replace("-", " ")
        clean = re.sub(r"\s+", " ", clean).strip()
        if not clean:
            return None

        if clean in self._POLISH_UNITS:
            return self._POLISH_UNITS[clean]
        if clean in self._POLISH_TEENS:
            return self._POLISH_TEENS[clean]
        if clean in self._POLISH_TENS:
            return self._POLISH_TENS[clean]
        if clean in self._ENGLISH_UNITS:
            return self._ENGLISH_UNITS[clean]
        if clean in self._ENGLISH_TEENS:
            return self._ENGLISH_TEENS[clean]
        if clean in self._ENGLISH_TENS:
            return self._ENGLISH_TENS[clean]

        parts = clean.split()
        if len(parts) == 2:
            first, second = parts

            if first in self._POLISH_TENS and second in self._POLISH_UNITS:
                return self._POLISH_TENS[first] + self._POLISH_UNITS[second]

            if first in self._ENGLISH_TENS and second in self._ENGLISH_UNITS:
                return self._ENGLISH_TENS[first] + self._ENGLISH_UNITS[second]

        return None

    def _build_relative_result(
        self,
        *,
        seconds: int,
        now: datetime,
        normalized: str,
        language: str,
    ) -> ReminderTimeParseResult:
        safe_seconds = max(1, int(seconds))
        due_at = now + timedelta(seconds=safe_seconds)
        return ReminderTimeParseResult(
            seconds=safe_seconds,
            due_at=due_at,
            normalized_phrase=normalized,
            display_phrase=self._format_relative(safe_seconds, language=language),
            mode="relative",
        )

    def _format_relative(self, seconds: int, *, language: str) -> str:
        safe_seconds = max(1, int(seconds))
        lang = "pl" if str(language or "").lower().startswith("pl") else "en"

        if safe_seconds < 60:
            if lang == "pl":
                return f"za {safe_seconds} {self._polish_seconds_unit(safe_seconds)}"
            return "in 1 second" if safe_seconds == 1 else f"in {safe_seconds} seconds"

        if safe_seconds % 3600 == 0:
            hours = safe_seconds // 3600
            if lang == "pl":
                return f"za {hours} {self._polish_hours_unit(hours)}"
            return "in 1 hour" if hours == 1 else f"in {hours} hours"

        if safe_seconds % 60 == 0:
            minutes = safe_seconds // 60
            if lang == "pl":
                return f"za {minutes} {self._polish_minutes_unit(minutes)}"
            return "in 1 minute" if minutes == 1 else f"in {minutes} minutes"

        minutes = round(safe_seconds / 60)
        if lang == "pl":
            return f"za {minutes} {self._polish_minutes_unit(minutes)}"
        return "in 1 minute" if minutes == 1 else f"in {minutes} minutes"

    def _polish_seconds_unit(self, value: int) -> str:
        if value == 1:
            return "sekundę"
        if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
            return "sekundy"
        return "sekund"

    def _polish_minutes_unit(self, value: int) -> str:
        if value == 1:
            return "minutę"
        if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
            return "minuty"
        return "minut"

    def _polish_hours_unit(self, value: int) -> str:
        if value == 1:
            return "godzinę"
        if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
            return "godziny"
        return "godzin"

    def _format_due_at(self, due_at: datetime, *, language: str) -> str:
        lang = "pl" if str(language or "").lower().startswith("pl") else "en"
        clock = due_at.strftime("%H:%M")
        return f"o {clock}" if lang == "pl" else f"at {clock}"


__all__ = ["ReminderTimeParseResult", "ReminderTimeParser"]
