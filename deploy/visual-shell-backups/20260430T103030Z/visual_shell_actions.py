from __future__ import annotations


VISUAL_SHELL_ACTIONS = frozenset(
    {
        "show_desktop",
        "show_shell",
        "show_temperature",
        "show_battery",
        "show_date",
        "show_time",
    }
)


def is_visual_shell_action(action: str) -> bool:
    return action in VISUAL_SHELL_ACTIONS
