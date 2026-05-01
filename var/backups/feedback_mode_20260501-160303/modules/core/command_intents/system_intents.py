from __future__ import annotations

from modules.core.command_intents.intent import (
    CommandIntentDefinition,
    CommandIntentDomain,
)


SYSTEM_INTENT_DEFINITIONS: dict[str, CommandIntentDefinition] = {
    "system.temperature": CommandIntentDefinition(
        key="system.temperature",
        domain=CommandIntentDomain.SYSTEM,
        action="report_temperature",
    ),
    "system.battery": CommandIntentDefinition(
        key="system.battery",
        domain=CommandIntentDomain.SYSTEM,
        action="report_battery",
    ),
    "system.current_time": CommandIntentDefinition(
        key="system.current_time",
        domain=CommandIntentDomain.SYSTEM,
        action="report_current_time",
    ),
    "system.current_date": CommandIntentDefinition(
        key="system.current_date",
        domain=CommandIntentDomain.SYSTEM,
        action="report_current_date",
    ),
    "system.exit": CommandIntentDefinition(
        key="system.exit",
        domain=CommandIntentDomain.SYSTEM,
        action="exit",
    ),
    "feedback.on": CommandIntentDefinition(
        key="feedback.on",
        domain=CommandIntentDomain.SYSTEM,
        action="feedback_on",
    ),
    "feedback.off": CommandIntentDefinition(
        key="feedback.off",
        domain=CommandIntentDomain.SYSTEM,
        action="feedback_off",
    ),
    "assistant.help": CommandIntentDefinition(
        key="assistant.help",
        domain=CommandIntentDomain.ASSISTANT,
        action="show_help",
    ),
    "assistant.identity": CommandIntentDefinition(
        key="assistant.identity",
        domain=CommandIntentDomain.ASSISTANT,
        action="introduce_self",
    ),
    "focus.start": CommandIntentDefinition(
        key="focus.start",
        domain=CommandIntentDomain.FOCUS,
        action="start_focus_mode",
    ),
    "focus.stop": CommandIntentDefinition(
        key="focus.stop",
        domain=CommandIntentDomain.FOCUS,
        action="stop_focus_mode",
    ),
    "focus.offer": CommandIntentDefinition(
        key="focus.offer",
        domain=CommandIntentDomain.FOCUS,
        action="offer_focus_mode",
    ),
    "break.start": CommandIntentDefinition(
        key="break.start",
        domain=CommandIntentDomain.BREAK,
        action="start_break_mode",
    ),
    "break.stop": CommandIntentDefinition(
        key="break.stop",
        domain=CommandIntentDomain.BREAK,
        action="stop_break_mode",
    ),
}


def get_system_intent_definition(intent_key: str) -> CommandIntentDefinition | None:
    return SYSTEM_INTENT_DEFINITIONS.get(intent_key)