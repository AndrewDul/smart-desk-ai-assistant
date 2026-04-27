from __future__ import annotations

from typing import Protocol

from modules.devices.audio.command_asr.command_grammar import CommandGrammar
from modules.devices.audio.command_asr.command_result import CommandRecognitionResult


class CommandRecognizer(Protocol):
    """Protocol for command-first recognizers."""

    def recognize_text(self, transcript: str) -> CommandRecognitionResult:
        """Recognize a deterministic command from text."""

    def reset(self) -> None:
        """Reset recognizer state."""


class GrammarCommandRecognizer:
    """Text-only command recognizer backed by CommandGrammar."""

    def __init__(self, grammar: CommandGrammar) -> None:
        self._grammar = grammar

    @property
    def grammar(self) -> CommandGrammar:
        return self._grammar

    def recognize_text(self, transcript: str) -> CommandRecognitionResult:
        return self._grammar.match(transcript)

    def reset(self) -> None:
        return None