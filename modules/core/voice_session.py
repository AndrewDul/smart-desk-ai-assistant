from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field


VOICE_STATE_STANDBY = "standby"
VOICE_STATE_WAKE_DETECTED = "wake_detected"
VOICE_STATE_LISTENING = "listening"
VOICE_STATE_TRANSCRIBING = "transcribing"
VOICE_STATE_ROUTING = "routing"
VOICE_STATE_THINKING = "thinking"
VOICE_STATE_SPEAKING = "speaking"
VOICE_STATE_SHUTDOWN = "shutdown"


_DEFAULT_WAKE_ACKS = (
    "Yes?",
    "I'm listening.",
    "I'm here.",
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
    "don't do it",
    "dont do it",
    "do not do it",
)


@dataclass(slots=True)
class VoiceSessionSnapshot:
    state: str
    active_until_monotonic: float = 0.0
    last_state_change_monotonic: float = field(default_factory=time.monotonic)
    detail: str = ""


class VoiceSessionController:
    """
    Lightweight controller for premium voice-session behaviour.

    Goals:
    - keep NeXa in passive standby until wake phrase is heard
    - provide non-repeating wake acknowledgements
    - expose a short active listening window after wake-up
    - expose explicit interaction states for UI / logging
    - centralize generic "cancel this task" phrase detection
    """

    def __init__(
        self,
        *,
        wake_phrases: tuple[str, ...] = ("nexa",),
        wake_acknowledgements: tuple[str, ...] = _DEFAULT_WAKE_ACKS,
        active_listen_window_seconds: float = 8.0,
        thinking_ack_seconds: float = 1.5,
    ) -> None:
        normalized_wake_phrases = tuple(
            self._normalize_text(phrase)
            for phrase in wake_phrases
            if str(phrase).strip()
        )
        self.wake_phrases = tuple(phrase for phrase in normalized_wake_phrases if phrase) or ("nexa",)

        self.wake_acknowledgements = tuple(
            str(item).strip()
            for item in wake_acknowledgements
            if str(item).strip()
        ) or _DEFAULT_WAKE_ACKS

        self.active_listen_window_seconds = max(float(active_listen_window_seconds), 2.0)
        self.thinking_ack_seconds = max(float(thinking_ack_seconds), 0.8)

        self._rng = random.Random()
        self._last_wake_acknowledgement: str | None = None
        self._snapshot = VoiceSessionSnapshot(state=VOICE_STATE_STANDBY)

    @property
    def state(self) -> str:
        return self._snapshot.state

    @property
    def state_detail(self) -> str:
        return self._snapshot.detail

    def snapshot(self) -> VoiceSessionSnapshot:
        return VoiceSessionSnapshot(
            state=self._snapshot.state,
            active_until_monotonic=self._snapshot.active_until_monotonic,
            last_state_change_monotonic=self._snapshot.last_state_change_monotonic,
            detail=self._snapshot.detail,
        )

    def set_state(self, state: str, detail: str = "") -> None:
        self._snapshot.state = str(state or VOICE_STATE_STANDBY).strip().lower() or VOICE_STATE_STANDBY
        self._snapshot.detail = str(detail or "").strip()
        self._snapshot.last_state_change_monotonic = time.monotonic()

    def open_active_window(self, *, seconds: float | None = None) -> None:
        duration = float(seconds) if seconds is not None else self.active_listen_window_seconds
        duration = max(duration, 1.0)
        self._snapshot.active_until_monotonic = time.monotonic() + duration
        self.set_state(VOICE_STATE_LISTENING, detail="active_window_open")

    def extend_active_window(self, *, seconds: float | None = None) -> None:
        duration = float(seconds) if seconds is not None else self.active_listen_window_seconds
        duration = max(duration, 1.0)
        now = time.monotonic()
        current_deadline = max(self._snapshot.active_until_monotonic, now)
        self._snapshot.active_until_monotonic = current_deadline + duration

    def close_active_window(self) -> None:
        self._snapshot.active_until_monotonic = 0.0
        self.set_state(VOICE_STATE_STANDBY, detail="active_window_closed")

    def active_window_open(self) -> bool:
        return time.monotonic() <= self._snapshot.active_until_monotonic

    def heard_wake_phrase(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        tokens = set(normalized.split())

        for phrase in self.wake_phrases:
            if phrase in normalized:
                return True

            phrase_tokens = tuple(part for part in phrase.split() if part)
            if phrase_tokens and all(part in tokens for part in phrase_tokens):
                return True

        return False

    def strip_wake_phrase(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        stripped = cleaned
        for phrase in self.wake_phrases:
            pattern = re.compile(rf"\b{re.escape(phrase)}\b[\s,.:;!?-]*", flags=re.IGNORECASE)
            stripped = pattern.sub("", stripped, count=1)

        return " ".join(stripped.split()).strip()

    def build_wake_acknowledgement(self) -> str:
        pool = [
            phrase
            for phrase in self.wake_acknowledgements
            if phrase != self._last_wake_acknowledgement
        ] or list(self.wake_acknowledgements)

        chosen = self._rng.choice(pool)
        self._last_wake_acknowledgement = chosen
        return chosen

    def looks_like_cancel_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        return any(marker in normalized for marker in _DEFAULT_CANCEL_PHRASES)

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return ""

        lowered = lowered.replace("ł", "l")
        lowered = lowered.replace("ą", "a")
        lowered = lowered.replace("ć", "c")
        lowered = lowered.replace("ę", "e")
        lowered = lowered.replace("ń", "n")
        lowered = lowered.replace("ó", "o")
        lowered = lowered.replace("ś", "s")
        lowered = lowered.replace("ż", "z")
        lowered = lowered.replace("ź", "z")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered