from __future__ import annotations


def _resolve_kind(action: str) -> str:
    if "time" in action:
        return "time"
    if "date" in action:
        return "date"
    if "day" in action:
        return "day"
    return "year"


def _should_show_on_display(action: str) -> bool:
    return str(action).startswith("show_")


def handle_temporal_intent(assistant, result, lang: str) -> bool:
    kind = _resolve_kind(result.action)
    spoken, title, lines = assistant._format_temporal_text(kind, lang)

    assistant.voice_out.speak(spoken, language=lang)

    if _should_show_on_display(result.action):
        assistant.display.show_block(
            title,
            lines,
            duration=assistant.default_overlay_seconds,
        )

    return True