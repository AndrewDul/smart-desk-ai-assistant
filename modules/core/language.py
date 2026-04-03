from __future__ import annotations

import re
import unicodedata


POLISH_DIACRITICS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"

POLISH_FUNCTION_WORDS = {
    "czy",
    "jak",
    "co",
    "gdzie",
    "ktora",
    "ktorej",
    "jaka",
    "jaki",
    "jest",
    "sa",
    "moge",
    "mozesz",
    "pomoc",
    "mi",
    "to",
    "za",
    "o",
    "w",
    "na",
    "pod",
    "przy",
    "dzisiaj",
    "teraz",
    "sie",
    "masz",
    "mam",
    "dla",
    "ze",
}

ENGLISH_FUNCTION_WORDS = {
    "what",
    "whats",
    "how",
    "can",
    "could",
    "would",
    "you",
    "your",
    "me",
    "my",
    "the",
    "to",
    "about",
    "in",
    "on",
    "at",
    "after",
    "now",
    "today",
    "please",
    "is",
    "are",
    "do",
}

POLISH_CONTENT_WORDS = {
    "asystent",
    "asystenta",
    "pomoc",
    "potrafisz",
    "umiesz",
    "godzina",
    "godzine",
    "czas",
    "data",
    "dzien",
    "rok",
    "przypomnij",
    "przypomnienie",
    "przypomnienia",
    "zapamietaj",
    "pamietasz",
    "pamiec",
    "zapomnij",
    "usun",
    "wyczysc",
    "timer",
    "focus",
    "przerwa",
    "skupienie",
    "pokaz",
    "wyswietl",
    "wylacz",
    "zamknij",
    "idz",
    "spac",
    "odpocznij",
    "sluchac",
    "imie",
    "nazywasz",
    "ktora",
    "ktory",
    "ktore",
    "mozliwosci",
    "komendy",
    "ekranie",
    "klucze",
    "kuchni",
    "zjesc",
}

ENGLISH_CONTENT_WORDS = {
    "assistant",
    "help",
    "time",
    "date",
    "day",
    "year",
    "remind",
    "reminder",
    "reminders",
    "remember",
    "memory",
    "forget",
    "delete",
    "remove",
    "clear",
    "timer",
    "focus",
    "break",
    "show",
    "display",
    "turn",
    "off",
    "sleep",
    "rest",
    "listening",
    "name",
    "introduce",
    "shutdown",
    "system",
    "screen",
    "menu",
    "capabilities",
    "features",
    "clock",
    "keys",
    "kitchen",
    "eat",
}

POLISH_STRONG_PHRASES = {
    "jak mozesz mi pomoc",
    "w czym mozesz mi pomoc",
    "co potrafisz",
    "co umiesz",
    "jak sie nazywasz",
    "kim jestes",
    "czym jestes",
    "wylacz asystenta",
    "idz spac",
    "odpocznij",
    "pokaz godzine",
    "pokaz mi godzine",
    "jaka jest godzina",
    "ktora jest godzina",
    "jaka jest data",
    "pokaz date",
    "pokaz dzien",
    "pokaz rok",
    "pokaz mi date",
    "pokaz mi dzien",
    "pokaz mi rok",
    "usun z pamieci",
    "usun klucze z pamieci",
    "zapamietaj ze",
    "zapamietaj gdzie sa",
    "gdzie sa klucze",
    "przypomnij mi za",
}

ENGLISH_STRONG_PHRASES = {
    "how can you help me",
    "what can you do",
    "what can i ask you",
    "what is your name",
    "whats your name",
    "who are you",
    "what are you",
    "turn off assistant",
    "go to sleep",
    "rest now",
    "what time is it",
    "show time",
    "show date",
    "show day",
    "show year",
    "show me the time",
    "show me the date",
    "show me the day",
    "show me the year",
    "forget from memory",
    "remove keys from memory",
    "remember that",
    "where are the keys",
    "remind me in",
    "remind me after",
}

STRONG_POLISH_SHORT = {
    "pomoc",
    "godzina",
    "czas",
    "data",
    "dzien",
    "rok",
    "przerwa",
    "pamiec",
    "przypomnienia",
    "pokaz",
    "wyswietl",
    "wylacz",
    "odpocznij",
    "zapamietaj",
    "przypomnij",
    "klucze",
}

STRONG_ENGLISH_SHORT = {
    "help",
    "time",
    "date",
    "day",
    "year",
    "break",
    "memory",
    "reminders",
    "show",
    "display",
    "shutdown",
    "remember",
    "remind",
    "assistant",
    "keys",
}

POLISH_FUZZY_CONFIRM_YES = {"tag", "tac", "takg", "tek", "tok"}
POLISH_FUZZY_CONFIRM_NO = {"ni", "ne", "nje", "nee"}


def _fallback_normalize_text(text: str) -> str:
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
        "nieważne",
        "nie pokazuj",
        "nie wyswietlaj",
        "nie wyświetlaj",
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

    polish_yes_strong = {
        "tak",
        "taaak",
        "takkk",
        "jasne",
        "pewnie",
        "dokladnie",
        "dokładnie",
        "zgadza sie",
        "zgadza się",
        "potwierdzam",
    }
    polish_yes_soft = {
        "no jasne",
        "oczywiscie",
        "oczywiście",
    }

    polish_no_strong = {
        "nie",
        "niee",
        "nieee",
        "anuluj",
        "zostaw to",
        "niewazne",
        "nieważne",
        "nie teraz",
        "nie pokazuj",
        "nie wyswietlaj",
        "nie wyświetlaj",
    }

    english_yes_strong = {
        "yes",
        "yeah",
        "yep",
        "sure",
        "correct",
        "of course",
        "do it",
        "show it",
        "display it",
    }
    english_no_strong = {
        "no",
        "nope",
        "cancel",
        "stop",
        "leave it",
        "never mind",
        "dont show it",
        "do not show it",
    }

    if context_lang == "pl":
        if normalized in polish_no_strong or normalized in POLISH_FUZZY_CONFIRM_NO:
            return "no"
        if normalized in polish_yes_strong or normalized in polish_yes_soft or normalized in POLISH_FUZZY_CONFIRM_YES:
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
        if normalized in english_no_strong:
            return "no"
        if normalized in english_yes_strong:
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
        english_score += 6
    if {"how", "can", "you", "help", "me"}.issubset(token_set):
        english_score += 7
    if {"what", "is", "your", "name"}.issubset(token_set) or {"who", "are", "you"}.issubset(token_set):
        english_score += 7
    if {"what", "are", "you"}.issubset(token_set):
        english_score += 7
    if {"turn", "off", "assistant"}.issubset(token_set) or {"go", "sleep"}.issubset(token_set):
        english_score += 7
    if {"show", "me", "the", "time"}.issubset(token_set):
        english_score += 8

    if {"jak", "mozesz", "mi", "pomoc"}.issubset(token_set):
        polish_score += 10
    if {"w", "czym", "mozesz", "mi", "pomoc"}.issubset(token_set):
        polish_score += 10
    if {"co", "potrafisz"}.issubset(token_set):
        polish_score += 8
    if {"jak", "sie", "nazywasz"}.issubset(token_set):
        polish_score += 9
    if {"kim", "jestes"}.issubset(token_set) or {"czym", "jestes"}.issubset(token_set):
        polish_score += 9
    if {"wylacz", "asystenta"}.issubset(token_set) or {"idz", "spac"}.issubset(token_set):
        polish_score += 7
    if {"ktora", "jest", "godzina"}.issubset(token_set) or {"jaka", "jest", "godzina"}.issubset(token_set):
        polish_score += 8
    if {"pokaz", "mi", "godzine"}.issubset(token_set):
        polish_score += 9
    if {"zapamietaj", "ze"}.issubset(token_set):
        polish_score += 8
    if {"gdzie", "sa", "klucze"}.issubset(token_set):
        polish_score += 8
    if {"przypomnij", "mi", "za"}.issubset(token_set):
        polish_score += 8
    if {"usun", "klucze", "z", "pamieci"}.issubset(token_set):
        polish_score += 10

    if len(tokens) == 1:
        token = tokens[0]
        if token in STRONG_ENGLISH_SHORT:
            english_score += 5
        if token in STRONG_POLISH_SHORT:
            polish_score += 5

    return polish_score, english_score


def _ambiguous_language_fallback(assistant, normalized: str, polish_score: int, english_score: int) -> str:
    tokens = normalized.split()
    token_set = set(tokens)

    if token_set & STRONG_POLISH_SHORT:
        return "pl"
    if token_set & STRONG_ENGLISH_SHORT:
        return "en"

    if token_set & POLISH_FUNCTION_WORDS and not (token_set & ENGLISH_FUNCTION_WORDS):
        return "pl"
    if token_set & ENGLISH_FUNCTION_WORDS and not (token_set & POLISH_FUNCTION_WORDS):
        return "en"

    if polish_score > 0 and english_score == 0:
        return "pl"
    if english_score > 0 and polish_score == 0:
        return "en"

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