from modules.core.command_intents.intent import CommandIntentDomain
from modules.core.command_intents.visual_shell_intents import (
    get_visual_shell_intent_definition,
)


def test_visual_shell_show_desktop_intent_definition_exists() -> None:
    definition = get_visual_shell_intent_definition(
        "visual_shell.show_desktop"
    )

    assert definition is not None
    assert definition.domain == CommandIntentDomain.VISUAL_SHELL
    assert definition.action == "show_desktop"


def test_visual_shell_show_shell_intent_definition_exists() -> None:
    definition = get_visual_shell_intent_definition("visual_shell.show_shell")

    assert definition is not None
    assert definition.domain == CommandIntentDomain.VISUAL_SHELL
    assert definition.action == "show_shell"


def test_unknown_visual_shell_intent_returns_none() -> None:
    assert get_visual_shell_intent_definition("visual_shell.unknown") is None