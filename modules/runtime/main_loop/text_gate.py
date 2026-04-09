from __future__ import annotations

import re
import time
import unicodedata
from typing import TYPE_CHECKING

from modules.shared.logging.logger import append_log

from .constants import (
    ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS,
    DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS,
    MAX_ISOLATED_WAKE_TOKENS,
    MIN_INLINE_COMMAND_ALPHA_CHARS,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


def _normalize_gate_text(text: str) -> str:
    lowered = str(text or "").lower().strip()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = lowered.replace("ł", "l")
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    lowered = re.sub(r"[^a-z0-9\s\[\]().,_/-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _normalized_tokens(text: str) -> list[str]:
    return [token for token in _normalize_gate_text(text).split() if token]


def _alpha_char_count(text: str) -> int:
    return len(re.sub(r"[^a-z]", "", _normalize_gate_text(text)))


def _looks_like_wake_alias(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return False

    compact_tokens = [re.sub(r"[^a-z0-9]", "", token) for token in normalized.split()[:3]]
    wake_aliases = {
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    }
    return any(token in wake_aliases or token.startswith("nex") for token in compact_tokens if token)


def _all_tokens_look_like_wake_aliases(tokens: list[str]) -> bool:
    return bool(tokens) and all(_looks_like_wake_alias(token) for token in tokens)


def _looks_like_isolated_wake_transcript(text: str) -> bool:
    tokens = _normalized_tokens(text)
    if not tokens or len(tokens) > MAX_ISOLATED_WAKE_TOKENS:
        return False
    return _all_tokens_look_like_wake_aliases(tokens)


def _is_blank_or_silence(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    return normalized in {
        "",
        "blank audio",
        "[blank_audio]",
        "blank_audio",
        "silence",
        "[ silence ]",
        "no speech",
        "no speech recognized",
        "[noise]",
        "noise",
        "<empty>",
        "...",
        ".",
        "-",
    }


def _is_bracketed_non_speech(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    bracketed_patterns = [
        r"^\[[a-z0-9 _-]+\]$",
        r"^\([a-z0-9 _-]+\)$",
    ]
    if not any(re.fullmatch(pattern, normalized) for pattern in bracketed_patterns):
        return False

    inner = re.sub(r"^[\[(]|[\])]\Z", "", normalized).strip()
    non_speech_terms = {
        "music",
        "upbeat music",
        "applause",
        "laughter",
        "background noise",
        "ambient sound",
        "static",
        "noise",
        "silence",
        "coughing",
        "breathing",
        "sigh",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }
    return inner in non_speech_terms


def _looks_like_non_speech_description(normalized: str) -> bool:
    if not normalized:
        return True

    exact_non_speech = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "applause",
        "music",
        "laughter",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }
    if normalized in exact_non_speech:
        return True

    non_speech_keywords = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "klawiatura",
        "krzeslo",
        "klasniecie",
        "klaskanie",
    }

    tokens = set(normalized.split())
    if tokens and tokens.issubset(non_speech_keywords):
        return True
    if len(tokens) <= 4 and (tokens & non_speech_keywords):
        return True
    return False


def _is_low_value_noise(text: str, assistant: CoreAssistant) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    filler_words = {
        "uh",
        "um",
        "hmm",
        "hm",
        "mmm",
        "ah",
        "eh",
        "yyy",
        "eee",
        "ok",
        "okay",
        "huh",
    }
    silence_hallucinations = {
        "thank you",
        "thanks for watching",
        "you",
        "bye",
        "foreign",
        "speaking in foreign language",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }

    if normalized in filler_words or normalized in silence_hallucinations:
        return True

    if _looks_like_non_speech_description(normalized):
        return True
    if not re.search(r"[a-z]", normalized):
        return True

    alpha_only = re.sub(r"[^a-z]", "", normalized)
    return len(alpha_only) <= 1


def _has_meaningful_inline_command(text: str, assistant: CoreAssistant) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return False
    if _is_blank_or_silence(text):
        return False
    if _is_bracketed_non_speech(text):
        return False
    if _is_low_value_noise(text, assistant):
        return False

    tokens = _normalized_tokens(text)
    if _all_tokens_look_like_wake_aliases(tokens):
        return False

    return _alpha_char_count(text) >= MIN_INLINE_COMMAND_ALPHA_CHARS


def _sanitize_inline_command(text: str | None, assistant: CoreAssistant) -> str | None:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return None
    if not _has_meaningful_inline_command(cleaned, assistant):
        return None
    return cleaned


def _should_ignore_duplicate_transcript(
    text: str,
    assistant: CoreAssistant,
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
    cooldown_seconds: float = DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS,
) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized or last_transcript_normalized is None or last_transcript_time is None:
        return False

    return (
        normalized == last_transcript_normalized
        and (time.monotonic() - last_transcript_time) <= cooldown_seconds
    )


def _should_log_gate_event(
    gate_event: str,
    gate_log_times: dict[str, float],
    cooldown_seconds: float = ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS,
) -> bool:
    now = time.monotonic()
    last_time = gate_log_times.get(gate_event)
    if last_time is None or (now - last_time) >= cooldown_seconds:
        gate_log_times[gate_event] = now
        return True
    return False


def _log_ignored_active_transcript(
    event_key: str,
    heard_text: str,
    gate_log_times: dict[str, float],
    message: str,
) -> None:
    if _should_log_gate_event(event_key, gate_log_times):
        append_log(f"Ignored active transcript [{event_key}]: {heard_text}")
    print(message)


def _should_ignore_active_transcript(
    assistant: CoreAssistant,
    heard_text: str,
    gate_log_times: dict[str, float],
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
) -> bool:
    if _is_blank_or_silence(heard_text):
        _log_ignored_active_transcript(
            "blank_or_silence",
            heard_text,
            gate_log_times,
            "Ignored blank audio marker.",
        )
        return True

    normalized_heard = _normalize_gate_text(heard_text)
    if not normalized_heard:
        _log_ignored_active_transcript(
            "empty_normalized",
            heard_text,
            gate_log_times,
            "Ignored empty normalized transcript.",
        )
        return True

    if _is_bracketed_non_speech(heard_text):
        _log_ignored_active_transcript(
            "bracketed_non_speech",
            heard_text,
            gate_log_times,
            f"Ignored non-speech transcript: {heard_text}",
        )
        return True

    if _is_low_value_noise(heard_text, assistant):
        _log_ignored_active_transcript(
            "low_value_noise",
            heard_text,
            gate_log_times,
            f"Ignored low-value noise: {heard_text}",
        )
        return True

    if _should_ignore_duplicate_transcript(
        heard_text,
        assistant,
        last_transcript_normalized=last_transcript_normalized,
        last_transcript_time=last_transcript_time,
    ):
        _log_ignored_active_transcript(
            "duplicate_transcript",
            heard_text,
            gate_log_times,
            f"Ignored duplicate transcript: {heard_text}",
        )
        return True

    return False