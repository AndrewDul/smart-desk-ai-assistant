from __future__ import annotations

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

__all__ = [
    "VOICE_STATE_STANDBY",
    "VOICE_STATE_WAKE_DETECTED",
    "VOICE_STATE_LISTENING",
    "VOICE_STATE_TRANSCRIBING",
    "VOICE_STATE_ROUTING",
    "VOICE_STATE_THINKING",
    "VOICE_STATE_SPEAKING",
    "VOICE_STATE_SHUTDOWN",
]