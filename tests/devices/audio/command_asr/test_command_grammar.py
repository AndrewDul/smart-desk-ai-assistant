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
    assert "która jest godzina" in polish_vocabulary
    assert "show desktop" not in polish_vocabulary
    assert "what time is it" not in polish_vocabulary


def test_runtime_recovery_aliases_from_candidate_comparison_logs() -> None:
    grammar = build_default_command_grammar()

    time_recovery = grammar.match("more time is it.")
    assert time_recovery.is_match
    assert time_recovery.intent_key == "system.current_time"
    assert time_recovery.language.value == "en"

    polish_identity_recovery = grammar.match("Jak się nazywaś?")
    assert polish_identity_recovery.is_match
    assert polish_identity_recovery.intent_key == "assistant.identity"
    assert polish_identity_recovery.language.value == "pl"

    polish_identity_natural = grammar.match("Jak masz na imię?")
    assert polish_identity_natural.is_match
    assert polish_identity_natural.intent_key == "assistant.identity"
    assert polish_identity_natural.language.value == "pl"


def test_runtime_recovery_aliases_do_not_mix_command_languages() -> None:
    grammar = build_default_command_grammar()

    english_phrases = grammar.phrases_for_language(CommandLanguage.ENGLISH)
    polish_phrases = grammar.phrases_for_language(CommandLanguage.POLISH)

    assert "more time is it" in english_phrases
    assert "more time is it" not in polish_phrases

    assert "jak się nazywaś" in polish_phrases
    assert "jak masz na imię" in polish_phrases
    assert "jak się nazywaś" not in english_phrases
    assert "jak masz na imię" not in english_phrases


def test_natural_time_alias_from_runtime_observation() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("What time it is?")

    assert result.is_match
    assert result.intent_key == "system.current_time"
    assert result.language.value == "en"


def test_default_grammar_recognizes_polish_natural_time_alias_from_vosk_observation() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("która jest godzina")

    assert result.is_match
    assert result.intent_key == "system.current_time"
    assert result.language.value == "pl"


def test_default_grammar_matches_vosk_unknown_polish_time_alternative() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("[unk] | która jest godzina")

    assert result.is_match
    assert result.intent_key == "system.current_time"
    assert result.language.value == "pl"
    assert result.normalized_transcript == "ktora jest godzina"


def test_default_grammar_does_not_match_cross_language_short_alternatives() -> None:
    grammar = build_default_command_grammar()

    result = grammar.match("is | jest")

    assert not result.is_match
    assert result.intent_key is None
    assert result.language.value == "unknown"


def test_vosk_vocabulary_excludes_stt_recovery_aliases_by_default() -> None:
    grammar = build_default_command_grammar()

    english_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.ENGLISH,
    )
    polish_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.POLISH,
    )

    assert "what time it is" in english_vocabulary
    assert "more time is it" not in english_vocabulary
    assert "jak się nazywaś" not in polish_vocabulary
    assert "pokaż pulpid" not in polish_vocabulary
    assert "pokaz pulpid" not in polish_vocabulary
    assert "pokaż pulbit" not in polish_vocabulary

    english_recovery_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.ENGLISH,
        include_stt_recovery=True,
    )
    polish_recovery_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.POLISH,
        include_stt_recovery=True,
    )

    assert "more time is it" in english_recovery_vocabulary
    assert "jak się nazywaś" in polish_recovery_vocabulary
    assert "pokaż pulpid" in polish_recovery_vocabulary


def test_vosk_vocabulary_excludes_small_model_unsupported_natural_aliases() -> None:
    grammar = build_default_command_grammar()

    polish_match = grammar.match("odsłoń pulpit")
    assert polish_match.is_match
    assert polish_match.intent_key == "visual_shell.show_desktop"
    assert polish_match.language.value == "pl"

    english_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.ENGLISH,
    )
    polish_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.POLISH,
    )

    assert "odsłoń pulpit" not in polish_vocabulary
    assert all("nexa" not in phrase.lower() for phrase in english_vocabulary)
    assert all("nexa" not in phrase.lower() for phrase in polish_vocabulary)


def test_vosk_vocabulary_excludes_vosk_exclude_even_when_recovery_enabled() -> None:
    grammar = build_default_command_grammar()

    english_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.ENGLISH,
        include_stt_recovery=True,
    )
    polish_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.POLISH,
        include_stt_recovery=True,
    )

    assert "odsłoń pulpit" not in polish_vocabulary
    assert all("nexa" not in phrase.lower() for phrase in english_vocabulary)
    assert all("nexa" not in phrase.lower() for phrase in polish_vocabulary)



def test_default_grammar_recognizes_assistant_help_aliases() -> None:
    grammar = build_default_command_grammar()

    english_result = grammar.match("help")
    polish_result = grammar.match("pomoc")

    assert english_result.status == CommandRecognitionStatus.MATCHED
    assert english_result.intent_key == "assistant.help"
    assert english_result.language == CommandLanguage.ENGLISH
    assert english_result.matched_phrase == "help"

    assert polish_result.status == CommandRecognitionStatus.MATCHED
    assert polish_result.intent_key == "assistant.help"
    assert polish_result.language == CommandLanguage.POLISH
    assert polish_result.matched_phrase == "pomoc"
