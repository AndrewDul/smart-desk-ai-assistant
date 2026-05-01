from __future__ import annotations

from modules.understanding.parsing.parser import IntentParser


def test_guided_reminder_start_accepts_plain_polish_phrase() -> None:
    result = IntentParser().parse("przypomnij mi coś")

    assert result.action == "reminder_create"
    assert result.data["guided"] is True
    assert result.data["guided_language"] == "pl"


def test_guided_reminder_start_accepts_runtime_asr_szypowi_imicowac() -> None:
    result = IntentParser().parse("Szypowi imicować")

    assert result.action == "reminder_create"
    assert result.data["guided"] is True
    assert result.data["guided_language"] == "pl"


def test_guided_reminder_start_accepts_runtime_asr_sie_pomnimi_cos() -> None:
    result = IntentParser().parse("się pomnimi coś")

    assert result.action == "reminder_create"
    assert result.data["guided"] is True
    assert result.data["guided_language"] == "pl"


def test_guided_reminder_start_does_not_steal_help_phrase() -> None:
    result = IntentParser().parse("pomóż mi")

    assert result.action != "reminder_create"
