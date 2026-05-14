from __future__ import annotations

from enum import Enum


class CommandLanguage(str, Enum):
    """Language detected or assigned for short command recognition."""

    ENGLISH = "en"
    POLISH = "pl"
    UNKNOWN = "unknown"


_POLISH_DIACRITICS = set("ąćęłńóśźż")

_POLISH_HINTS = {
    "baza",
    "bateria",
    "czas",
    "data",
    "daj",
    "dostep",
    "godzina",
    "ikony",
    "jaka",
    "jaki",
    "jest",
    "komputera",
    "linuxa",
    "minut",
    "poka",
    "pokaz",
    "pomoc",
    "pulpit",
    "shell",
    "sterowania",
    "temperatura",
    "tryb",
    "twoja",
    "ukryj",
    "wroc",
    "zdejmij",
}

_ENGLISH_HINTS = {
    "battery",
    "computer",
    "control",
    "date",
    "desktop",
    "drive",
    "focus",
    "give",
    "help",
    "hide",
    "icons",
    "linux",
    "manual",
    "minutes",
    "mode",
    "name",
    "shell",
    "show",
    "start",
    "stop",
    "temperature",
    "time",
    "timer",
    "what",
    "your",
    "cpu",
    "processor",
    "system",
    "device",
    "computer",
    "board",
    "core",
    "raspberry",
    "pi",
    "hot",
    "overheating",
}


def detect_command_language(text: str) -> CommandLanguage:
    """Detect likely command language for short built-in utterances."""

    raw = text.strip().lower()
    if not raw:
        return CommandLanguage.UNKNOWN

    if any(character in _POLISH_DIACRITICS for character in raw):
        return CommandLanguage.POLISH

    words = {
        word
        for word in raw.replace("?", " ").replace(",", " ").replace(".", " ").split()
        if word
    }

    polish_score = len(words & _POLISH_HINTS)
    english_score = len(words & _ENGLISH_HINTS)

    if polish_score > english_score:
        return CommandLanguage.POLISH
    if english_score > polish_score:
        return CommandLanguage.ENGLISH

    return CommandLanguage.UNKNOWN