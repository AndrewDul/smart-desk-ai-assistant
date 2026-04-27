from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.core.command_intents.intent import CommandIntent
from modules.core.command_intents.intent_result import (
    CommandIntentResolutionResult,
)
from modules.core.voice_engine.fallback_pipeline import FallbackDecision
from modules.core.voice_engine.voice_engine_metrics import VoiceEngineMetrics
from modules.core.voice_engine.voice_turn_state import VoiceTurnState
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
)


class VoiceTurnRoute(str, Enum):
    """Final routing decision for one voice turn."""

    COMMAND = "command"
    FALLBACK = "fallback"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class VoiceTurnInput:
    """Input passed to Voice Engine v2 for one turn."""

    turn_id: str
    transcript: str = ""
    pcm: bytes | None = None
    started_monotonic: float = 0.0
    speech_end_monotonic: float | None = None
    language_hint: CommandLanguage = CommandLanguage.UNKNOWN
    source: str = "voice_engine_v2"

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if self.started_monotonic < 0:
            raise ValueError("started_monotonic must not be negative")
        if self.speech_end_monotonic is not None and self.speech_end_monotonic < 0:
            raise ValueError("speech_end_monotonic must not be negative")
        if self.pcm is None and not self.transcript.strip():
            raise ValueError("transcript or pcm must be provided")
        if not self.source.strip():
            raise ValueError("source must not be empty")


@dataclass(frozen=True, slots=True)
class VoiceTurnResult:
    """Output returned by Voice Engine v2 for one turn."""

    turn_id: str
    state: VoiceTurnState
    route: VoiceTurnRoute
    language: CommandLanguage
    metrics: VoiceEngineMetrics
    source_text: str = ""
    intent: CommandIntent | None = None
    recognition: CommandRecognitionResult | None = None
    resolution: CommandIntentResolutionResult | None = None
    fallback: FallbackDecision | None = None

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")

        if self.route is VoiceTurnRoute.COMMAND and self.intent is None:
            raise ValueError("command route requires intent")

        if self.route is VoiceTurnRoute.FALLBACK and self.fallback is None:
            raise ValueError("fallback route requires fallback decision")

    @property
    def is_command(self) -> bool:
        return self.route is VoiceTurnRoute.COMMAND

    @property
    def is_fallback(self) -> bool:
        return self.route is VoiceTurnRoute.FALLBACK