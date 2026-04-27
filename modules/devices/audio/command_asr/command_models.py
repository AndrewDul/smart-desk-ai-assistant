from __future__ import annotations

from dataclasses import dataclass

from modules.devices.audio.command_asr.command_language import CommandLanguage


@dataclass(frozen=True, slots=True)
class CommandPhrase:
    """Single phrase variant assigned to a deterministic command intent."""

    intent_key: str
    phrase: str
    language: CommandLanguage
    weight: int = 1
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.intent_key.strip():
            raise ValueError("intent_key must not be empty")
        if not self.phrase.strip():
            raise ValueError("phrase must not be empty")
        if self.weight <= 0:
            raise ValueError("weight must be greater than zero")