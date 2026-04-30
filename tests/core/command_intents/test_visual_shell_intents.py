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


def test_visual_shell_extended_voice_control_intent_definitions_exist() -> None:
    expected_actions = {
        "visual_shell.show_self": "show_self",
        "visual_shell.show_eyes": "show_eyes",
        "visual_shell.show_face": "show_face_contour",
        "visual_shell.look_at_user": "look_at_user",
        "visual_shell.start_scanning": "start_scanning",
        "visual_shell.return_to_idle": "return_to_idle",
        "visual_shell.show_temperature": "show_temperature",
        "visual_shell.show_battery": "show_battery",
    }

    for intent_key, action in expected_actions.items():
        definition = get_visual_shell_intent_definition(intent_key)

        assert definition is not None
        assert definition.domain == CommandIntentDomain.VISUAL_SHELL
        assert definition.action == action
