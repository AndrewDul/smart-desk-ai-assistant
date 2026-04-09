from __future__ import annotations

import random
import threading

from .acknowledgements import VoiceSessionAcknowledgements
from .constants import (
    _DEFAULT_CANCEL_PHRASES,
    _DEFAULT_THINKING_ACKS_EN,
    _DEFAULT_THINKING_ACKS_PL,
    _DEFAULT_WAKE_ACKS,
    VOICE_STATE_STANDBY,
)
from .matching import VoiceSessionMatching
from .models import VoiceSessionSnapshot
from .state import VoiceSessionState


class VoiceSessionController(
    VoiceSessionAcknowledgements,
    VoiceSessionState,
    VoiceSessionMatching,
):
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


__all__ = ["VoiceSessionController"]