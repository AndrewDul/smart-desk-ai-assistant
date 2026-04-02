from __future__ import annotations


def handle_help(assistant, lang: str) -> bool:
    assistant._show_capabilities(lang)
    assistant._speak_localized(
        lang,
        "Mogę zapamiętywać informacje, ustawiać przypomnienia i timery, podawać godzinę, datę, dzień i rok, prowadzić focus mode i przerwę, usuwać pamięć i przypomnienia oraz pokazywać informacje na ekranie.",
        "I can remember information, set reminders and timers, tell you the time, date, day and year, run focus and break sessions, remove memory and reminders, and show information on the screen.",
    )
    return True


def handle_introduce_self(assistant, lang: str) -> bool:
    assistant.pending_follow_up = {
        "type": "capture_name",
        "lang": lang,
    }
    assistant._show_localized_block(
        lang,
        "CZEŚĆ",
        "HELLO",
        [
            "jestem Smart Assistant",
            "mogę ci pomagać",
            "jak masz na imię?",
        ],
        [
            "I am Smart Assistant",
            "I can help you",
            "what is your name?",
        ],
        duration=10.0,
    )
    assistant._speak_localized(
        lang,
        "Jestem Smart Assistant. Mogę zapamiętywać rzeczy, ustawiać przypomnienia i pomagać ci podczas nauki. Jak masz na imię?",
        "I am Smart Assistant. I can remember things, set reminders, and help you during study sessions. What is your name?",
    )
    return True


def handle_status(assistant, lang: str) -> bool:
    timer_status = assistant.timer.status()
    memory_count = len(assistant.memory.get_all())
    reminder_count = len(assistant.reminders.list_all())

    if lang == "pl":
        lines = [
            f"focus: {'ON' if assistant.state.get('focus_mode') else 'OFF'}",
            f"przerwa: {'ON' if assistant.state.get('break_mode') else 'OFF'}",
            f"timer: {assistant.state.get('current_timer') or 'brak'}",
            f"pamiec: {memory_count}",
            f"przypomnienia: {reminder_count}",
            f"dziala: {'TAK' if timer_status.get('running') else 'NIE'}",
        ]
        spoken = "Pokazuję aktualny stan asystenta."
    else:
        lines = [
            f"focus: {'ON' if assistant.state.get('focus_mode') else 'OFF'}",
            f"break: {'ON' if assistant.state.get('break_mode') else 'OFF'}",
            f"timer: {assistant.state.get('current_timer') or 'none'}",
            f"memory: {memory_count}",
            f"reminders: {reminder_count}",
            f"running: {'YES' if timer_status.get('running') else 'NO'}",
        ]
        spoken = "Showing the current assistant status."

    assistant.display.show_block(
        assistant._localized(lang, "STATUS", "STATUS"),
        lines,
        duration=assistant.default_overlay_seconds,
    )
    assistant.voice_out.speak(spoken, language=lang)
    return True


def handle_exit(assistant, lang: str) -> bool:
    assistant.pending_follow_up = {
        "type": "confirm_exit",
        "lang": lang,
    }
    assistant.display.show_block(
        assistant._localized(lang, "ZAMKNĄĆ ASYSTENTA?", "CLOSE ASSISTANT?"),
        [assistant._localized(lang, "powiedz tak lub nie", "say yes or no")],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        "Czy na pewno mam zamknąć asystenta?",
        "Are you sure I should close the assistant?",
    )
    return True


def handle_shutdown(assistant, lang: str) -> bool:
    assistant.pending_follow_up = {
        "type": "confirm_shutdown",
        "lang": lang,
    }
    assistant.display.show_block(
        assistant._localized(lang, "WYŁĄCZYĆ SYSTEM?", "SHUT DOWN SYSTEM?"),
        [assistant._localized(lang, "powiedz tak lub nie", "say yes or no")],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        "Czy na pewno mam wyłączyć system?",
        "Are you sure I should shut down the system?",
    )
    return True