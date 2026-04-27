from __future__ import annotations

from collections.abc import Callable

from modules.devices.audio.command_asr.command_grammar import (
    CommandGrammar,
    normalize_command_text,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_recognizer import CommandRecognizer
from modules.devices.audio.command_asr.command_result import CommandRecognitionResult

PcmTranscriptProvider = Callable[[bytes], str | None]


class VoskCommandRecognizer(CommandRecognizer):
    """Vosk-compatible command recognizer shell for Voice Engine v2.

    Stage 3 intentionally keeps the actual Vosk dependency out of the core
    contract. Runtime integration should inject a PCM transcript provider
    after model selection, device policy and acceptance tests are ready.
    """

    def __init__(
        self,
        *,
        grammar: CommandGrammar,
        pcm_transcript_provider: PcmTranscriptProvider | None = None,
    ) -> None:
        self._grammar = grammar
        self._pcm_transcript_provider = pcm_transcript_provider

    @property
    def grammar(self) -> CommandGrammar:
        return self._grammar

    def recognize_text(self, transcript: str) -> CommandRecognitionResult:
        return self._grammar.match(transcript)

    def recognize_pcm(self, pcm: bytes) -> CommandRecognitionResult:
        if self._pcm_transcript_provider is None:
            raise RuntimeError("pcm_transcript_provider is required for PCM recognition")

        transcript = self._pcm_transcript_provider(pcm)
        if transcript is None or not transcript.strip():
            return CommandRecognitionResult.no_match(
                transcript=transcript or "",
                normalized_transcript=normalize_command_text(transcript or ""),
                language=CommandLanguage.UNKNOWN,
            )

        return self.recognize_text(transcript)

    def reset(self) -> None:
        return None