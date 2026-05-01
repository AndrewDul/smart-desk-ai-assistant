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


def _normalized_command_candidates(text: str) -> tuple[str, ...]:
    """Return safe normalized alternatives for short command matching.

    Vosk limited-grammar recognition may return fallback alternatives such as
    "[unk] | która jest godzina". The command matcher should evaluate the real
    phrase alternative without treating the placeholder token as command text.
    """

    raw_candidates = [text]
    if "|" in text:
        raw_candidates.extend(part for part in text.split("|"))

    normalized_candidates: list[str] = []
    seen: set[str] = set()

    for raw_candidate in raw_candidates:
        normalized = normalize_command_text(raw_candidate)
        normalized = _strip_vosk_unknown_tokens(normalized)
        if not normalized or normalized in seen:
            continue
        normalized_candidates.append(normalized)
        seen.add(normalized)

    return tuple(normalized_candidates)


def _strip_vosk_unknown_tokens(normalized: str) -> str:
    tokens = [
        token
        for token in normalized.split()
        if token not in {"unk", "unknown"}
    ]
    return _SPACES_PATTERN.sub(" ", " ".join(tokens)).strip()


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
        normalized_candidates = _normalized_command_candidates(transcript)
        normalized = normalized_candidates[0] if normalized_candidates else ""
        detected_language = detect_command_language(transcript)

        if not normalized_candidates:
            return CommandRecognitionResult.no_match(
                transcript=transcript,
                normalized_transcript=normalized,
                language=CommandLanguage.UNKNOWN,
            )

        for candidate in normalized_candidates:
            exact_match = self._exact_index.get(candidate)
            if exact_match is not None:
                return CommandRecognitionResult.matched(
                    transcript=transcript,
                    normalized_transcript=candidate,
                    language=exact_match.language,
                    confidence=1.0,
                    intent_key=exact_match.intent_key,
                    matched_phrase=exact_match.phrase,
                )

        for candidate in normalized_candidates:
            compact_matches = self._compact_index.get(self._compact(candidate), [])
            if len(compact_matches) == 1:
                phrase = compact_matches[0]
                return CommandRecognitionResult.matched(
                    transcript=transcript,
                    normalized_transcript=candidate,
                    language=phrase.language,
                    confidence=0.92,
                    intent_key=phrase.intent_key,
                    matched_phrase=phrase.phrase,
                )

            if len(compact_matches) > 1:
                return CommandRecognitionResult.ambiguous(
                    transcript=transcript,
                    normalized_transcript=candidate,
                    language=detected_language,
                    alternatives=tuple(
                        sorted({phrase.intent_key for phrase in compact_matches})
                    ),
                )

        no_match_language = (
            CommandLanguage.UNKNOWN
            if len(normalized_candidates) > 1
            else detected_language
        )

        return CommandRecognitionResult.no_match(
            transcript=transcript,
            normalized_transcript=normalized,
            language=no_match_language,
        )

    def phrases_for_language(self, language: CommandLanguage) -> tuple[str, ...]:
        return tuple(
            phrase.phrase
            for phrase in self._phrases
            if phrase.language == language
        )

    def to_vosk_vocabulary(
        self,
        *,
        language: CommandLanguage | None = None,
        include_stt_recovery: bool = False,
    ) -> tuple[str, ...]:
        """Return phrase list suitable for limited grammar ASR engines.

        STT recovery aliases are useful when matching a full legacy transcript,
        but they should not be exported to Vosk by default. Some recovery
        phrases contain words that are not present in small Vosk model
        vocabularies and would produce runtime grammar warnings.
        """

        phrases = self._phrases
        if language in (CommandLanguage.ENGLISH, CommandLanguage.POLISH):
            phrases = [
                phrase
                for phrase in self._phrases
                if phrase.language == language
            ]

        phrases = [
            phrase
            for phrase in phrases
            if "vosk_exclude" not in phrase.tags
        ]

        if not include_stt_recovery:
            phrases = [
                phrase
                for phrase in phrases
                if "stt_recovery" not in phrase.tags
            ]

        return tuple(sorted({phrase.phrase for phrase in phrases}))

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
            tags=("visual_shell", "desktop", 'vosk_exclude'),
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
            "schowaj pulpit",
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


        # Visual Shell / visible face behaviour.
        CommandPhrase(
            "visual_shell.show_face",
            "pokaż się",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "pokaz sie",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "pokaż siebie",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "show yourself",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "pokaż twarz",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "pokaz twarz",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "show face",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "face"),
        ),

        CommandPhrase(
            "visual_shell.return_to_idle",
            "wróć do chmury",
            CommandLanguage.POLISH,
            tags=("visual_shell", "idle"),
        ),
        CommandPhrase(
            "visual_shell.return_to_idle",
            "wroc do chmury",
            CommandLanguage.POLISH,
            tags=("visual_shell", "idle"),
        ),
        CommandPhrase(
            "visual_shell.return_to_idle",
            "return to idle",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "idle"),
        ),
        CommandPhrase(
            "visual_shell.return_to_idle",
            "go idle",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "idle"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "pokaż temperaturę",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "pokaz temperature",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "show temperature",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "pokaż baterię",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "pokaz baterie",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "show battery",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "battery level",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),

        # System state.
        CommandPhrase(
            "visual_shell.show_temperature",
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
            "visual_shell.show_battery",
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
            "która jest godzina",
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
            "system.current_time",
            "what time it is",
            CommandLanguage.ENGLISH,
            tags=('system', 'time'),
        ),
        CommandPhrase(
            "system.current_time",
            "more time is it",
            CommandLanguage.ENGLISH,
            tags=('system', 'time', 'stt_recovery'),
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
            "visual_shell.show_date",
            "pokaż datę",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_date",
            "pokaz date",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_date",
            "show date",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_date",
            "show the date",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_date",
            "display date",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),

        CommandPhrase(
            "visual_shell.show_time",
            "pokaż czas",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "pokaz czas",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "pokaż godzinę",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "pokaz godzine",
            CommandLanguage.POLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "show time",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "show the time",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
        ),
        CommandPhrase(
            "visual_shell.show_time",
            "display time",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "metric"),
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
            "help",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),
        CommandPhrase(
            "assistant.help",
            "help me",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),


    # Visual help overlay aliases and common short ASR recovery phrases.
        CommandPhrase(
            "assistant.help",
            "show help",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "so help",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "show commands",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "show command list",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "command list",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "commands list",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "help screen",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "open help",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "open commands",
            CommandLanguage.ENGLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "pokaż pomoc",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "pokaz pomoc",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "pokaż komendy",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "pokaz komendy",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "lista komend",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "ekran pomocy",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "otwórz pomoc",
            CommandLanguage.POLISH,
            tags=("assistant",),
        ),

        CommandPhrase(
            "assistant.help",
            "otworz pomoc",
            CommandLanguage.POLISH,
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
            "jak się nazywaś",
            CommandLanguage.POLISH,
            tags=('assistant', 'identity', 'stt_recovery'),
        ),
        CommandPhrase(
            "assistant.identity",
            "jak masz na imię",
            CommandLanguage.POLISH,
            tags=('assistant', 'identity'),
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
            tags=("system", "exit", 'vosk_exclude'),
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
            tags=("system", "exit", 'vosk_exclude'),
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
            "focus mode",
            CommandLanguage.ENGLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.offer",
            "i want to study",
            CommandLanguage.ENGLISH,
            tags=("focus", "offer"),
        ),
        CommandPhrase(
            "focus.offer",
            "study time",
            CommandLanguage.ENGLISH,
            tags=("focus", "offer"),
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
            "focus.start",
            "tryb skupienia",
            CommandLanguage.POLISH,
            tags=("focus",),
        ),
        CommandPhrase(
            "focus.offer",
            "chcę się pouczyć",
            CommandLanguage.POLISH,
            tags=("focus", "offer"),
        ),
        CommandPhrase(
            "focus.offer",
            "chce sie pouczyc",
            CommandLanguage.POLISH,
            tags=("focus", "offer", "stt_recovery"),
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

        # Break mode.
        CommandPhrase(
            "break.start",
            "break mode",
            CommandLanguage.ENGLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "start break mode",
            CommandLanguage.ENGLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "take a break",
            CommandLanguage.ENGLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.stop",
            "stop break mode",
            CommandLanguage.ENGLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "przerwa",
            CommandLanguage.POLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "odpoczynek",
            CommandLanguage.POLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "czas na przerwę",
            CommandLanguage.POLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.start",
            "czas na przerwe",
            CommandLanguage.POLISH,
            tags=("break", "stt_recovery"),
        ),
        CommandPhrase(
            "break.stop",
            "zatrzymaj przerwę",
            CommandLanguage.POLISH,
            tags=("break",),
        ),
        CommandPhrase(
            "break.stop",
            "zatrzymaj przerwe",
            CommandLanguage.POLISH,
            tags=("break", "stt_recovery"),
        ),

        CommandPhrase(
            "visual_shell.show_face",
            "face",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "face", "short"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "your face",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "face", "short"),
        ),
        CommandPhrase(
            "visual_shell.show_face",
            "twarz",
            CommandLanguage.POLISH,
            tags=("visual_shell", "face", "short"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "display temperature",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "temperature"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "show current temperature",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "temperature"),
        ),
        CommandPhrase(
            "visual_shell.show_temperature",
            "pokaż temperaturę",
            CommandLanguage.POLISH,
            tags=("visual_shell", "temperature"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "display battery",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "battery"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "show battery status",
            CommandLanguage.ENGLISH,
            tags=("visual_shell", "battery"),
        ),
        CommandPhrase(
            "visual_shell.show_battery",
            "pokaż baterię",
            CommandLanguage.POLISH,
            tags=("visual_shell", "battery"),
        ),

        # Fast guided reminder phrases for Vosk command ASR.
        CommandPhrase(
            'reminder.guided_start',
            'set reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'set a reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'set the reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'set the reminders',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'add reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'add a reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'create reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'create a reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'make reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'make a reminder',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'remind me',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'remind me something',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'remind me about something',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'przypomnij mi',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'przypomnij mi coś',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'ustaw przypomnienie',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'dodaj przypomnienie',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'stwórz przypomnienie',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.guided_start',
            'zrób przypomnienie',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'guided', 'start'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'one second',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in one second',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'two seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in two seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'three seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in three seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'four seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in four seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'five seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in five seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'six seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in six seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'seven seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in seven seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'eight seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in eight seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'nine seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in nine seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'ten seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in ten seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'fifteen seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in fifteen seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'twenty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in twenty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'thirty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in thirty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'forty five seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in forty five seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'sixty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in sixty seconds',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'one minute',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in one minute',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'two minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in two minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'three minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in three minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'five minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in five minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'ten minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'in ten minutes',
            language=CommandLanguage.ENGLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'jedna sekunda',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za jedna sekunda',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dwie sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dwie sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'trzy sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za trzy sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'cztery sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za cztery sekundy',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'pięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za pięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'sześć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za sześć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'siedem sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za siedem sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'osiem sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za osiem sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dziewięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dziewięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dziesięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dziesięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'piętnaście sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za piętnaście sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dwadzieścia sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dwadzieścia sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'trzydzieści sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za trzydzieści sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'czterdzieści pięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za czterdzieści pięć sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'sześćdziesiąt sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za sześćdziesiąt sekund',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'minuta',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za minuta',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'jedna minuta',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za jedna minuta',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dwie minuty',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dwie minuty',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'trzy minuty',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za trzy minuty',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'pięć minut',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za pięć minut',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'dziesięć minut',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),
        CommandPhrase(
            'reminder.time_answer',
            'za dziesięć minut',
            language=CommandLanguage.POLISH,
            tags=('reminder', 'time', 'follow_up'),
        ),

        CommandPhrase(
            'memory.guided_start',
            'remember something',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'remember this',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'remember that',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'remember it',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'zapamiętaj coś',
            language=CommandLanguage.POLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'zapamietaj cos',
            language=CommandLanguage.POLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'zapamiętaj to',
            language=CommandLanguage.POLISH,
            tags=('memory', 'guided_start'),
        ),
        CommandPhrase(
            'memory.guided_start',
            'zapamietaj to',
            language=CommandLanguage.POLISH,
            tags=('memory', 'guided_start'),
        ),

        CommandPhrase(
            'memory.list',
            'memory list',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'show memory',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'what do you remember',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'show what you remember',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'pokaż pamięć',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'pokaz pamiec',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'co pamiętasz',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'co pamietasz',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list'),
        ),
        CommandPhrase(
            'memory.list',
            'co zapamiętałaś',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list', 'stt_recovery', 'vosk_exclude'),
        ),
        CommandPhrase(
            'memory.list',
            'co zapamietalas',
            language=CommandLanguage.POLISH,
            tags=('memory', 'list', 'stt_recovery', 'vosk_exclude'),
        ),

        # ------------------------------------------------------------------
        # Memory recall — fast-lane (Vosk friendly)
        #
        # These short trigger phrases let "where is my X" / "gdzie jest X"
        # land in the Voice Engine v2 fast lane. The actual subject (X) is
        # resolved later by MemoryService token search, so the grammar only
        # needs to recognise the trigger prefix.
        #
        # Words below are intentionally chosen from the small Vosk vocab
        # (no rare Polish conjugations, no soft-sign endings).
        # ------------------------------------------------------------------
        CommandPhrase(
            'memory.recall',
            'where is',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'where are',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'do you remember',
            language=CommandLanguage.ENGLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'gdzie jest',
            language=CommandLanguage.POLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'gdzie są',
            language=CommandLanguage.POLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'gdzie sa',
            language=CommandLanguage.POLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'czy pamiętasz',
            language=CommandLanguage.POLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
        CommandPhrase(
            'memory.recall',
            'czy pamietasz',
            language=CommandLanguage.POLISH,
            tags=('memory', 'recall', 'prefix'),
        ),
    ]

    return CommandGrammar(phrases)
