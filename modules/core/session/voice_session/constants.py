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

VOICE_PHASE_WAKE_GATE = "wake_gate"
VOICE_PHASE_WAKE_ACK = "wake_ack"
VOICE_PHASE_COMMAND = "command"
VOICE_PHASE_FOLLOW_UP = "follow_up"
VOICE_PHASE_GRACE = "grace"
VOICE_PHASE_TRANSCRIBE = "transcribe"
VOICE_PHASE_ROUTE = "route"
VOICE_PHASE_THINK = "think"
VOICE_PHASE_SPEAK = "speak"
VOICE_PHASE_NOTIFICATION = "notification"
VOICE_PHASE_SHUTDOWN = "shutdown"

_VALID_PHASES = {
    VOICE_PHASE_WAKE_GATE,
    VOICE_PHASE_WAKE_ACK,
    VOICE_PHASE_COMMAND,
    VOICE_PHASE_FOLLOW_UP,
    VOICE_PHASE_GRACE,
    VOICE_PHASE_TRANSCRIBE,
    VOICE_PHASE_ROUTE,
    VOICE_PHASE_THINK,
    VOICE_PHASE_SPEAK,
    VOICE_PHASE_NOTIFICATION,
    VOICE_PHASE_SHUTDOWN,
}

VOICE_INPUT_OWNER_NONE = "none"
VOICE_INPUT_OWNER_WAKE_GATE = "wake_gate"
VOICE_INPUT_OWNER_VOICE_INPUT = "voice_input"
VOICE_INPUT_OWNER_ASSISTANT_OUTPUT = "assistant_output"

_VALID_INPUT_OWNERS = {
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_ASSISTANT_OUTPUT,
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
    "Give me a moment.",
    "I'm checking that now.",
    "One second, I'm looking into it.",
    "I'm thinking it through.",
    "I'll answer in a moment.",
    "I'm checking the details.",
    "Let me look that up.",
    "I'm working on it.",
    "One moment, please.",
    "I'm checking quickly.",
    "I'm looking at it now.",
)

_DEFAULT_THINKING_ACKS_PL = (
    "Chwila moment.",
    "Daj mi sekundę.",
    "Już sprawdzam.",
    "Daj mi pomyśleć.",
    "Daj mi chwilę.",
    "Chwileczkę, sprawdzam.",
    "Moment, szukam tego.",
    "Zaraz Ci odpowiem.",
    "Muszę to szybko sprawdzić.",
    "Już nad tym pracuję.",
    "Sekundę, sprawdzam szczegóły.",
    "Już patrzę.",
    "Moment, zaraz wracam z odpowiedzią.",
    "Sprawdzam to teraz.",
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
    "VOICE_PHASE_WAKE_GATE",
    "VOICE_PHASE_WAKE_ACK",
    "VOICE_PHASE_COMMAND",
    "VOICE_PHASE_FOLLOW_UP",
    "VOICE_PHASE_GRACE",
    "VOICE_PHASE_TRANSCRIBE",
    "VOICE_PHASE_ROUTE",
    "VOICE_PHASE_THINK",
    "VOICE_PHASE_SPEAK",
    "VOICE_PHASE_NOTIFICATION",
    "VOICE_PHASE_SHUTDOWN",
    "VOICE_INPUT_OWNER_NONE",
    "VOICE_INPUT_OWNER_WAKE_GATE",
    "VOICE_INPUT_OWNER_VOICE_INPUT",
    "VOICE_INPUT_OWNER_ASSISTANT_OUTPUT",
]
