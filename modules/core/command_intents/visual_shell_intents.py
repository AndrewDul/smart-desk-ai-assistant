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
    "visual_shell.show_temperature": CommandIntentDefinition(
        key="visual_shell.show_temperature",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_temperature",
    ),
    "visual_shell.show_battery": CommandIntentDefinition(
        key="visual_shell.show_battery",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_battery",
    ),
    "visual_shell.show_date": CommandIntentDefinition(
        key="visual_shell.show_date",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_date",
    ),
    "visual_shell.show_time": CommandIntentDefinition(
        key="visual_shell.show_time",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_time",
    ),
    "visual_shell.show_face": CommandIntentDefinition(
        key="visual_shell.show_face",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_face_contour",
    ),
    "visual_shell.show_self": CommandIntentDefinition(
        key="visual_shell.show_self",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_self",
    ),
    "visual_shell.show_eyes": CommandIntentDefinition(
        key="visual_shell.show_eyes",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="show_eyes",
    ),
    "visual_shell.look_at_user": CommandIntentDefinition(
        key="visual_shell.look_at_user",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="look_at_user",
    ),
    "visual_shell.start_scanning": CommandIntentDefinition(
        key="visual_shell.start_scanning",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="start_scanning",
    ),
    "visual_shell.return_to_idle": CommandIntentDefinition(
        key="visual_shell.return_to_idle",
        domain=CommandIntentDomain.VISUAL_SHELL,
        action="return_to_idle",
    ),

}


def get_visual_shell_intent_definition(
    intent_key: str,
) -> CommandIntentDefinition | None:
    return VISUAL_SHELL_INTENT_DEFINITIONS.get(intent_key)
