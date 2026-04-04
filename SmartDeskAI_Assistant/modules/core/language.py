from __future__ import annotations

import re
import unicodedata


POLISH_DIACRITICS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"

POLISH_FUNCTION_WORDS = {
    "a",
    "ale",
    "bo",
    "co",
    "czy",
    "czyli",
    "dla",
    "do",
    "gdzie",
    "i",
    "jak",
    "jaka",
    "jaki",
    "jest",
    "ktora",
    "ktorej",
    "mam",
    "masz",
    "mi",
    "mnie",
    "moge",
    "mozesz",
    "mozemy",
    "na",
    "nie",
    "o",
    "od",
    "po",
    "pod",
    "pomoc",
    "potrzebuje",
    "powiedz",
    "pogadaj",
    "przy",
    "sie",
    "teraz",
    "to",
    "w",
    "za",
    "zadaj",
    "ze",
}

ENGLISH_FUNCTION_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "at",
    "because",
    "but",
    "can",
    "could",
    "do",
    "for",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "now",
    "of",
    "on",
    "please",
    "say",
    "talk",
    "tell",
    "the",
    "to",
    "today",
    "what",
    "when",
    "where",
    "why",
    "with",
    "would",
    "you",
    "your",
}

POLISH_CONTENT_WORDS = {
    "asystent",
    "asystenta",
    "break",
    "ciekawego",
    "czas",
    "data",
    "dzien",
    "focus",
    "godzina",
    "godzine",
    "imie",
    "interesujacego",
    "jakosc",
    "klucze",
    "komendy",
    "kuchni",
    "leniwa",
    "leniwy",
    "memory",
    "motywacji",
    "nauce",
    "nazwa",
    "nazywasz",
    "nexa",
    "pamiec",
    "pamietaj",
    "pamietasz",
    "pogadac",
    "pokaz",
    "potrafisz",
    "powiedz",
    "przerwa",
    "przypomnij",
    "przypomnienie",
    "przypomnienia",
    "przytloczona",
    "przytloczony",
    "rok",
    "rozprasza",
    "senna",
    "senny",
    "skupic",
    "smiesznego",
    "stoper",
    "system",
    "timer",
    "trudny",
    "umiesz",
    "usun",
    "wlacz",
    "wyswietl",
    "wyjasnij",
    "wylacz",
    "wytlumacz",
    "zabawnego",
    "zagadka",
    "zagadke",
    "zapamietaj",
    "zapomnij",
    "zle",
    "zmotywuj",
    "zmeczona",
    "zmeczony",
    "zwierzetach",
}

ENGLISH_CONTENT_WORDS = {
    "animals",
    "assistant",
    "black",
    "break",
    "capabilities",
    "clear",
    "clock",
    "date",
    "day",
    "delete",
    "display",
    "explain",
    "features",
    "focus",
    "forget",
    "funny",
    "help",
    "interesting",
    "introduce",
    "joke",
    "keys",
    "kitchen",
    "lazy",
    "memory",
    "menu",
    "motivate",
    "motivation",
    "name",
    "nexa",
    "overwhelmed",
    "recursion",
    "remind",
    "reminder",
    "reminders",
    "remember",
    "riddle",
    "screen",
    "shutdown",
    "sleep",
    "sleepy",
    "system",
    "talk",
    "time",
    "timer",
    "tired",
    "turn",
    "year",
}

POLISH_STRONG_PHRASES = {
    "co potrafisz",
    "co to jest",
    "czarna dziura",
    "czym jest",
    "daj mi zagadke",
    "gdzie sa klucze",
    "i feel tired",
    "jak mozesz mi pomoc",
    "jak sie nazywasz",
    "jaka jest data",
    "jaka jest godzina",
    "kim jestes",
    "ktora jest godzina",
    "mozemy porozmawiac chwile",
    "mozemy pogadac",
    "nie moge sie skupic",
    "nie moge sie skoncentrowac",
    "opowiedz mi cos ciekawego",
    "opowiedz mi cos ciekawego o zwierzetach",
    "pogadaj ze mna",
    "pomoz mi sie uczyc",
    "potrzebuje pomocy w nauce",
    "powiedz cos smiesznego",
    "powiedz cos zabawnego",
    "powiedz dowcip",
    "przypomnij mi za",
    "turn off assistant",
    "turn off system",
    "ustaw timer",
    "wyjasnij",
    "wylacz asystenta",
    "wylacz nexa",
    "wylacz system",
    "wytlumacz",
    "zadaj mi zagadke",
    "zapamietaj ze",
}

ENGLISH_STRONG_PHRASES = {
    "can we talk",
    "can we talk for a minute",
    "can you talk with me for a minute",
    "cheer me up",
    "explain recursion",
    "give me a riddle",
    "how can you help me",
    "how do they form",
    "i am tired",
    "i do not feel well",
    "i feel tired",
    "i feel bad",
    "i need help studying",
    "what can you do",
    "what is a black hole",
    "what is your name",
    "what time is it",
    "who are you",
    "turn off assistant",
    "turn off nexa",
    "turn off system",
    "tell me a joke",
    "tell me a riddle",
    "tell me something funny",
    "tell me something interesting",
    "tell me something interesting about animals",
    "talk to me",
    "show date",
    "show day",
    "show time",
    "show year",
    "remind me in",
    "remember that",
    "motivate me",
}

STRONG_POLISH_SHORT = {
    "czas",
    "data",
    "dzien",
    "focus",
    "godzina",
    "help",
    "memory",
    "nexa",
    "pamiec",
    "pokaz",
    "pomoc",
    "przerwa",
    "przypomnienia",
    "rok",
    "timer",
    "wylacz",
    "zagadka",
}

STRONG_ENGLISH_SHORT = {
    "assistant",
    "break",
    "date",
    "day",
    "focus",
    "help",
    "joke",
    "memory",
    "nexa",
    "riddle",
    "show",
    "shutdown",
    "talk",
    "time",
    "timer",
    "year",
}

POLISH_FUZZY_CONFIRM_YES = {"tag", "tac", "takg", "takkk", "tek", "tok"}
POLISH_FUZZY_CONFIRM_NO = {"ne", "nee", "ni", "niee", "nje"}

POLISH_CONFIRM_YES_STRONG = {
    "tak",
    "tak tak",
    "jasne",
    "no jasne",
    "oczywiscie",
    "pewnie",
    "dokladnie",
    "zgadza sie",
    "potwierdzam",
}

POLISH_CONFIRM_NO_STRONG = {
    "nie",
    "nie nie",
    "nie teraz",
    "anuluj",
    "zostaw to",
    "niewazne",
    "nie pokazuj",
    "nie wyswietlaj",
}

ENGLISH_CONFIRM_YES_STRONG = {
    "yes",
    "yeah",
    "yep",
    "sure",
    "of course",
    "correct",
    "do it",
    "show it",
    "display it",
}

ENGLISH_CONFIRM_NO_STRONG = {
    "no",
    "nope",
    "cancel",
    "stop",
    "leave it",
    "never mind",
    "dont show it",
    "do not show it",
}


def _fallback_normalize_text(text: str) -> str:
    lowered = str(text or "").lower().strip()
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


def normalize_text(assistant, text: str) -> str:
    parser = getattr(assistant, "parser", None)
    if parser is not None and hasattr(parser, "_normalize_text"):
        return parser._normalize_text(text)
    return _fallback_normalize_text(text)


def _confirm_yes_set(assistant) -> set[str]:
    parser_set = getattr(assistant.parser, "normalized_confirm_yes", None)
    if isinstance(parser_set, set):
        return parser_set

    fallback = {
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
        "zgadza sie",
        "potwierdzam",
        "zrob to",
        "pokaz",
        "wyswietl",
    }
    return {normalize_text(assistant, item) for item in fallback}


def _confirm_no_set(assistant) -> set[str]:
    parser_set = getattr(assistant.parser, "normalized_confirm_no", None)
    if isinstance(parser_set, set):
        return parser_set

    fallback = {
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
        "nie pokazuj",
        "nie wyswietlaj",
    }
    return {normalize_text(assistant, item) for item in fallback}


def _current_confirmation_language(assistant) -> str | None:
    if assistant.pending_follow_up:
        follow_up_lang = assistant.pending_follow_up.get("lang")
        if follow_up_lang in {"pl", "en"}:
            return follow_up_lang

    if assistant.pending_confirmation:
        confirmation_lang = assistant.pending_confirmation.get("language")
        if confirmation_lang in {"pl", "en"}:
            return confirmation_lang

    return None


def _extract_minutes_from_normalized(normalized: str) -> float | None:
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


def _classify_confirmation(assistant, text: str) -> str | None:
    normalized = normalize_text(assistant, text)
    if not normalized:
        return None

    direct_parser_yes = normalized in _confirm_yes_set(assistant)
    direct_parser_no = normalized in _confirm_no_set(assistant)
    context_lang = _current_confirmation_language(assistant)

    if context_lang == "pl":
        if normalized in POLISH_CONFIRM_NO_STRONG or normalized in POLISH_FUZZY_CONFIRM_NO:
            return "no"
        if normalized in POLISH_CONFIRM_YES_STRONG or normalized in POLISH_FUZZY_CONFIRM_YES:
            return "yes"
        if normalized == "yes":
            return "yes"
        if normalized == "no":
            return "no"
        if normalized in {"yeah", "yep"}:
            return None
        if direct_parser_no:
            return "no"
        if direct_parser_yes:
            return "yes"
        return None

    if context_lang == "en":
        if normalized in ENGLISH_CONFIRM_NO_STRONG:
            return "no"
        if normalized in ENGLISH_CONFIRM_YES_STRONG:
            return "yes"
        if normalized == "tak":
            return "yes"
        if normalized == "nie":
            return "no"
        if normalized in POLISH_FUZZY_CONFIRM_YES or normalized in POLISH_FUZZY_CONFIRM_NO:
            return None
        if direct_parser_no:
            return "no"
        if direct_parser_yes:
            return "yes"
        return None

    if normalized in POLISH_CONFIRM_NO_STRONG or normalized in ENGLISH_CONFIRM_NO_STRONG:
        return "no"
    if normalized in POLISH_CONFIRM_YES_STRONG or normalized in ENGLISH_CONFIRM_YES_STRONG:
        return "yes"

    if direct_parser_yes:
        return "yes"
    if direct_parser_no:
        return "no"

    return None


def _looks_like_confirmation(assistant, normalized: str) -> bool:
    return _classify_confirmation(assistant, normalized) in {"yes", "no"}


def _language_scores_from_text(normalized: str, raw_text: str) -> tuple[int, int]:
    tokens = normalized.split()
    token_set = set(tokens)

    polish_score = 0
    english_score = 0

    if any(ch in raw_text for ch in POLISH_DIACRITICS):
        polish_score += 6

    for token in tokens:
        if token in POLISH_FUNCTION_WORDS:
            polish_score += 2
        if token in ENGLISH_FUNCTION_WORDS:
            english_score += 2
        if token in POLISH_CONTENT_WORDS:
            polish_score += 3
        if token in ENGLISH_CONTENT_WORDS:
            english_score += 3

    for phrase in POLISH_STRONG_PHRASES:
        if phrase in normalized:
            polish_score += 8

    for phrase in ENGLISH_STRONG_PHRASES:
        if phrase in normalized:
            english_score += 8

    if {"what", "time", "is", "it"}.issubset(token_set):
        english_score += 7
    if {"what", "is", "your", "name"}.issubset(token_set) or {"who", "are", "you"}.issubset(token_set):
        english_score += 7
    if {"turn", "off", "assistant"}.issubset(token_set):
        english_score += 8
    if {"turn", "off", "system"}.issubset(token_set):
        english_score += 9
    if {"turn", "off", "nexa"}.issubset(token_set):
        english_score += 9
    if {"can", "we", "talk"}.issubset(token_set):
        english_score += 8
    if {"i", "feel", "tired"}.issubset(token_set):
        english_score += 8

    if {"jak", "mozesz", "mi", "pomoc"}.issubset(token_set):
        polish_score += 10
    if {"co", "potrafisz"}.issubset(token_set):
        polish_score += 8
    if {"jak", "sie", "nazywasz"}.issubset(token_set):
        polish_score += 9
    if {"wylacz", "asystenta"}.issubset(token_set):
        polish_score += 8
    if {"wylacz", "system"}.issubset(token_set):
        polish_score += 9
    if {"wylacz", "nexa"}.issubset(token_set):
        polish_score += 9
    if {"mozemy", "porozmawiac", "chwile"}.issubset(token_set):
        polish_score += 10
    if {"jestem", "zmeczony"}.issubset(token_set) or {"jestem", "zmeczona"}.issubset(token_set):
        polish_score += 8
    if {"czuje", "sie", "zle"}.issubset(token_set):
        polish_score += 8

    if len(tokens) == 1:
        token = tokens[0]
        if token in STRONG_POLISH_SHORT:
            polish_score += 5
        if token in STRONG_ENGLISH_SHORT:
            english_score += 5

    return polish_score, english_score


def _ambiguous_language_fallback(assistant, normalized: str, polish_score: int, english_score: int) -> str:
    tokens = normalized.split()
    token_set = set(tokens)

    if token_set & STRONG_POLISH_SHORT and not (token_set & STRONG_ENGLISH_SHORT):
        return "pl"
    if token_set & STRONG_ENGLISH_SHORT and not (token_set & STRONG_POLISH_SHORT):
        return "en"

    if token_set & POLISH_FUNCTION_WORDS and not (token_set & ENGLISH_FUNCTION_WORDS):
        return "pl"
    if token_set & ENGLISH_FUNCTION_WORDS and not (token_set & POLISH_FUNCTION_WORDS):
        return "en"

    if polish_score > 0 and english_score == 0:
        return "pl"
    if english_score > 0 and polish_score == 0:
        return "en"

    last_language = getattr(assistant, "last_language", None)
    if last_language in {"pl", "en"}:
        return last_language

    return "en"


def detect_language(assistant, text: str) -> str:
    normalized = normalize_text(assistant, text)
    if not normalized:
        return assistant.last_language if getattr(assistant, "last_language", None) in {"pl", "en"} else "en"

    context_lang = _current_confirmation_language(assistant)
    if context_lang is not None:
        if _looks_like_confirmation(assistant, normalized):
            return context_lang
        if _extract_minutes_from_normalized(normalized) is not None and len(normalized.split()) <= 3:
            return context_lang

    polish_score, english_score = _language_scores_from_text(normalized, text)

    if polish_score >= english_score + 2:
        return "pl"
    if english_score >= polish_score + 2:
        return "en"

    return _ambiguous_language_fallback(assistant, normalized, polish_score, english_score)


def localized(lang: str, pl_text: str, en_text: str) -> str:
    return pl_text if lang == "pl" else en_text


def speak_localized(assistant, lang: str, pl_text: str, en_text: str) -> None:
    assistant.voice_out.speak(localized(lang, pl_text, en_text), language=lang)


def context_language(assistant, text: str, detected_lang: str) -> str:
    normalized = normalize_text(assistant, text)
    context_lang = _current_confirmation_language(assistant)

    if context_lang is None:
        return detected_lang

    if _looks_like_confirmation(assistant, normalized):
        return context_lang

    if _extract_minutes_from_normalized(normalized) is not None and len(normalized.split()) <= 3:
        return context_lang

    polish_score, english_score = _language_scores_from_text(normalized, text)

    if context_lang == "pl" and english_score >= polish_score + 4:
        return "en"
    if context_lang == "en" and polish_score >= english_score + 4:
        return "pl"

    if detected_lang in {"pl", "en"}:
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
    return _extract_minutes_from_normalized(normalized)


def is_yes(assistant, text: str) -> bool:
    return _classify_confirmation(assistant, text) == "yes"


def is_no(assistant, text: str) -> bool:
    return _classify_confirmation(assistant, text) == "no"