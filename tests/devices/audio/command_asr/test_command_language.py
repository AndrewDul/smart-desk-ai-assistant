from modules.devices.audio.command_asr.command_language import (
    CommandLanguage,
    detect_command_language,
)


def test_detect_command_language_uses_polish_diacritics() -> None:
    assert detect_command_language("pokaż pulpit") == CommandLanguage.POLISH


def test_detect_command_language_uses_polish_command_hints() -> None:
    assert detect_command_language("pokaz pulpit") == CommandLanguage.POLISH


def test_detect_command_language_uses_english_command_hints() -> None:
    assert detect_command_language("show desktop") == CommandLanguage.ENGLISH


def test_detect_command_language_returns_unknown_for_empty_text() -> None:
    assert detect_command_language("") == CommandLanguage.UNKNOWN