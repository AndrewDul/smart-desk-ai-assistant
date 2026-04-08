from __future__ import annotations

import random
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field


VOICE_STATE_STANDBY = "standby"
VOICE_STATE_WAKE_DETECTED = "wake_detected"
VOICE_STATE_LISTENING = "listening"
VOICE_STATE_TRANSCRIBING = "transcribing"
VOICE_STATE_ROUTING = "routing"
VOICE_STATE_THINKING = "thinking"
VOICE_STATE_SPEAKING = "speaking"
VOICE_STATE_SHUTDOWN = "shutdown"

_VALID_STATES = {
    VOICE_STATE_STANDBY,
    VOICE_STATE_WAKE_DETECTED,
    VOICE_STATE_LISTENING,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_THINKING,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_SHUTDOWN,
}

_DEFAULT_WAKE_ACKS = (
    "Yes?",
    "I'm listening.",
    "I'm here.",
)

_DEFAULT_THINKING_ACKS_EN = (
    "Just a moment.",
    "Give me a second.",
    "I'm checking.",
    "Let me think.",
)

_DEFAULT_THINKING_ACKS_PL = (
    "Chwila moment.",
    "Daj mi sekundę.",
    "Już sprawdzam.",
    "Daj mi pomyśleć.",
)

_DEFAULT_CANCEL_PHRASES = (
    "cancel",
    "nevermind",
    "never mind",
    "forget it",
    "leave it",
    "drop it",
    "stop that",
    "stop this",
    "not important",
    "dont do it",
    "don't do it",
    "do not do it",
    "anuluj",
    "nieważne",
    "niewazne",
    "nie ważne",
    "nie wazne",
    "zapomnij",
    "zostaw to",
    "daj spokój",
    "daj spokoj",
    "nie rób tego",
    "nie rob tego",
    "nie ustawiaj",
    "nie włączaj",
    "nie wlaczaj",
    "nie uruchamiaj",
)


@dataclass(slots=True)
class VoiceSessionSnapshot:
    state: str
    active_until_monotonic: float = 0.0
    last_state_change_monotonic: float = field(default_factory=time.monotonic)
    detail: str = ""
    last_wake_detected_monotonic: float = 0.0
    last_command_accepted_monotonic: float = 0.0
    active_window_generation: int = 0

    @property
    def active_window_open(self) -> bool:
        return self.active_window_remaining_seconds > 0.0

    @property
    def active_window_remaining_seconds(self) -> float:
        remaining = self.active_until_monotonic - time.monotonic()
        return max(0.0, remaining)

    @property
    def state_age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.last_state_change_monotonic)


class VoiceSessionController:
    """
    Central voice-session state controller for NeXa.

    Responsibilities:
    - keep one authoritative interaction state
    - manage standby / wake / command / follow-up timing safely
    - normalize wake and cancel phrase detection with tolerant matching
    - keep wake stripping conservative so command text is not damaged
    - generate non-repeating wake and thinking acknowledgements
    - keep access thread-safe for the full runtime
    """

    _WAKE_RELATED_ALIASES = (
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    )

    _WAKE_BOUNDARY_FILLER_WORDS = {
        "hey",
        "hi",
        "hello",
        "ok",
        "okay",
        "yo",
        "please",
        "hej",
        "halo",
        "dobra",
        "okej",
        "okey",
        "prosze",
        "proszę",
    }

    _MAX_WAKE_ONLY_TOKENS = 3

    def __init__(
        self,
        *,
        wake_phrases: tuple[str, ...] = ("nexa",),
        wake_acknowledgements: tuple[str, ...] = _DEFAULT_WAKE_ACKS,
        active_listen_window_seconds: float = 8.0,
        thinking_ack_seconds: float = 1.5,
        cancel_phrases: tuple[str, ...] = _DEFAULT_CANCEL_PHRASES,
    ) -> None:
        normalized_wake_phrases = tuple(
            self._normalize_text(phrase)
            for phrase in wake_phrases
            if str(phrase).strip()
        )
        filtered_wake_phrases = tuple(
            phrase for phrase in normalized_wake_phrases if phrase
        ) or ("nexa",)

        self.wake_phrases = filtered_wake_phrases
        self.wake_acknowledgements = tuple(
            self._normalize_phrase_for_output(item)
            for item in wake_acknowledgements
            if str(item).strip()
        ) or _DEFAULT_WAKE_ACKS

        self.thinking_acknowledgements_en = tuple(
            self._normalize_phrase_for_output(item)
            for item in _DEFAULT_THINKING_ACKS_EN
        )
        self.thinking_acknowledgements_pl = tuple(
            self._normalize_phrase_for_output(item)
            for item in _DEFAULT_THINKING_ACKS_PL
        )

        self.cancel_phrases = tuple(
            phrase
            for phrase in (self._normalize_text(item) for item in cancel_phrases)
            if phrase
        ) or tuple(
            phrase
            for phrase in (self._normalize_text(item) for item in _DEFAULT_CANCEL_PHRASES)
            if phrase
        )

        self.active_listen_window_seconds = max(float(active_listen_window_seconds), 2.0)
        self.thinking_ack_seconds = max(float(thinking_ack_seconds), 0.8)

        self._lock = threading.RLock()
        self._rng = random.Random()
        self._last_wake_acknowledgement: str | None = None
        self._last_thinking_acknowledgement_by_language: dict[str, str | None] = {
            "en": None,
            "pl": None,
        }
        self._snapshot = VoiceSessionSnapshot(state=VOICE_STATE_STANDBY)

        self._wake_phrase_aliases = self._build_wake_aliases(self.wake_phrases)
        self._wake_phrase_patterns = tuple(
            self._build_phrase_pattern(phrase)
            for phrase in self._wake_phrase_aliases
        )
        self._wake_only_patterns = tuple(
            self._build_wake_only_pattern(phrase)
            for phrase in self._wake_phrase_aliases
        )
        self._cancel_patterns = tuple(
            self._build_phrase_pattern(phrase)
            for phrase in self.cancel_phrases
        )

    # ------------------------------------------------------------------
    # Snapshot and state
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._snapshot.state

    @property
    def state_detail(self) -> str:
        with self._lock:
            return self._snapshot.detail

    def snapshot(self) -> VoiceSessionSnapshot:
        with self._lock:
            return VoiceSessionSnapshot(
                state=self._snapshot.state,
                active_until_monotonic=self._snapshot.active_until_monotonic,
                last_state_change_monotonic=self._snapshot.last_state_change_monotonic,
                detail=self._snapshot.detail,
                last_wake_detected_monotonic=self._snapshot.last_wake_detected_monotonic,
                last_command_accepted_monotonic=self._snapshot.last_command_accepted_monotonic,
                active_window_generation=self._snapshot.active_window_generation,
            )

    def set_state(self, state: str, detail: str = "") -> None:
        normalized_state = str(state or "").strip().lower()
        if normalized_state not in _VALID_STATES:
            normalized_state = VOICE_STATE_STANDBY

        with self._lock:
            self._snapshot.state = normalized_state
            self._snapshot.detail = str(detail or "").strip()
            self._snapshot.last_state_change_monotonic = time.monotonic()

            if normalized_state == VOICE_STATE_WAKE_DETECTED:
                self._snapshot.last_wake_detected_monotonic = self._snapshot.last_state_change_monotonic

    def state_age_seconds(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self._snapshot.last_state_change_monotonic)

    # ------------------------------------------------------------------
    # Active listen window
    # ------------------------------------------------------------------

    def open_active_window(self, *, seconds: float | None = None) -> None:
        duration = self._resolve_window_seconds(seconds)
        now = time.monotonic()
        with self._lock:
            self._snapshot.active_until_monotonic = now + duration
            self._snapshot.active_window_generation += 1
            self._snapshot.state = VOICE_STATE_LISTENING
            self._snapshot.detail = "active_window_open"
            self._snapshot.last_state_change_monotonic = now

    def extend_active_window(self, *, seconds: float | None = None) -> None:
        duration = self._resolve_window_seconds(seconds)
        with self._lock:
            now = time.monotonic()
            current_deadline = max(self._snapshot.active_until_monotonic, now)
            self._snapshot.active_until_monotonic = current_deadline + duration

    def shorten_active_window(self, *, seconds: float) -> None:
        safe_seconds = max(float(seconds), 0.0)
        with self._lock:
            if self._snapshot.active_until_monotonic <= 0.0:
                return
            now = time.monotonic()
            target_deadline = now + safe_seconds
            self._snapshot.active_until_monotonic = min(
                self._snapshot.active_until_monotonic,
                target_deadline,
            )

    def close_active_window(self) -> None:
        with self._lock:
            self._snapshot.active_until_monotonic = 0.0
            self._snapshot.state = VOICE_STATE_STANDBY
            self._snapshot.detail = "active_window_closed"
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def active_window_open(self) -> bool:
        return self.active_window_remaining_seconds() > 0.0

    def active_window_remaining_seconds(self) -> float:
        with self._lock:
            remaining = self._snapshot.active_until_monotonic - time.monotonic()
            return max(0.0, remaining)

    def has_meaningful_active_window(self, *, minimum_seconds: float = 0.35) -> bool:
        return self.active_window_remaining_seconds() > max(0.0, float(minimum_seconds))

    def note_command_accepted(self) -> None:
        with self._lock:
            self._snapshot.last_command_accepted_monotonic = time.monotonic()

    # ------------------------------------------------------------------
    # Wake phrase handling
    # ------------------------------------------------------------------

    def heard_wake_phrase(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        if self._looks_like_wake_only_text(normalized):
            return True

        for pattern in self._wake_phrase_patterns:
            if pattern.search(normalized):
                return True

        compact = self._compact_text(normalized)
        if compact.startswith("nex") and len(compact) <= 8:
            return True

        return False

    def strip_wake_phrase(self, text: str) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""

        normalized = self._normalize_text(cleaned)
        if not normalized:
            return ""

        if self._looks_like_wake_only_text(normalized):
            return ""

        stripped = normalized
        for phrase in self._wake_phrase_aliases:
            pattern = self._build_phrase_pattern(phrase)
            stripped = pattern.sub(" ", stripped)

        stripped = re.sub(r"\s+", " ", stripped).strip(" ,.:;!?-")
        return stripped.strip()

    def build_wake_acknowledgement(self) -> str:
        with self._lock:
            chosen = self._choose_non_repeating_phrase(
                self.wake_acknowledgements,
                self._last_wake_acknowledgement,
                rng=self._rng,
            )
            self._last_wake_acknowledgement = chosen
            return chosen

    # ------------------------------------------------------------------
    # Thinking acknowledgement
    # ------------------------------------------------------------------

    def build_thinking_acknowledgement(self, language: str) -> str:
        normalized_language = self._normalize_language(language)
        phrase_pool = (
            self.thinking_acknowledgements_pl
            if normalized_language == "pl"
            else self.thinking_acknowledgements_en
        )

        with self._lock:
            previous = self._last_thinking_acknowledgement_by_language.get(normalized_language)
            chosen = self._choose_non_repeating_phrase(
                phrase_pool,
                previous,
                rng=self._rng,
            )
            self._last_thinking_acknowledgement_by_language[normalized_language] = chosen
            return chosen

    # ------------------------------------------------------------------
    # Cancel detection
    # ------------------------------------------------------------------

    def looks_like_cancel_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        for pattern in self._cancel_patterns:
            if pattern.search(normalized):
                return True
        return False

    # ------------------------------------------------------------------
    # Convenience state queries
    # ------------------------------------------------------------------

    def is_standby(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_STANDBY

    def is_listening(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_LISTENING

    def is_speaking(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_SPEAKING

    def is_busy(self) -> bool:
        with self._lock:
            return self._snapshot.state in {
                VOICE_STATE_WAKE_DETECTED,
                VOICE_STATE_LISTENING,
                VOICE_STATE_TRANSCRIBING,
                VOICE_STATE_ROUTING,
                VOICE_STATE_THINKING,
                VOICE_STATE_SPEAKING,
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_window_seconds(self, seconds: float | None) -> float:
        value = self.active_listen_window_seconds if seconds is None else float(seconds)
        return max(1.0, value)

    @staticmethod
    def _normalize_phrase_for_output(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    @staticmethod
    def _choose_non_repeating_phrase(
        phrases: tuple[str, ...] | list[str],
        previous: str | None,
        *,
        rng: random.Random | None = None,
    ) -> str:
        safe_rng = rng or random
        pool = [phrase for phrase in phrases if phrase and phrase != previous]
        if not pool:
            pool = [phrase for phrase in phrases if phrase]

        if not pool:
            return ""

        return safe_rng.choice(pool)

    @classmethod
    def _build_wake_aliases(cls, wake_phrases: tuple[str, ...]) -> tuple[str, ...]:
        aliases: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            normalized = cls._normalize_text(value)
            if normalized and normalized not in seen:
                aliases.append(normalized)
                seen.add(normalized)

        for phrase in wake_phrases:
            add(phrase)
            compact = cls._compact_text(phrase)
            if compact == "nexa" or phrase == "nexa":
                for alias in cls._WAKE_RELATED_ALIASES:
                    add(alias)

        return tuple(aliases) if aliases else ("nexa",)

    @classmethod
    def _build_phrase_pattern(cls, phrase: str) -> re.Pattern[str]:
        body = cls._phrase_to_flexible_body(phrase)
        if not body:
            return re.compile(r"$^")
        return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")

    @classmethod
    def _build_wake_only_pattern(cls, phrase: str) -> re.Pattern[str]:
        body = cls._phrase_to_flexible_body(phrase)
        if not body:
            return re.compile(r"$^")

        fillers = sorted((re.escape(word) for word in cls._WAKE_BOUNDARY_FILLER_WORDS), key=len, reverse=True)
        filler_group = r"(?:%s)" % "|".join(fillers) if fillers else r"(?:)"
        optional_prefix = rf"(?:{filler_group}\s+)?"
        optional_suffix = rf"(?:\s+{filler_group})?"
        return re.compile(rf"^\s*{optional_prefix}{body}{optional_suffix}\s*$")

    @classmethod
    def _phrase_to_flexible_body(cls, phrase: str) -> str:
        normalized = cls._normalize_text(phrase)
        parts = [re.escape(part) for part in normalized.split() if part]
        if not parts:
            return ""
        return r"[\s'-]*".join(parts)

    @classmethod
    def _looks_like_wake_only_text(cls, normalized_text: str) -> bool:
        tokens = [token for token in normalized_text.split() if token]
        if not tokens:
            return False

        if len(tokens) > cls._MAX_WAKE_ONLY_TOKENS:
            return False

        for pattern in (
            cls._build_wake_only_pattern(alias)
            for alias in cls._WAKE_RELATED_ALIASES
        ):
            if pattern.fullmatch(normalized_text):
                return True

        filtered_tokens = [
            token
            for token in tokens
            if token not in cls._WAKE_BOUNDARY_FILLER_WORDS
        ]
        if not filtered_tokens:
            return False

        return all(cls._is_wake_alias_token(token) for token in filtered_tokens)

    @classmethod
    def _is_wake_alias_token(cls, token: str) -> bool:
        compact = cls._compact_text(token)
        if not compact:
            return False
        if compact in {"nexa", "nexta", "neksa", "nexaah", "nex"}:
            return True
        return compact.startswith("nex") and len(compact) <= 8

    @staticmethod
    def _normalize_phrase_boundaries(text: str) -> str:
        normalized = str(text or "")
        normalized = re.sub(r"[_/\\|]+", " ", normalized)
        normalized = re.sub(r"[,:;!?]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _compact_text(text: str) -> str:
        normalized = VoiceSessionController._normalize_text(text)
        return re.sub(r"[^a-z0-9]", "", normalized)

    @staticmethod
    def _normalize_text(text: str) -> str:
        raw = str(text or "").strip().lower()
        if not raw:
            return ""

        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))

        normalized = normalized.replace("ł", "l")
        normalized = normalized.replace("ß", "ss")
        normalized = normalized.replace("’", "'")
        normalized = normalized.replace("`", "'")

        normalized = re.sub(r"[_/\\|]+", " ", normalized)
        normalized = re.sub(r"[.,:;!?()\[\]{}]+", " ", normalized)
        normalized = re.sub(r"[^a-z0-9\s'-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized


__all__ = [
    "VOICE_STATE_LISTENING",
    "VOICE_STATE_ROUTING",
    "VOICE_STATE_SHUTDOWN",
    "VOICE_STATE_SPEAKING",
    "VOICE_STATE_STANDBY",
    "VOICE_STATE_THINKING",
    "VOICE_STATE_TRANSCRIBING",
    "VOICE_STATE_WAKE_DETECTED",
    "VoiceSessionController",
    "VoiceSessionSnapshot",
]