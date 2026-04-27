from __future__ import annotations

import re
import unicodedata

from modules.devices.audio.command_asr.command_language import (
    CommandLanguage,
    detect_command_language,
)
from modules.devices.audio.command_asr.command_models import CommandPhrase
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


_NON_WORD_PATTERN = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACES_PATTERN = re.compile(r"\s+")


def normalize_command_text(text: str) -> str:
    """Normalize short spoken command text for deterministic matching."""

    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    without_accents = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    without_punctuation = _NON_WORD_PATTERN.sub(" ", without_accents)
    return _SPACES_PATTERN.sub(" ", without_punctuation).strip()


class CommandGrammar:
    """Deterministic bilingual command grammar for Voice Engine v2."""

    def __init__(self, phrases: list[CommandPhrase] | None = None) -> None:
        self._phrases: list[CommandPhrase] = []
        self._exact_index: dict[str, CommandPhrase] = {}
        self._compact_index: dict[str, list[CommandPhrase]] = {}

        for phrase in phrases or []:
            self.add_phrase(phrase)

    @property
    def phrases(self) -> tuple[CommandPhrase, ...]:
        return tuple(self._phrases)

    @property
    def intent_keys(self) -> tuple[str, ...]:
        return tuple(sorted({phrase.intent_key for phrase in self._phrases}))

    def add_phrase(self, phrase: CommandPhrase) -> None:
        normalized = normalize_command_text(phrase.phrase)
        if not normalized:
            raise ValueError("normalized phrase must not be empty")

        existing = self._exact_index.get(normalized)
        if existing is not None:
            if (
                existing.intent_key == phrase.intent_key
                and existing.language == phrase.language
            ):
                return

            raise ValueError(
                "duplicate phrase maps to multiple command intents: "
                f"{phrase.phrase!r}"
            )

        self._phrases.append(phrase)
        self._exact_index[normalized] = phrase
        self._compact_index.setdefault(
            self._compact(normalized),
            [],
        ).append(phrase)

    def match(self, transcript: str) -> CommandRecognitionResult:
        normalized = normalize_command_text(transcript)
        detected_language = detect_command_language(transcript)

        if not normalized:
            return CommandRecognitionResult.no_match(
                transcript=transcript,
                normalized_transcript=normalized,
                language=CommandLanguage.UNKNOWN,
            )

        exact_match = self._exact_index.get(normalized)
        if exact_match is not None:
            return CommandRecognitionResult.matched(
                transcript=transcript,
                normalized_transcript=normalized,
                language=exact_match.language,
                confidence=1.0,
                intent_key=exact_match.intent_key,
                matched_phrase=exact_match.phrase,
            )

        compact_matches = self._compact_index.get(self._compact(normalized), [])
        if len(compact_matches) == 1:
            phrase = compact_matches[0]
            return CommandRecognitionResult.matched(
                transcript=transcript,
                normalized_transcript=normalized,
                language=phrase.language,
                confidence=0.92,
                intent_key=phrase.intent_key,
                matched_phrase=phrase.phrase,
            )

        if len(compact_matches) > 1:
            return CommandRecognitionResult.ambiguous(
                transcript=transcript,
                normalized_transcript=normalized,
                language=detected_language,
                alternatives=tuple(
                    sorted({phrase.intent_key for phrase in compact_matches})
                ),
            )

        return CommandRecognitionResult.no_match(
            transcript=transcript,
            normalized_transcript=normalized,
            language=detected_language,
        )

    def phrases_for_language(self, language: CommandLanguage) -> tuple[str, ...]:
        return tuple(
            phrase.phrase
            for phrase in self._phrases
            if phrase.language == language
        )

    def to_vosk_vocabulary(self) -> tuple[str, ...]:
        """Return phrase list suitable for limited grammar ASR engines."""

        return tuple(sorted({phrase.phrase for phrase in self._phrases}))

    @staticmethod
    def _compact(normalized: str) -> str:
        return normalized.replace(" ", "")


def build_default_command_grammar() -> CommandGrammar:
    """Build the initial bilingual built-in command grammar.

    This is the new canonical command phrase source for Voice Engine v2.
    During migration, older Visual Shell phrase lists may still exist, but
    they should be deprecated after CommandIntentResolver integration.
    """

    phrases = [
        # Visual Shell / desktop access.
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaż pulpit",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaz pulpit",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaż pulpid",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop", "stt_recovery"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaz pulpid",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop", "stt_recovery"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaż pulbit",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop", "stt_recovery"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "pokaż ikony",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "zdejmij shell",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "odsłoń pulpit",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "daj dostęp do komputera",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "daj mi dostęp do linuxa",
            CommandLanguage.POLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "show desktop",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "show icons",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "hide shell",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "give me access to linux",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "desktop"),
        ),
        CommandPhrase(
            "visual_shell.show_desktop",
            "let me see the desktop",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "desktop"),
        ),

        # Return to assistant shell.
        CommandPhrase(
            "visual_shell.show_shell",
            "wróć do shell",
            CommandLanguage.POLISH,
            tags=("visual_shell",),
        ),
        CommandPhrase(
            "visual_shell.show_shell",
            "pokaż shell",
            CommandLanguage.POLISH,
            tags=("visual_shell",),
        ),
        CommandPhrase(
            "visual_shell.show_shell",
            "ukryj pulpit",
            CommandLanguage.POLISH,
            tags=("visual_shell",),
        ),
        CommandPhrase(
            "visual_shell.show_shell",
            "show shell",
            CommandLanguage.ENGLISH,
            tags=("visual_shell",),
        ),
        CommandPhrase(
            "visual_shell.show_shell",
            "hide desktop",
            CommandLanguage.ENGLISH,
            tags=("visual_shell",),
        ),
        CommandPhrase(
            "visual_shell.show_shell",
            "go back to assistant",
            CommandLanguage.ENGLISH,
            tags=("visual_shell",),
        ),

        # System state.
        CommandPhrase(
            "system.temperature",
            "temperatura",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.temperature",
            "jaka jest twoja temperatura",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.temperature",
            "czy jest ci za gorąco",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.temperature",
            "temperature",
            CommandLanguage.ENGLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.temperature",
            "what is your temperature",
            CommandLanguage.ENGLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.battery",
            "bateria",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.battery",
            "jaka jest twoja bateria",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.battery",
            "czy jesteś zmęczona",
            CommandLanguage.POLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.battery",
            "battery",
            CommandLanguage.ENGLISH,
            tags=("system",),
        ),
        CommandPhrase(
            "system.battery",
            "what is your battery",
            CommandLanguage.ENGLISH,
            tags=("system",),
        ),

        # Basic assistant commands.
        CommandPhrase(
            "system.current_time",
            "która godzina",
            CommandLanguage.POLISH,
            tags=("system", "time"),
        ),
        CommandPhrase(
            "system.current_time",
            "jaki jest czas",
            CommandLanguage.POLISH,
            tags=("system", "time"),
        ),
        CommandPhrase(
            "system.current_time",
            "what time is it",
            CommandLanguage.ENGLISH,
            tags=("system", "time"),
        ),
        CommandPhrase(
            "system.current_date",
            "jaka jest data",
            CommandLanguage.POLISH,
            tags=("system", "date"),
        ),
        CommandPhrase(
            "system.current_date",
            "dzisiejsza data",
            CommandLanguage.POLISH,
            tags=("system", "date"),
        ),
        CommandPhrase(
            "system.current_date",
            "what is today's date",
            CommandLanguage.ENGLISH,
            tags=("system", "date"),
        ),
        CommandPhrase(
            "assistant.help",
            "pomoc",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),
        CommandPhrase(
            "assistant.help",
            "pomóż mi",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),
        CommandPhrase(
            "assistant.help",
            "help me",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),
        CommandPhrase(
            "assistant.identity",
            "jak się nazywasz",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),
        CommandPhrase(
            "assistant.identity",
            "what is your name",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        # Assistant exit / sleep request.
        CommandPhrase(
            "system.exit",
            "exit",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "exit assistant",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "close assistant",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "close nexa",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "go to sleep",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "turn off assistant",
            CommandLanguage.ENGLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "zamknij asystenta",
            CommandLanguage.POLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "zamknij nexa",
            CommandLanguage.POLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "idź spać",
            CommandLanguage.POLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "idz spac",
            CommandLanguage.POLISH,
            tags=("system", "exit", "stt_recovery"),
        ),
        CommandPhrase(
            "system.exit",
            "odpocznij",
            CommandLanguage.POLISH,
            tags=("system", "exit"),
        ),
        CommandPhrase(
            "system.exit",
            "wyłącz asystenta",
            CommandLanguage.POLISH,
            tags=("system", "exit"),
        ),

        # Focus mode.
        CommandPhrase(
            "focus.start",
            "start focus mode",
            CommandLanguage.ENGLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.start",
            "start focus mode for five minutes",
            CommandLanguage.ENGLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.start",
            "włącz focus mode",
            CommandLanguage.POLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.start",
            "włącz tryb skupienia",
            CommandLanguage.POLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.stop",
            "stop focus mode",
            CommandLanguage.ENGLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.stop",
            "zatrzymaj focus mode",
            CommandLanguage.POLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.stop",
            "wyłącz tryb skupienia",
            CommandLanguage.POLISH,
            tags=("focus",),
        ),
    ]

    return CommandGrammar(phrases)