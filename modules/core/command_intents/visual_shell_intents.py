from __future__ import annotations

from modules.core.command_intents.intent import (
    CommandIntentDefinition,
    CommandIntentDomain,
)


VISUAL_SHELL_INTENT_DEFINITIONS: dict[str, CommandIntentDefinition] = {
    "visual_shell.show_desktop": CommandIntentDefinition(
        key="visual_shell.show_desktop",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_desktop",
    ),
    "visual_shell.show_shell": CommandIntentDefinition(
        key="visual_shell.show_shell",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_shell",
    ),
}


def get_visual_shell_intent_definition(
    intent_key: str,
) -> CommandIntentDefinition | None:
    return VISUAL_SHELL_INTENT_DEFINITIONS.get(intent_key)