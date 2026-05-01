from __future__ import annotations

import re

from modules.understanding.parsing.models import IntentResult
from modules.understanding.parsing.normalization import normalize_text, parse_spoken_number


class IntentParserRemindersMixin:
    def _parse_reminder(self, normalized: str) -> IntentResult | None:
        normalized = self._normalize_guided_reminder_start(normalized)

        reminder_triggers = {
            "remind",
            "przypomnij",
            "przypomnisz",
            "przypomnienie",
            "reminder",
        }
        if not any(trigger in normalized for trigger in reminder_triggers):
            return None

        guided_phrases_pl = {
            "przypomnisz mi o czyms",
            "przypomnij mi o czyms",
            "przypomnij mi cos",
            "przypomnij cos",
            "przypomnisz mi cos",
            "przypomnisz cos",
            "przypomniesz mi cos",
            "przypomniesz cos",
            "ustaw przypomnienie",
            "dodaj przypomnienie",
            "chce dodac przypomnienie",
            "chce ustawic przypomnienie",
        }
        guided_phrases_en = {
            "set the reminder",
            "set the reminders",
            "set a reminder",
            "set reminder",
            "add a reminder",
            "add reminder",
            "create a reminder",
            "create reminder",
            "make a reminder",
            "make reminder",
            "remind me about something",
            "remind me something",
            "reminder",
        }

        if normalized in guided_phrases_pl:
            return IntentResult.from_action(
                action="reminder_create",
                data={"guided": True, "guided_language": "pl"},
            )

        if normalized in guided_phrases_en:
            return IntentResult.from_action(
                action="reminder_create",
                data={"guided": True, "guided_language": "en"},
            )

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

    def _normalize_guided_reminder_start(self, normalized: str) -> str:
        """Correct common ASR mistakes for guided reminder start phrases."""

        clean = normalize_text(normalized)
        if not clean:
            return clean

        exact_replacements = {
            "set the reminder": "set a reminder",
            "set the reminders": "set a reminder",
            "syl pomnimi cos": "przypomnij mi cos",
            "sił pomnimi coś": "przypomnij mi cos",
            "się pomni mi coś": "przypomnij mi cos",
            "sil pomnimi cos": "przypomnij mi cos",
            "sie pomni mi cos": "przypomnij mi cos",
            "pomnij mi cos": "przypomnij mi cos",
            "szypowi imicowac": "przypomnij mi cos",
            "szypowi imicować": "przypomnij mi cos",
            "sie pomnimi cos": "przypomnij mi cos",
            "się pomnimi coś": "przypomnij mi cos",
            "pomnimi cos": "przypomnij mi cos",
            "pomni mi cos": "przypomnij mi cos",
            "przypomni mi cos": "przypomnij mi cos",
            "przypomnij mi co": "przypomnij mi cos",
            "przypomnij cos": "przypomnij mi cos",
            "przypomnisz mi cos": "przypomnij mi cos",
            "przypomniesz mi cos": "przypomnij mi cos",
        }

        if clean in exact_replacements:
            return exact_replacements[clean]

        if "pomnimi" in clean and "cos" in clean:
            return "przypomnij mi cos"

        if "przypom" in clean and "cos" in clean:
            return "przypomnij mi cos"

        return clean


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
                candidate = candidate[len(prefix):].strip()
                break

        candidate = re.sub(
            r"\b(?:in|after|za)\s+\d+(?:[.,]\d+)?\s*(?:second|seconds|sec|minute|minutes|min|sekunda|sekundy|sekund|minuta|minuty|minut)\b",
            " ",
            candidate,
        )
        candidate = self._cleanup_reminder_message(candidate)
        return candidate