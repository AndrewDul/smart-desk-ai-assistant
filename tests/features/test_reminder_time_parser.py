from __future__ import annotations

from datetime import datetime

from modules.features.reminders.time_parser import ReminderTimeParser


def test_reminder_time_parser_handles_polish_relative_minutes() -> None:
    result = ReminderTimeParser().parse(
        "za 15 minut",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 15 * 60
    assert result.display_phrase == "za 15 minut"


def test_reminder_time_parser_handles_polish_absolute_clock_time() -> None:
    result = ReminderTimeParser().parse(
        "o 18:30",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.due_at == datetime(2026, 4, 30, 18, 30, 0)
    assert result.display_phrase == "o 18:30"


def test_reminder_time_parser_moves_plain_past_clock_time_to_next_day() -> None:
    result = ReminderTimeParser().parse(
        "o 8",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.due_at == datetime(2026, 5, 1, 8, 0, 0)


def test_reminder_time_parser_handles_english_relative_hours() -> None:
    result = ReminderTimeParser().parse(
        "in 2 hours",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="en",
    )

    assert result is not None
    assert result.seconds == 2 * 60 * 60
    assert result.display_phrase == "in 2 hours"


def test_reminder_time_parser_rejects_ambiguous_time() -> None:
    result = ReminderTimeParser().parse(
        "za jakiś czas",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is None


def test_reminder_time_parser_handles_polish_numeric_seconds() -> None:
    result = ReminderTimeParser().parse(
        "za 3 sekundy",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 3
    assert result.display_phrase == "za 3 sekundy"


def test_reminder_time_parser_handles_polish_spoken_seconds() -> None:
    result = ReminderTimeParser().parse(
        "za trzy sekundy",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 3
    assert result.display_phrase == "za 3 sekundy"


def test_reminder_time_parser_handles_polish_spoken_fifteen_seconds() -> None:
    result = ReminderTimeParser().parse(
        "za piętnaście sekund",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 15
    assert result.display_phrase == "za 15 sekund"


def test_reminder_time_parser_accepts_bare_polish_time_answer() -> None:
    result = ReminderTimeParser().parse(
        "piętnaście sekund",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 15


def test_reminder_time_parser_handles_runtime_asr_jason_second() -> None:
    result = ReminderTimeParser().parse(
        "Jason Second",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 10


def test_reminder_time_parser_handles_runtime_asr_kteri_sekundy() -> None:
    result = ReminderTimeParser().parse(
        "Kteri sekundy",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 4


def test_reminder_time_parser_handles_runtime_asr_dlonascie() -> None:
    result = ReminderTimeParser().parse(
        "Dłonaście",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 12


def test_reminder_time_parser_handles_runtime_asr_ocean() -> None:
    result = ReminderTimeParser().parse(
        "Ocean",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 8


def test_reminder_time_parser_handles_english_seconds_answer_in_polish_flow() -> None:
    result = ReminderTimeParser().parse(
        "8 seconds",
        now=datetime(2026, 4, 30, 12, 0, 0),
        language="pl",
    )

    assert result is not None
    assert result.seconds == 8
    assert result.display_phrase == "za 8 sekund"
