from __future__ import annotations


def handle_temporal_intent(assistant, result, lang: str) -> bool:
    if "time" in result.action:
        kind = "time"
    elif "date" in result.action:
        kind = "date"
    elif "day" in result.action:
        kind = "day"
    else:
        kind = "year"

    spoken, title, lines = assistant._format_temporal_text(kind, lang)
    assistant.voice_out.speak(spoken, language=lang)

    if result.action.startswith("show_"):
        assistant.display.show_block(title, lines, duration=assistant.default_overlay_seconds)
    else:
        assistant._offer_oled_display(lang, title, lines)

    return True