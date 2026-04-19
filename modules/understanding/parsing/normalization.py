from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable


YES_PHRASES = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "okay",
    "ok",
    "okay then",
    "of course",
    "correct",
    "right",
    "affirmative",
    "do it",
    "show it",
    "display it",
    "go ahead",
    "continue",
    "tak",
    "ta",
    "no tak",
    "jasne",
    "pewnie",
    "dobra",
    "dobrze",
    "okej",
    "ok",
    "zgoda",
    "zgadza sie",
    "zgadza się",
    "dokladnie",
    "dokładnie",
    "potwierdzam",
    "zrob to",
    "zrób to",
    "pokaz",
    "pokaż",
    "wyswietl",
    "wyświetl",
    "kontynuuj",
    "dalej",
}

NO_PHRASES = {
    "no",
    "nope",
    "nah",
    "not now",
    "cancel",
    "stop",
    "leave it",
    "do not",
    "do not show it",
    "dont show it",
    "don't show it",
    "never mind",
    "forget it",
    "nie",
    "nie teraz",
    "nie chce",
    "nie chcę",
    "anuluj",
    "stop",
    "zostaw to",
    "niewazne",
    "nieważne",
    "nie pokazuj",
    "nie wyswietlaj",
    "nie wyświetlaj",
    "odpusc",
    "odpuść",
}

CANCEL_PHRASES = {
    "cancel",
    "stop",
    "never mind",
    "nevermind",
    "forget it",
    "leave it",
    "drop it",
    "abort",
    "anuluj",
    "nieważne",
    "niewazne",
    "zostaw to",
    "zapomnij",
    "przestan",
    "przestań",
    "przerwij",
    "odpusc",
    "odpuść",
}

EXIT_PHRASES = {
    "exit",
    "quit",
    "close assistant",
    "exit assistant",
    "goodbye",
    "bye",
    "bye bye",
    "stop listening",
    "go to sleep",
    "sleep now",
    "sleep",
    "assistant sleep",
    "go idle",
    "stand by",
    "standby",
    "go standby",
    "wyjdz",
    "wyjdź",
    "zamknij asystenta",
    "do widzenia",
    "pa",
    "paa",
    "idz spac",
    "idź spać",
    "spij",
    "śpij",
    "uspij sie",
    "uśpij się",
    "tryb czuwania",
    "przejdz w czuwanie",
    "przejdź w czuwanie",
    "wroc do czuwania",
    "wróć do czuwania",
    "czuwanie",
    "standby mode",
}

STANDBY_PHRASES = {
    "sleep",
    "go to sleep",
    "sleep now",
    "stop listening",
    "stand by",
    "standby",
    "go standby",
    "go idle",
    "back to sleep",
    "return to standby",
    "idle mode",
    "spij",
    "śpij",
    "idz spac",
    "idź spać",
    "uspij sie",
    "uśpij się",
    "wroc do czuwania",
    "wróć do czuwania",
    "przejdz w czuwanie",
    "przejdź w czuwanie",
    "tryb czuwania",
    "czuwanie",
}

MICRO_REPLY_PHRASES = YES_PHRASES | NO_PHRASES | CANCEL_PHRASES | {
    "exit",
    "quit",
    "sleep",
    "standby",
    "ok",
    "okej",
    "okay",
    "dalej",
    "continue",
    "next",
    "stop listening",
    "go to sleep",
    "wróć do czuwania",
    "wroc do czuwania",
}

_SPOKEN_NUMBERS = {
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
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
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


def normalize_text(text: str) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return ""

    normalized = unicodedata.normalize("NFKD", raw)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("ł", "l")
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("'", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split() if token]


def contains_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    for phrase in phrases:
        normalized_phrase = normalize_text(str(phrase))
        if not normalized_phrase:
            continue
        if re.search(rf"(?:^|\s){re.escape(normalized_phrase)}(?:\s|$)", normalized):
            return True

    return False


def exact_phrase_match(text: str, phrases: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    return normalized in {normalize_text(str(item)) for item in phrases if str(item).strip()}


def is_yes(text: str) -> bool:
    return exact_phrase_match(text, YES_PHRASES)


def is_no(text: str) -> bool:
    return exact_phrase_match(text, NO_PHRASES)


def is_cancel_request(text: str) -> bool:
    return exact_phrase_match(text, CANCEL_PHRASES) or contains_any_phrase(text, CANCEL_PHRASES)


def is_exit_request(text: str) -> bool:
    return exact_phrase_match(text, EXIT_PHRASES) or contains_any_phrase(text, EXIT_PHRASES)


def is_standby_request(text: str) -> bool:
    return exact_phrase_match(text, STANDBY_PHRASES) or contains_any_phrase(text, STANDBY_PHRASES)


def is_micro_reply(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized in {normalize_text(item) for item in MICRO_REPLY_PHRASES}:
        return True
    return len(normalized.split()) <= 3 and contains_any_phrase(normalized, MICRO_REPLY_PHRASES)


def similarity_score(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)

    if not normalized_left or not normalized_right:
        return 0.0

    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))

    if not left_tokens or not right_tokens:
        return 0.0

    common = left_tokens & right_tokens
    if not common:
        return 0.0

    return float(len(common) / max(len(left_tokens), len(right_tokens)))


def best_similarity_against(text: str, candidates: Iterable[str]) -> tuple[str | None, float]:
    best_candidate: str | None = None
    best_score = 0.0

    for candidate in candidates:
        score = similarity_score(text, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate, best_score


def best_overlap_against(text: str, candidates: Iterable[str]) -> tuple[str | None, float]:
    best_candidate: str | None = None
    best_score = 0.0

    for candidate in candidates:
        score = token_overlap_score(text, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate, best_score


def normalize_for_fuzzy_key(text: str) -> str:
    normalized = normalize_text(text)
    normalized = strip_leading_fillers(normalized)
    normalized = singularize_last_token(normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def strip_leading_fillers(text: str) -> str:
    fillers = (
        "my ",
        "moje ",
        "moj ",
        "moja ",
        "the ",
        "a ",
        "an ",
        "number ",
        "numer ",
    )

    result = normalize_text(text)
    changed = True

    while changed:
        changed = False
        for filler in fillers:
            if result.startswith(filler):
                result = result[len(filler):].strip()
                changed = True

    return result


def singularize_last_token(text: str) -> str:
    tokens = tokenize(text)
    if not tokens:
        return ""

    last = tokens[-1]

    irregular = {
        "keys": "key",
        "phones": "phone",
        "numbers": "number",
        "klucze": "klucz",
        "telefony": "telefon",
    }

    if last in irregular:
        tokens[-1] = irregular[last]
        return " ".join(tokens)

    if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        tokens[-1] = last[:-1]

    return " ".join(tokens)


def extract_first_number(text: str) -> float | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    numeric_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", normalized)
    if numeric_match:
        try:
            return float(numeric_match.group(1).replace(",", "."))
        except ValueError:
            pass

    spoken_value = parse_spoken_number(normalized)
    if spoken_value is not None:
        return float(spoken_value)

    return None


def parse_spoken_number(text: str) -> int | None:
    tokens = tokenize(text)
    if not tokens:
        return None

    index = 0
    while index < len(tokens):
        current = tokens[index]
        current_value = _SPOKEN_NUMBERS.get(current)
        if current_value is None:
            index += 1
            continue

        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_value = _SPOKEN_NUMBERS.get(next_token)
            if next_value is not None and current_value >= 20 and next_value < 10:
                return current_value + next_value

        return current_value

    return None


def extract_duration_minutes(text: str) -> float | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    seconds_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds|sekunda|sekundy|sekund)\b",
        normalized,
    )
    if seconds_match:
        try:
            return max(float(seconds_match.group(1).replace(",", ".")) / 60.0, 1 / 60.0)
        except ValueError:
            return None

    minutes_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes|minuta|minuty|minut)\b",
        normalized,
    )
    if minutes_match:
        try:
            return float(minutes_match.group(1).replace(",", "."))
        except ValueError:
            return None

    numeric_value = extract_first_number(normalized)
    if numeric_value is not None:
        return numeric_value

    return None


def starts_with_show_intent(text: str) -> bool:
    normalized = normalize_text(text)
    prefixes = {
        "show",
        "display",
        "pokaz",
        "pokaż",
        "wyswietl",
        "wyświetl",
    }
    first_token = normalized.split()[0] if normalized else ""
    return first_token in {normalize_text(item) for item in prefixes}


__all__ = [
    "CANCEL_PHRASES",
    "EXIT_PHRASES",
    "MICRO_REPLY_PHRASES",
    "NO_PHRASES",
    "STANDBY_PHRASES",
    "YES_PHRASES",
    "best_overlap_against",
    "best_similarity_against",
    "clean_text",
    "contains_any_phrase",
    "exact_phrase_match",
    "extract_duration_minutes",
    "extract_first_number",
    "is_cancel_request",
    "is_exit_request",
    "is_micro_reply",
    "is_no",
    "is_standby_request",
    "is_yes",
    "normalize_for_fuzzy_key",
    "normalize_text",
    "parse_spoken_number",
    "similarity_score",
    "singularize_last_token",
    "starts_with_show_intent",
    "strip_leading_fillers",
    "token_overlap_score",
    "tokenize",
]