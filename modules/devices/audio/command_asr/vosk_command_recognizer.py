from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from modules.devices.audio.command_asr.command_grammar import (
    CommandGrammar,
    normalize_command_text,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_recognizer import CommandRecognizer
from modules.devices.audio.command_asr.command_result import CommandRecognitionResult

PcmTranscriptProvider = Callable[[bytes], str | None]

DEFAULT_VOSK_SAMPLE_RATE = 16_000
DEFAULT_VOSK_CHUNK_BYTES = 4_000
DEFAULT_VOSK_MODEL_PATH = "var/models/vosk"


class LocalVoskPcmTranscriptProvider:
    """Local Vosk PCM transcript provider for controlled command recognition.

    This provider consumes an existing PCM buffer. It does not open a microphone,
    does not start an audio stream, does not execute commands, and does not log
    raw PCM. The Vosk model is loaded lazily on first use.
    """

    def __init__(
        self,
        *,
        model_path: str | Path = DEFAULT_VOSK_MODEL_PATH,
        sample_rate: int = DEFAULT_VOSK_SAMPLE_RATE,
        grammar_phrases: Iterable[str] | None = None,
        chunk_bytes: int = DEFAULT_VOSK_CHUNK_BYTES,
    ) -> None:
        self._model_path = Path(model_path)
        self._sample_rate = int(sample_rate)
        self._grammar_phrases = tuple(
            phrase.strip()
            for phrase in grammar_phrases or ()
            if str(phrase).strip()
        )
        self._chunk_bytes = int(chunk_bytes)
        self._model: Any | None = None

        if self._sample_rate <= 0:
            raise ValueError("sample_rate must be greater than zero")
        if self._chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be greater than zero")

    @property
    def model_path(self) -> Path:
        return self._model_path

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def grammar_phrases(self) -> tuple[str, ...]:
        return self._grammar_phrases

    def __call__(self, pcm: bytes) -> str | None:
        if not pcm:
            return None

        model = self._load_model()
        recognizer = self._build_recognizer(model)

        text_parts: list[str] = []
        for start in range(0, len(pcm), self._chunk_bytes):
            chunk = pcm[start : start + self._chunk_bytes]
            if not chunk:
                continue

            if recognizer.AcceptWaveform(chunk):
                text = _extract_text(recognizer.Result())
                if text:
                    text_parts.append(text)

        final_text = _extract_text(recognizer.FinalResult())
        if final_text:
            text_parts.append(final_text)

        transcript = " ".join(part for part in text_parts if part).strip()
        return transcript or None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        model_path = _resolve_vosk_model_path(self._model_path)

        try:
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            self._model = Model(str(model_path))
            return self._model
        except Exception as error:
            raise RuntimeError(
                f"failed_to_load_vosk_model:{model_path}:{type(error).__name__}:{error}"
            ) from error

    def _build_recognizer(self, model: Any) -> Any:
        try:
            from vosk import KaldiRecognizer

            if self._grammar_phrases:
                grammar_json = json.dumps(
                    [*self._grammar_phrases, "[unk]"],
                    ensure_ascii=False,
                )
                return KaldiRecognizer(model, self._sample_rate, grammar_json)

            return KaldiRecognizer(model, self._sample_rate)
        except Exception as error:
            raise RuntimeError(
                f"failed_to_create_vosk_recognizer:{type(error).__name__}:{error}"
            ) from error


class VoskCommandRecognizer(CommandRecognizer):
    """Vosk-compatible command recognizer for Voice Engine v2.

    The recognizer can still use an injected PCM transcript provider for tests,
    but it can now also use a real local Vosk model when `model_path` is given.
    """

    def __init__(
        self,
        *,
        grammar: CommandGrammar,
        pcm_transcript_provider: PcmTranscriptProvider | None = None,
        model_path: str | Path | None = None,
        sample_rate: int = DEFAULT_VOSK_SAMPLE_RATE,
        use_limited_grammar: bool = True,
        grammar_language: CommandLanguage | str | None = None,
    ) -> None:
        self._grammar = grammar
        self._pcm_transcript_provider = pcm_transcript_provider

        if self._pcm_transcript_provider is None and model_path is not None:
            grammar_phrases: tuple[str, ...] = ()
            if use_limited_grammar:
                grammar_phrases = grammar.to_vosk_vocabulary(
                    language=_coerce_command_language(grammar_language)
                )

            self._pcm_transcript_provider = LocalVoskPcmTranscriptProvider(
                model_path=model_path,
                sample_rate=sample_rate,
                grammar_phrases=grammar_phrases,
            )

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


def _coerce_command_language(
    language: CommandLanguage | str | None,
) -> CommandLanguage | None:
    if language is None:
        return None
    if isinstance(language, CommandLanguage):
        if language in (CommandLanguage.ENGLISH, CommandLanguage.POLISH):
            return language
        return None

    value = str(language).strip().lower()
    if not value or value in {"all", "any", "unknown"}:
        return None

    try:
        parsed = CommandLanguage(value)
    except ValueError as error:
        raise ValueError(f"unsupported grammar language: {language!r}") from error

    if parsed in (CommandLanguage.ENGLISH, CommandLanguage.POLISH):
        return parsed
    return None


def _resolve_vosk_model_path(path: Path) -> Path:
    """Resolve a Vosk model path without guessing stage-specific names."""

    if not path.exists():
        raise RuntimeError(f"vosk_model_path_missing:{path}")

    if _looks_like_vosk_model_dir(path):
        return path

    if path.is_dir():
        candidates = [
            child
            for child in sorted(path.iterdir())
            if child.is_dir() and _looks_like_vosk_model_dir(child)
        ]
        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            preferred = [
                candidate
                for candidate in candidates
                if "small" in candidate.name.lower()
            ]
            if preferred:
                return preferred[0]
            return candidates[0]

    raise RuntimeError(f"vosk_model_directory_not_found:{path}")


def _looks_like_vosk_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False

    required_any = [
        path / "am",
        path / "conf",
        path / "graph",
        path / "ivector",
    ]
    return any(item.exists() for item in required_any)


def _extract_text(raw_json: str) -> str:
    try:
        payload = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return ""

    return str(payload.get("text") or "").strip()


__all__ = [
    "DEFAULT_VOSK_CHUNK_BYTES",
    "DEFAULT_VOSK_MODEL_PATH",
    "DEFAULT_VOSK_SAMPLE_RATE",
    "LocalVoskPcmTranscriptProvider",
    "PcmTranscriptProvider",
    "VoskCommandRecognizer",
    "_coerce_command_language",
]
