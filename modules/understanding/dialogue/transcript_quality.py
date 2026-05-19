"""
Transcript quality gate and safe correction for conversation/LLM routes.

Rejects obviously corrupted ASR output before it reaches the LLM.
Applies known-safe corrections when query structure is strong.
Asks for clarification when the question is structurally intact but missing its object.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from modules.shared.logging.logger import append_log


@dataclass(slots=True)
class TranscriptQualityResult:
    is_acceptable: bool
    corrected_text: str
    correction_applied: bool = False
    correction_reason: str = ""
    rejection_reason: str = ""
    repeat_text_pl: str = "Nie jestem pewna, czy dobrze usłyszałam. Możesz powtórzyć pytanie trochę wyraźniej?"
    repeat_text_en: str = "I'm not sure I heard that correctly. Can you repeat the question a bit more clearly?"


class _Correction(NamedTuple):
    pattern: re.Pattern[str]
    replacement: str
    reason: str


class _IncompletePattern(NamedTuple):
    pattern: re.Pattern[str]
    clarification_en: str
    clarification_pl: str
    reason: str


_CORRECTIONS_PL: tuple[_Correction, ...] = (
    _Correction(
        re.compile(r"\bplanka\s+(\w+)", re.IGNORECASE),
        r"prędkość \1",
        "planka→prędkość (Planck ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bplanka\b", re.IGNORECASE),
        "prędkość",
        "planka→prędkość (Planck ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bjak\s+szybkej\s+(\w+)", re.IGNORECASE),
        r"jak szybkie jest \1",
        "szybkej→szybkie jest (inflection ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bjak\s+szybkie\s+(?!jest\b)(\w+)", re.IGNORECASE),
        r"jak szybkie jest \1",
        "jak szybkie→jak szybkie jest (missing jest)",
    ),
    _Correction(
        re.compile(r"\bte?\s*leport\w*\b", re.IGNORECASE),
        "teleportacja",
        "leport*→teleportacja (word-split ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bczarnadzur\w*\b", re.IGNORECASE),
        "czarna dziura",
        "czarnadzura→czarna dziura (word-merge ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bprędkość\s+(?:swiatla|świała|świadł|swiadl|swiatl)\b", re.IGNORECASE),
        "prędkość światła",
        "swiatla/świała/świadł/swiadl/swiatl→światła (diacritics/truncation ASR mishear)",
    ),
)

_CORRECTIONS_EN: tuple[_Correction, ...] = (
    _Correction(
        re.compile(r"\bspeed\s+of\s+(?:life|live|lite)\b", re.IGNORECASE),
        "speed of light",
        "life/live/lite→light (ASR mishear)",
    ),
    _Correction(
        re.compile(r"\bblack\s+whole\b", re.IGNORECASE),
        "black hole",
        "whole→hole (ASR mishear)",
    ),
    _Correction(
        re.compile(r"\btele\s+port\w*\b", re.IGNORECASE),
        "teleportation",
        "tele port→teleportation (word-split ASR mishear)",
    ),
)

# Patterns for structurally intact questions that are missing their object.
# Checked on the CORRECTED text so corrections run first.
_INCOMPLETE_PATTERNS_EN: tuple[_IncompletePattern, ...] = (
    _IncompletePattern(
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?speed\s+of\s*[?!.]*$", re.IGNORECASE),
        "Speed of what? Can you repeat the full question?",
        "Prędkość czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_speed_of_en",
    ),
    _IncompletePattern(
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?speed\s*[?!.]*$", re.IGNORECASE),
        "Speed of what? Can you repeat the full question?",
        "Prędkość czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_speed_en",
    ),
    _IncompletePattern(
        re.compile(r"^how\s+fast\s+is\s*(?:it\s*)?[?!.]*$", re.IGNORECASE),
        "How fast is what, exactly? Can you repeat the full question?",
        "Jak szybkie jest co dokładnie? Możesz powtórzyć pełne pytanie?",
        "incomplete_how_fast_en",
    ),
    _IncompletePattern(
        re.compile(r"^how\s+big\s+is\s*(?:it\s*)?[?!.]*$", re.IGNORECASE),
        "How big is what, exactly? Can you repeat the full question?",
        "Jak duże jest co dokładnie? Możesz powtórzyć pełne pytanie?",
        "incomplete_how_big_en",
    ),
    _IncompletePattern(
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?temperature\s*[?!.]*$", re.IGNORECASE),
        "Temperature of what? Can you repeat the full question?",
        "Temperatura czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_temperature_en",
    ),
    _IncompletePattern(
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:mass|weight|size|distance|height|age)\s*[?!.]*$", re.IGNORECASE),
        "Of what? Can you repeat the full question?",
        "Czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_quantity_en",
    ),
)

_INCOMPLETE_PATTERNS_PL: tuple[_IncompletePattern, ...] = (
    _IncompletePattern(
        re.compile(r"^jaka\s+jest\s+prędkość\s*[?!.]*$", re.IGNORECASE),
        "Speed of what? Can you repeat the full question?",
        "Prędkość czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_speed_pl",
    ),
    _IncompletePattern(
        re.compile(r"^jak\s+szybki?e?\s+jest\s*[?!.]*$", re.IGNORECASE),
        "How fast is what, exactly? Can you repeat the full question?",
        "Jak szybkie jest co dokładnie? Możesz powtórzyć pełne pytanie?",
        "incomplete_how_fast_pl",
    ),
    _IncompletePattern(
        re.compile(r"^jak\s+duż[ae]?\s+jest\s*[?!.]*$", re.IGNORECASE),
        "How big is what, exactly? Can you repeat the full question?",
        "Jak duże jest co dokładnie? Możesz powtórzyć pełne pytanie?",
        "incomplete_how_big_pl",
    ),
    _IncompletePattern(
        re.compile(r"^jaka\s+jest\s+(?:temperatura|masa|waga|odległość|wysokość)\s*[?!.]*$", re.IGNORECASE),
        "Of what? Can you repeat the full question?",
        "Czego? Możesz powtórzyć pełne pytanie?",
        "incomplete_quantity_pl",
    ),
)

_QUESTION_OPENERS_PL: tuple[str, ...] = (
    "co to jest",
    "co to są",
    "czym jest",
    "czym są",
    "jaka jest",
    "jaki jest",
    "jak szybkie",
    "jak duże",
    "jak działa",
    "powiedz mi o",
    "wyjaśnij",
    "dlaczego",
)
_QUESTION_OPENERS_EN: tuple[str, ...] = (
    "what is",
    "what are",
    "what were",
    "how does",
    "how fast",
    "how big",
    "how many",
    "tell me about",
    "explain",
    "why is",
    "why are",
    "who is",
    "where is",
)

_ONE_TOKEN_FOLLOW_UPS_EN = frozenset({"why", "how", "what", "when", "where"})
_ONE_TOKEN_FOLLOW_UPS_PL = frozenset({"czemu", "dlaczego", "jak", "co", "kiedy", "gdzie"})


def _tokenize(text: str) -> list[str]:
    """Return lower-case alphabetic tokens (strip punctuation, numbers)."""
    return [t for t in re.split(r"[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", text.lower()) if t]


def _max_run_short(tokens: list[str], max_chars: int = 3) -> int:
    """Return the maximum consecutive run of tokens all ≤ max_chars long."""
    best = cur = 0
    for tok in tokens:
        if len(tok) <= max_chars:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _check_rejection(tokens: list[str], text_lower: str, language: str) -> str:
    """Return a non-empty rejection reason string if the transcript should be rejected."""
    is_polish = str(language or "").lower().startswith("pl")
    if len(tokens) < 2:
        follow_ups = _ONE_TOKEN_FOLLOW_UPS_PL if is_polish else _ONE_TOKEN_FOLLOW_UPS_EN
        if len(tokens) == 1 and tokens[0] in follow_ups:
            return ""
        return "too_few_words"

    openers = _QUESTION_OPENERS_PL if is_polish else _QUESTION_OPENERS_EN

    opener_word_count = 0
    for opener in openers:
        if text_lower.startswith(opener):
            opener_word_count = len(opener.split())
            break

    # Only flag "all short fragments" when no recognized question opener anchors the sentence.
    if opener_word_count == 0 and all(len(t) <= 3 for t in tokens):
        return "all_fragments_short"

    # Check words AFTER the opener for a burst of ≥4 consecutive short fragments.
    check_tokens = tokens[opener_word_count:]
    if _max_run_short(check_tokens, 3) >= 4:
        return "consecutive_fragment_burst"

    return ""


def _check_incomplete_question(text: str, language: str) -> _IncompletePattern | None:
    """Return an _IncompletePattern if the text is a known truncated factual question."""
    is_polish = str(language or "").lower().startswith("pl")
    patterns = _INCOMPLETE_PATTERNS_PL if is_polish else _INCOMPLETE_PATTERNS_EN
    stripped = text.strip()
    for pat in patterns:
        if pat.pattern.match(stripped):
            return pat
    return None


def check_and_correct(text: str, language: str) -> TranscriptQualityResult:
    """
    Run quality gate and safe corrections on ASR transcript text.

    Returns TranscriptQualityResult. If is_acceptable is False, the caller
    should respond with repeat_text_pl / repeat_text_en instead of routing to LLM.
    """
    cleaned = text.strip()
    if not cleaned:
        return TranscriptQualityResult(
            is_acceptable=False,
            corrected_text=cleaned,
            rejection_reason="empty_transcript",
        )

    tokens = _tokenize(cleaned)
    rejection = _check_rejection(tokens, cleaned.lower(), language)

    if rejection:
        append_log(
            f"[transcript-gate] rejected reason={rejection} language={language} "
            f'text="{cleaned[:80]}"'
        )
        return TranscriptQualityResult(
            is_acceptable=False,
            corrected_text=cleaned,
            rejection_reason=rejection,
        )

    is_polish = str(language or "").lower().startswith("pl")
    corrections = _CORRECTIONS_PL if is_polish else _CORRECTIONS_EN

    corrected = cleaned
    applied_reason = ""
    for corr in corrections:
        new_text, n_subs = corr.pattern.subn(corr.replacement, corrected)
        if n_subs > 0:
            corrected = new_text
            applied_reason = corr.reason
            break

    if applied_reason:
        append_log(
            f"[transcript-normalization] original={cleaned!r} "
            f"corrected={corrected!r} reason={applied_reason}"
        )

    # Check AFTER corrections: structurally intact question missing its object.
    incomplete = _check_incomplete_question(corrected, language)
    if incomplete is not None:
        append_log(
            f"[transcript-gate] rejected reason={incomplete.reason} language={language} "
            f'text="{corrected[:80]}"'
        )
        return TranscriptQualityResult(
            is_acceptable=False,
            corrected_text=corrected,
            rejection_reason=incomplete.reason,
            repeat_text_pl=incomplete.clarification_pl,
            repeat_text_en=incomplete.clarification_en,
        )

    return TranscriptQualityResult(
        is_acceptable=True,
        corrected_text=corrected,
        correction_applied=bool(applied_reason),
        correction_reason=applied_reason,
    )


__all__ = ["TranscriptQualityResult", "check_and_correct"]
