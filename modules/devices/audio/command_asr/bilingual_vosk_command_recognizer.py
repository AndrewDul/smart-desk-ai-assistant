from __future__ import annotations

from pathlib import Path

from modules.devices.audio.command_asr.command_grammar import (
    CommandGrammar,
    build_default_command_grammar,
    normalize_command_text,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_recognizer import CommandRecognizer
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    DEFAULT_VOSK_SAMPLE_RATE,
    VoskCommandRecognizer,
)


DEFAULT_ENGLISH_VOSK_MODEL_PATH = "var/models/vosk/vosk-model-small-en-us-0.15"
DEFAULT_POLISH_VOSK_MODEL_PATH = "var/models/vosk/vosk-model-small-pl-0.22"


class BilingualVoskCommandRecognizer(CommandRecognizer):
    """Command recognizer that keeps English and Polish Vosk paths separated.

    The same PCM command window is evaluated by two language-specific Vosk
    recognizers. Each recognizer receives only its own command grammar. The
    class does not start a microphone stream, does not execute actions, and
    does not log raw PCM.
    """

    def __init__(
        self,
        *,
        grammar: CommandGrammar | None = None,
        english_recognizer: VoskCommandRecognizer | None = None,
        polish_recognizer: VoskCommandRecognizer | None = None,
        english_model_path: str | Path | None = None,
        polish_model_path: str | Path | None = None,
        sample_rate: int = DEFAULT_VOSK_SAMPLE_RATE,
    ) -> None:
        self._grammar = grammar or build_default_command_grammar()
        self._english_recognizer = english_recognizer or VoskCommandRecognizer(
            grammar=self._grammar,
            model_path=english_model_path or DEFAULT_ENGLISH_VOSK_MODEL_PATH,
            sample_rate=sample_rate,
            grammar_language=CommandLanguage.ENGLISH,
        )
        self._polish_recognizer = polish_recognizer or VoskCommandRecognizer(
            grammar=self._grammar,
            model_path=polish_model_path or DEFAULT_POLISH_VOSK_MODEL_PATH,
            sample_rate=sample_rate,
            grammar_language=CommandLanguage.POLISH,
        )

    @property
    def grammar(self) -> CommandGrammar:
        return self._grammar

    def recognize_text(self, transcript: str) -> CommandRecognitionResult:
        return self._grammar.match(transcript)

    def recognize_pcm(self, pcm: bytes) -> CommandRecognitionResult:
        english_result = self._safe_recognize(
            recognizer=self._english_recognizer,
            pcm=pcm,
        )
        polish_result = self._safe_recognize(
            recognizer=self._polish_recognizer,
            pcm=pcm,
        )

        return _select_bilingual_result(
            english_result=english_result,
            polish_result=polish_result,
        )

    def reset(self) -> None:
        self._english_recognizer.reset()
        self._polish_recognizer.reset()

    @staticmethod
    def _safe_recognize(
        *,
        recognizer: VoskCommandRecognizer,
        pcm: bytes,
    ) -> CommandRecognitionResult:
        try:
            return recognizer.recognize_pcm(pcm)
        except RuntimeError as error:
            return CommandRecognitionResult.no_match(
                transcript=f"recognizer_error:{type(error).__name__}",
                normalized_transcript=normalize_command_text(str(error)),
                language=CommandLanguage.UNKNOWN,
            )


def _select_bilingual_result(
    *,
    english_result: CommandRecognitionResult,
    polish_result: CommandRecognitionResult,
) -> CommandRecognitionResult:
    matched_results = [
        result
        for result in (english_result, polish_result)
        if result.status is CommandRecognitionStatus.MATCHED
    ]

    if len(matched_results) == 1:
        return matched_results[0]

    if len(matched_results) > 1:
        ordered = sorted(
            matched_results,
            key=lambda result: result.confidence,
            reverse=True,
        )
        if ordered[0].confidence > ordered[1].confidence:
            return ordered[0]

        alternatives = tuple(
            sorted(
                {
                    str(result.intent_key)
                    for result in matched_results
                    if result.intent_key
                }
            )
        )
        transcript = " | ".join(
            result.transcript for result in matched_results if result.transcript
        )
        return CommandRecognitionResult.ambiguous(
            transcript=transcript,
            normalized_transcript=normalize_command_text(transcript),
            language=CommandLanguage.UNKNOWN,
            alternatives=alternatives,
        )

    return _best_no_match(
        english_result=english_result,
        polish_result=polish_result,
    )


def _best_no_match(
    *,
    english_result: CommandRecognitionResult,
    polish_result: CommandRecognitionResult,
) -> CommandRecognitionResult:
    if english_result.transcript.strip() and not polish_result.transcript.strip():
        return english_result
    if polish_result.transcript.strip() and not english_result.transcript.strip():
        return polish_result

    transcript = " | ".join(
        result.transcript
        for result in (english_result, polish_result)
        if result.transcript.strip()
    )
    if transcript:
        return CommandRecognitionResult.no_match(
            transcript=transcript,
            normalized_transcript=normalize_command_text(transcript),
            language=CommandLanguage.UNKNOWN,
        )

    return CommandRecognitionResult.no_match(
        transcript="",
        normalized_transcript="",
        language=CommandLanguage.UNKNOWN,
    )


__all__ = [
    "BilingualVoskCommandRecognizer",
    "DEFAULT_ENGLISH_VOSK_MODEL_PATH",
    "DEFAULT_POLISH_VOSK_MODEL_PATH",
]
