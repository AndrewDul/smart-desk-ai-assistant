from __future__ import annotations

import re


def normalize_text(assistant, text: str) -> str:
    return assistant.parser._normalize_text(text)


def detect_language(assistant, text: str) -> str:
    normalized = normalize_text(assistant, text)
    tokens = set(normalized.split())

    polish_markers = {
        "pomoc",
        "potrafisz",
        "godzina",
        "data",
        "dzien",
        "rok",
        "przypomnij",
        "zapamietaj",
        "gdzie",
        "imie",
        "przerwa",
        "skupienie",
        "ucze",
        "pokaz",
        "wyswietl",
        "tak",
        "nie",
        "zapomnij",
        "usun",
        "wyczysc",
        "przypomnienie",
        "przypomnienia",
        "wylacz",
    }
    english_markers = {
        "help",
        "time",
        "date",
        "day",
        "year",
        "remember",
        "remind",
        "where",
        "name",
        "focus",
        "break",
        "timer",
        "show",
        "display",
        "yes",
        "no",
        "assistant",
        "forget",
        "remove",
        "delete",
        "clear",
        "shutdown",
        "reminder",
        "reminders",
    }

    if any(ch in text for ch in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
        return "pl"
    if tokens & polish_markers:
        return "pl"
    if tokens & english_markers:
        return "en"
    return assistant.last_language or "en"


def localized(lang: str, pl_text: str, en_text: str) -> str:
    return pl_text if lang == "pl" else en_text


def speak_localized(assistant, lang: str, pl_text: str, en_text: str) -> None:
    assistant.voice_out.speak(localized(lang, pl_text, en_text), language=lang)


def context_language(assistant, text: str, detected_lang: str) -> str:
    context_lang = None

    if assistant.pending_follow_up:
        follow_up_lang = assistant.pending_follow_up.get("lang")
        if follow_up_lang in {"pl", "en"}:
            context_lang = follow_up_lang

    if context_lang is None and assistant.pending_confirmation:
        confirmation_lang = assistant.pending_confirmation.get("language")
        if confirmation_lang in {"pl", "en"}:
            context_lang = confirmation_lang

    if context_lang is None:
        return detected_lang

    parsed_action = assistant.parser.parse(text).action
    normalized = normalize_text(assistant, text)

    if parsed_action in {"confirm_yes", "confirm_no"}:
        return context_lang

    if extract_minutes_from_text(assistant, text) is not None and len(normalized.split()) <= 3:
        return context_lang

    if detected_lang in {"pl", "en"} and detected_lang != context_lang:
        return detected_lang

    return context_lang


def pluralize_polish(value: int, singular: str, few: str, many: str) -> str:
    if value == 1:
        return singular
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return few
    return many


def format_duration_text(total_seconds: int, lang: str) -> str:
    total_seconds = max(int(total_seconds), 0)

    if total_seconds < 60:
        if lang == "pl":
            unit = pluralize_polish(total_seconds, "sekundę", "sekundy", "sekund")
            return f"{total_seconds} {unit}"
        unit = "second" if total_seconds == 1 else "seconds"
        return f"{total_seconds} {unit}"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []

    if lang == "pl":
        if hours:
            parts.append(f"{hours} {pluralize_polish(hours, 'godzinę', 'godziny', 'godzin')}")
        if minutes:
            parts.append(f"{minutes} {pluralize_polish(minutes, 'minutę', 'minuty', 'minut')}")
        if seconds:
            parts.append(f"{seconds} {pluralize_polish(seconds, 'sekundę', 'sekundy', 'sekund')}")
        return " ".join(parts)

    if hours:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if seconds:
        parts.append(f"{seconds} {'second' if seconds == 1 else 'seconds'}")
    return " ".join(parts)


def extract_minutes_from_text(assistant, text: str) -> float | None:
    normalized = normalize_text(assistant, text)
    match = re.search(
        r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sec|sekunda|sekundy|sekund|minute|minutes|min|minuta|minuty|minut)?",
        normalized,
    )
    if not match:
        return None

    value = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "minutes").strip()

    if unit.startswith("sec") or unit.startswith("sek"):
        return round(value / 60.0, 2)
    return value


def is_yes(assistant, text: str) -> bool:
    return assistant.parser.parse(text).action == "confirm_yes"


def is_no(assistant, text: str) -> bool:
    return assistant.parser.parse(text).action == "confirm_no"