from __future__ import annotations

from modules.core.assistant import CoreAssistant
from modules.features.reminders.time_parser import ReminderTimeParser
from modules.understanding.parsing.parser import IntentParser


def _remove_reminders_by_message(assistant: CoreAssistant, *messages: str) -> None:
    message_set = {message for message in messages if message}
    reminders = getattr(assistant, "reminders", None)
    if reminders is None or not message_set:
        return

    load_method = getattr(reminders, "_load_reminders", None)
    save_method = getattr(reminders, "_save_reminders", None)
    if not callable(load_method) or not callable(save_method):
        return

    stored = list(load_method())
    filtered = [
        reminder
        for reminder in stored
        if reminder.get("message") not in message_set
    ]
    save_method(filtered)



def test_english_guided_reminder_start_sets_english_language() -> None:
    result = IntentParser().parse("set a reminder")

    assert result.action == "reminder_create"
    assert result.data == {"guided": True, "guided_language": "en"}


def test_polish_guided_reminder_start_sets_polish_language() -> None:
    result = IntentParser().parse("przypomnij mi coś")

    assert result.action == "reminder_create"
    assert result.data == {"guided": True, "guided_language": "pl"}


def test_english_guided_reminder_flow_keeps_english_language() -> None:
    assistant = CoreAssistant()

    assert assistant.handle_command("set a reminder") is True
    assert assistant.pending_follow_up["language"] == "en"

    assert assistant.handle_command("in 8 seconds") is True
    assert assistant.pending_follow_up["language"] == "en"
    assert assistant.pending_follow_up["seconds"] == 8
    assert assistant.pending_follow_up["time_label"] == "in 8 seconds"

    assert assistant.handle_command("call mum") is True
    assert assistant.pending_follow_up is None

    matching = [
        reminder
        for reminder in assistant.reminders.list_all()
        if reminder.get("message") == "call mum"
    ]
    assert matching
    assert matching[-1]["language"] == "en"
    _remove_reminders_by_message(assistant, "call mum")


def test_polish_guided_reminder_flow_keeps_polish_language() -> None:
    assistant = CoreAssistant()

    assert assistant.handle_command("przypomnij mi coś") is True
    assert assistant.pending_follow_up["language"] == "pl"

    assert assistant.handle_command("za 8 sekund") is True
    assert assistant.pending_follow_up["language"] == "pl"
    assert assistant.pending_follow_up["seconds"] == 8

    assert assistant.handle_command("zadzwoń do mamy") is True
    assert assistant.pending_follow_up is None

    matching = [
        reminder
        for reminder in assistant.reminders.list_all()
        if reminder.get("message") == "zadzwoń do mamy"
    ]
    assert matching
    assert matching[-1]["language"] == "pl"
    _remove_reminders_by_message(assistant, "zadzwoń do mamy")


def test_polish_flow_keeps_polish_language_when_asr_returns_english_seconds() -> None:
    assistant = CoreAssistant()

    assert assistant.handle_command("przypomnij mi coś") is True
    assert assistant.pending_follow_up["language"] == "pl"

    assert assistant.handle_command("8 seconds") is True
    assert assistant.pending_follow_up["seconds"] == 8
    assert assistant.pending_follow_up["language"] == "pl"
    assert assistant.pending_follow_up["time_label"] == "za 8 sekund"


def test_time_parser_handles_observed_polish_asr_variants() -> None:
    parser = ReminderTimeParser()

    assert parser.parse("Szy sekundy", language="pl").seconds == 3
    assert parser.parse("Po osiem sekund", language="pl").seconds == 8


def test_set_the_reminder_is_guided_start_not_message() -> None:
    assistant = CoreAssistant()

    assert assistant.handle_command("set the reminder") is True
    assert assistant.pending_follow_up == {
        "type": "reminder_time",
        "language": "en",
        "message": "",
    }
