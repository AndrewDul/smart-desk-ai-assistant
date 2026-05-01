from modules.core.command_intents.intent import CommandIntentDomain
from modules.core.command_intents.system_intents import (
    get_system_intent_definition,
)


def test_system_battery_intent_definition_exists() -> None:
    definition = get_system_intent_definition("system.battery")

    assert definition is not None
    assert definition.domain == CommandIntentDomain.SYSTEM
    assert definition.action == "report_battery"


def test_system_temperature_intent_definition_exists() -> None:
    definition = get_system_intent_definition("system.temperature")

    assert definition is not None
    assert definition.domain == CommandIntentDomain.SYSTEM
    assert definition.action == "report_temperature"


def test_focus_start_intent_definition_exists() -> None:
    definition = get_system_intent_definition("focus.start")

    assert definition is not None
    assert definition.domain == CommandIntentDomain.FOCUS
    assert definition.action == "start_focus_mode"


def test_unknown_system_intent_returns_none() -> None:
    assert get_system_intent_definition("system.unknown") is None