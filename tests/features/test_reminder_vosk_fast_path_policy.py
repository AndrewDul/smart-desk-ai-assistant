from __future__ import annotations

from modules.devices.audio.command_asr.command_grammar import build_default_command_grammar
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import CommandRecognitionStatus


def _matched(text: str) -> bool:
    result = build_default_command_grammar().match(text)
    return result.status == CommandRecognitionStatus.MATCHED


def _intent(text: str) -> str:
    result = build_default_command_grammar().match(text)
    return str(getattr(result, "intent_key", "") or "")


def test_vosk_command_grammar_accepts_guided_reminder_start_phrases() -> None:
    assert _matched("set reminder")
    assert _matched("set a reminder")
    assert _matched("set the reminder")
    assert _matched("przypomnij mi coś")

    assert _intent("set reminder") == "reminder.guided_start"
    assert _intent("przypomnij mi coś") == "reminder.guided_start"


def test_vosk_command_grammar_accepts_reminder_time_follow_up_phrases() -> None:
    assert _matched("eight seconds")
    assert _matched("in eight seconds")
    assert _matched("osiem sekund")
    assert _matched("za osiem sekund")

    assert _intent("eight seconds") == "reminder.time_answer"
    assert _intent("za osiem sekund") == "reminder.time_answer"


def test_vosk_vocabulary_exports_reminder_fast_path_phrases() -> None:
    grammar = build_default_command_grammar()

    english_vocabulary = set(
        grammar.to_vosk_vocabulary(language=CommandLanguage.ENGLISH)
    )
    polish_vocabulary = set(
        grammar.to_vosk_vocabulary(language=CommandLanguage.POLISH)
    )

    assert "set reminder" in english_vocabulary
    assert "set a reminder" in english_vocabulary
    assert "set the reminder" in english_vocabulary
    assert "eight seconds" in english_vocabulary
    assert "in eight seconds" in english_vocabulary

    assert "przypomnij mi coś" in polish_vocabulary
    assert "osiem sekund" in polish_vocabulary
    assert "za osiem sekund" in polish_vocabulary
