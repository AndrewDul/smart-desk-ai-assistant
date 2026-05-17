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
    assert result.intent_key == "visual_shell.show_battery"
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


def test_default_grammar_recognizes_safe_memory_forget_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = {
        "forget phone": (CommandLanguage.ENGLISH, "memory.forget"),
        "forget object phone": (CommandLanguage.ENGLISH, "memory.forget"),
        "remove phone from memory": (CommandLanguage.ENGLISH, "memory.forget"),
        "delete object phone from memory": (CommandLanguage.ENGLISH, "memory.forget"),
        "zapomnij telefon": (CommandLanguage.POLISH, "memory.forget"),
        "zapomnij obiekt telefon": (CommandLanguage.POLISH, "memory.forget"),
        "usun telefon z pamieci": (CommandLanguage.POLISH, "memory.forget"),
        "usuń obiekt telefon z pamięci": (CommandLanguage.POLISH, "memory.forget"),
    }

    for phrase, (language, intent_key) in cases.items():
        result = grammar.match(phrase)
        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language == language


def test_vosk_memory_forget_vocabulary_avoids_arbitrary_names() -> None:
    grammar = build_default_command_grammar()

    polish_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)
    english_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)

    assert "zapomnij tomka" not in polish_vocabulary
    assert "zapomnij vape" not in polish_vocabulary
    assert "forget tomek" not in english_vocabulary
    assert "forget vape" not in english_vocabulary
    assert "zapomnij telefon" in polish_vocabulary
    assert "forget phone" in english_vocabulary
    assert all("nexa" not in phrase.lower() for phrase in polish_vocabulary)


def test_polish_vosk_vocabulary_excludes_small_model_missing_words() -> None:
    grammar = build_default_command_grammar()

    polish_vocabulary = grammar.to_vosk_vocabulary(
        language=CommandLanguage.POLISH,
    )
    normalized_words = {
        word
        for phrase in polish_vocabulary
        for word in normalize_command_text(phrase).split()
    }

    assert "polozylam" not in normalized_words
    assert "polozylem" not in normalized_words
    assert "pamietasz" not in normalized_words
    assert "zapamietane" not in normalized_words
    assert "nexa" not in normalized_words
    assert "pamieci" not in normalized_words


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


def test_default_grammar_recognizes_fast_calculator_phrases() -> None:
    grammar = build_default_command_grammar()

    polish_result = grammar.match("ile to jest dwa plus dwa")
    english_result = grammar.match("calculate five times six")

    assert polish_result.status == CommandRecognitionStatus.MATCHED
    assert polish_result.intent_key == "system.calculate"
    assert polish_result.language == CommandLanguage.POLISH
    assert polish_result.matched_phrase == "2 + 2"

    assert english_result.status == CommandRecognitionStatus.MATCHED
    assert english_result.intent_key == "system.calculate"
    assert english_result.language == CommandLanguage.ENGLISH
    assert english_result.matched_phrase == "5 * 6"


def test_default_grammar_recognizes_square_root_calculator_phrases() -> None:
    grammar = build_default_command_grammar()

    polish_result = grammar.match("ile to jest pierwiastek z dziewięć")
    english_result = grammar.match("calculate square root of sixteen")
    operation_result = grammar.match("square root of nine plus square root of sixteen")

    assert polish_result.status == CommandRecognitionStatus.MATCHED
    assert polish_result.intent_key == "system.calculate"
    assert polish_result.language == CommandLanguage.POLISH
    assert polish_result.matched_phrase == "√9"

    assert english_result.status == CommandRecognitionStatus.MATCHED
    assert english_result.intent_key == "system.calculate"
    assert english_result.language == CommandLanguage.ENGLISH
    assert english_result.matched_phrase == "√16"

    assert operation_result.status == CommandRecognitionStatus.MATCHED
    assert operation_result.intent_key == "system.calculate"
    assert operation_result.language == CommandLanguage.ENGLISH
    assert operation_result.matched_phrase == "√9 + √16"


def test_calculator_small_number_vocabulary_is_available_for_limited_vosk() -> None:
    grammar = build_default_command_grammar()

    english_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    polish_vocabulary = grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)

    assert "what is two plus two" in english_vocabulary
    assert "ile to jest dwa plus dwa" in polish_vocabulary
    assert "what is square root of nine" in english_vocabulary
    assert "ile to jest pierwiastek z dziewięć" in polish_vocabulary
    assert "square root of nine plus square root of four" in english_vocabulary
    assert "pierwiastek z dziewięć plus pierwiastek z cztery" in polish_vocabulary


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


def test_default_grammar_recognizes_visual_shell_voice_control_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("pokaż się", "visual_shell.show_face", "pl"),
        ("show yourself", "visual_shell.show_face", "en"),
        ("pokaż twarz", "visual_shell.show_face", "pl"),
        ("show face", "visual_shell.show_face", "en"),
        ("wróć do chmury", "visual_shell.return_to_idle", "pl"),
        ("return to idle", "visual_shell.return_to_idle", "en"),
        ("jaka masz temperaturę", "visual_shell.show_temperature", "pl"),
        ("cpu temperatura", "visual_shell.show_temperature", "pl"),
        ("show cpu temperature", "visual_shell.show_temperature", "en"),
        ("pokaż baterię", "visual_shell.show_battery", "pl"),
        ("show battery", "visual_shell.show_battery", "en"),
        ("spójrz na mnie", "visual_shell.look_at_user", "pl"),
        ("look at me", "visual_shell.look_at_user", "en"),
    ]

    for transcript, intent_key, language in cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language.value == language

    newly_promoted_cases = [
        ("pokaż oczy", "visual_shell.show_eyes", "pl"),
        ("show eyes", "visual_shell.show_eyes", "en"),
        ("sprawdź pokój", "visual_shell.start_scanning", "pl"),
        ("scan room", "visual_shell.start_scanning", "en"),
        ("look around", "visual_shell.start_scanning", "en"),
    ]

    for transcript, intent_key, language in newly_promoted_cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language.value == language


def test_default_grammar_reserves_generic_temperature_for_room_sensor() -> None:
    grammar = build_default_command_grammar()

    reserved_cases = [
        "temperatura",
        "pokaż temperaturę",
        "pokaz temperature",
        "temperature",
        "show temperature",
        "display temperature",
    ]

    for transcript in reserved_cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.NO_MATCH
        assert result.intent_key is None


def test_default_grammar_recognizes_cpu_temperature_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("jaka masz temperaturę", "visual_shell.show_temperature", "pl"),
        ("jaką masz temperaturę", "visual_shell.show_temperature", "pl"),
        ("jako masz temperatura", "visual_shell.show_temperature", "pl"),
        ("jaka jest twoja temperatura", "visual_shell.show_temperature", "pl"),
        ("cpu temperatura", "visual_shell.show_temperature", "pl"),
        ("temperatura cpu", "visual_shell.show_temperature", "pl"),
        ("temperatura procesora", "visual_shell.show_temperature", "pl"),
        ("what is your cpu", "visual_shell.show_temperature", "en"),
        ("what is your cpu temperature", "visual_shell.show_temperature", "en"),
        ("what is the cpu temperature", "visual_shell.show_temperature", "en"),
        ("show cpu temperature", "visual_shell.show_temperature", "en"),
        ("processor temperature", "visual_shell.show_temperature", "en"),
        ("raspberry pi temperature", "visual_shell.show_temperature", "en"),
    ]

    for transcript, intent_key, language in cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language.value == language


def test_default_grammar_routes_show_time_to_visual_shell_without_hijacking_time_question() -> None:
    grammar = build_default_command_grammar()

    visual_cases = [
        ("show time", "visual_shell.show_time", "en"),
        ("show the time", "visual_shell.show_time", "en"),
        ("pokaż czas", "visual_shell.show_time", "pl"),
        ("pokaż godzinę", "visual_shell.show_time", "pl"),
    ]

    for transcript, intent_key, language in visual_cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language.value == language

    english_question = grammar.match("what time is it")
    assert english_question.status == CommandRecognitionStatus.MATCHED
    assert english_question.intent_key == "system.current_time"

    polish_question = grammar.match("która godzina")
    assert polish_question.status == CommandRecognitionStatus.MATCHED
    assert polish_question.intent_key == "system.current_time"


def test_default_grammar_routes_show_date_to_visual_shell() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("show date", "visual_shell.show_date", "en"),
        ("show the date", "visual_shell.show_date", "en"),
        ("pokaż datę", "visual_shell.show_date", "pl"),
        ("pokaz date", "visual_shell.show_date", "pl"),
    ]

    for transcript, intent_key, language in cases:
        result = grammar.match(transcript)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language.value == language


def test_default_grammar_recognizes_visual_help_overlay_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("show help", "assistant.help", CommandLanguage.ENGLISH),
        ("so help", "assistant.help", CommandLanguage.ENGLISH),
        ("show commands", "assistant.help", CommandLanguage.ENGLISH),
        ("show command list", "assistant.help", CommandLanguage.ENGLISH),
        ("command list", "assistant.help", CommandLanguage.ENGLISH),
        ("help screen", "assistant.help", CommandLanguage.ENGLISH),
        ("pokaż pomoc", "assistant.help", CommandLanguage.POLISH),
        ("pokaz pomoc", "assistant.help", CommandLanguage.POLISH),
        ("pokaż komendy", "assistant.help", CommandLanguage.POLISH),
        ("pokaz komendy", "assistant.help", CommandLanguage.POLISH),
        ("lista komend", "assistant.help", CommandLanguage.POLISH),
        ("ekran pomocy", "assistant.help", CommandLanguage.POLISH),
    ]

    for phrase, intent_key, language in cases:
        result = grammar.match(phrase)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language == language

def test_default_grammar_recognizes_feedback_mode_commands() -> None:
    grammar = build_default_command_grammar()

    on_result = grammar.match("feedback on")
    assert on_result.status == CommandRecognitionStatus.MATCHED
    assert on_result.intent_key == "feedback.on"
    assert on_result.language == CommandLanguage.ENGLISH

    pl_on_result = grammar.match("uruchom feedback")
    assert pl_on_result.status == CommandRecognitionStatus.MATCHED
    assert pl_on_result.intent_key == "feedback.on"
    assert pl_on_result.language == CommandLanguage.POLISH

    off_result = grammar.match("feedback off")
    assert off_result.status == CommandRecognitionStatus.MATCHED
    assert off_result.intent_key == "feedback.off"
    assert off_result.language == CommandLanguage.ENGLISH

    pl_off_result = grammar.match("zamknij feedback")
    assert pl_off_result.status == CommandRecognitionStatus.MATCHED
    assert pl_off_result.intent_key == "feedback.off"
    assert pl_off_result.language == CommandLanguage.POLISH


def test_default_grammar_recognizes_feedback_asr_variants() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("feed back on", "feedback.on"),
        ("feedback own", "feedback.on"),
        ("feedback of", "feedback.off"),
        ("feed back off", "feedback.off"),
        ("feed the back of", "feedback.off"),
        ("sheet back off", "feedback.off"),
        ("sheets back off", "feedback.off"),
    ]

    for phrase, expected_intent in cases:
        result = grammar.match(phrase)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == expected_intent
        assert result.language == CommandLanguage.ENGLISH



def test_default_grammar_recognizes_mobile_base_drive_mode_aliases() -> None:
    grammar = build_default_command_grammar()
    english = grammar.match("drive mode")
    assert english.is_match
    assert english.intent_key == "mobile_base.drive_mode"
    assert english.language == CommandLanguage.ENGLISH
    polish = grammar.match("tryb sterowania")
    assert polish.is_match
    assert polish.intent_key == "mobile_base.drive_mode"
    assert polish.language == CommandLanguage.POLISH
    assert "drive mode" in grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    assert "tryb sterowania" in grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)


def test_default_grammar_recognizes_mobile_base_stop_aliases() -> None:
    grammar = build_default_command_grammar()

    english = grammar.match("stop mobile base")
    assert english.is_match
    assert english.intent_key == "mobile_base.stop"
    assert english.language == CommandLanguage.ENGLISH

    polish = grammar.match("zatrzymaj bazę")
    assert polish.is_match
    assert polish.intent_key == "mobile_base.stop"
    assert polish.language == CommandLanguage.POLISH

    assert "stop mobile base" in grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    assert "zatrzymaj bazę" in grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)

    bare_stop = grammar.match("stop")
    assert bare_stop.intent_key != "mobile_base.stop"


def test_default_grammar_recognizes_mobile_base_drive_mode_asr_recovery_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("drie moe", CommandLanguage.ENGLISH),
        ("drive moe", CommandLanguage.ENGLISH),
        ("dry mode", CommandLanguage.ENGLISH),
        ("tryp sterowania", CommandLanguage.POLISH),
        ("try sterowania", CommandLanguage.POLISH),
        ("tryb sterowanie", CommandLanguage.POLISH),
    ]

    for phrase, expected_language in cases:
        result = grammar.match(phrase)

        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == "mobile_base.drive_mode"
        assert result.language == expected_language

    assert "drie moe" not in grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    assert "tryp sterowania" not in grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)



def test_default_grammar_recognizes_rich_identity_and_help_aliases() -> None:
    grammar = build_default_command_grammar()

    cases = [
        ("kim jesteś", "assistant.identity", CommandLanguage.POLISH),
        ("kim ty jesteś", "assistant.identity", CommandLanguage.POLISH),
        ("powiedz kim jesteś", "assistant.identity", CommandLanguage.POLISH),
        ("who are you", "assistant.identity", CommandLanguage.ENGLISH),
        ("what are you", "assistant.identity", CommandLanguage.ENGLISH),
        ("tell me who you are", "assistant.identity", CommandLanguage.ENGLISH),
        ("jak możesz mi pomóc", "assistant.help", CommandLanguage.POLISH),
        ("co potrafisz", "assistant.help", CommandLanguage.POLISH),
        ("how can you help me", "assistant.help", CommandLanguage.ENGLISH),
        ("what can you do", "assistant.help", CommandLanguage.ENGLISH),
        ("what are your commands", "assistant.help", CommandLanguage.ENGLISH),
    ]

    for phrase, intent_key, language in cases:
        result = grammar.match(phrase)
        assert result.status == CommandRecognitionStatus.MATCHED
        assert result.intent_key == intent_key
        assert result.language == language
