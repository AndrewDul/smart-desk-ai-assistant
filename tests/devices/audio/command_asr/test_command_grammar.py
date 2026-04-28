import pytest

from modules.devices.audio.command_asr.command_grammar import (
    CommandGrammar,
    build_default_command_grammar,
    normalize_command_text,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_models import CommandPhrase
from modules.devices.audio.command_asr.command_result import CommandRecognitionStatus


def test_normalize_command_text_removes_case_accents_and_punctuation() -> None:
    assert normalize_command_text(" Pokaż, PULPIT! ") == "pokaz pulpit"


def test_default_grammar_recognizes_polish_show_desktop() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("pokaż pulpit")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_desktop"
    assert result.language == CommandLanguage.POLISH
    assert result.confidence == 1.0


def test_default_grammar_recognizes_polish_stt_recovery_variant() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("pokaż pulpid")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_desktop"
    assert result.language == CommandLanguage.POLISH


def test_default_grammar_recognizes_english_show_desktop() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("show desktop")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_desktop"
    assert result.language == CommandLanguage.ENGLISH


def test_default_grammar_recognizes_polish_hide_desktop_fixture_phrase() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("schowaj pulpit")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "visual_shell.show_shell"
    assert result.language == CommandLanguage.POLISH


def test_default_grammar_recognizes_short_battery_command() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("bateria")

    assert result.status == CommandRecognitionStatus.MATCHED
    assert result.intent_key == "system.battery"
    assert result.language == CommandLanguage.POLISH


def test_default_grammar_does_not_route_open_questions_as_commands() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("czym jest czarna dziura")

    assert result.status == CommandRecognitionStatus.NO_MATCH
    assert result.intent_key is None


def test_command_grammar_rejects_duplicate_phrase_for_different_intents() -> None:
    grammar = CommandGrammar(
        [
            CommandPhrase(
                intent_key="system.battery",
                phrase="battery",
                language=CommandLanguage.ENGLISH,
            )
        ]
    )

    with pytest.raises(ValueError, match="duplicate phrase"):
        grammar.add_phrase(
            CommandPhrase(
                intent_key="system.temperature",
                phrase="battery",
                language=CommandLanguage.ENGLISH,
            )
        )


def test_grammar_exports_vocabulary_for_limited_asr() -> None:
    grammar = build_default_command_grammar()

    vocabulary = grammar.to_vosk_vocabulary()

    assert "show desktop" in vocabulary
    assert "pokaż pulpit" in vocabulary
    assert "bateria" in vocabulary


def test_grammar_exports_language_scoped_vosk_vocabulary() -> None:
    grammar = build_default_command_grammar()

    english_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    polish_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)

    assert "show desktop" in english_vocabulary
    assert "hide desktop" in english_vocabulary
    assert "what time is it" in english_vocabulary
    assert "pokaż pulpit" not in english_vocabulary
    assert "która godzina" not in english_vocabulary

    assert "pokaż pulpit" in polish_vocabulary
    assert "schowaj pulpit" in polish_vocabulary
    assert "która godzina" in polish_vocabulary
    assert "show desktop" not in polish_vocabulary
    assert "what time is it" not in polish_vocabulary