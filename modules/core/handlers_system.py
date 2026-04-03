from __future__ import annotations


def _help_screen_lines(lang: str) -> list[str]:
    if lang == "pl":
        return [
            "zapamietywanie informacji",
            "przypomnienia",
            "timer",
            "focus mode",
            "break mode",
        ]

    return [
        "remember information",
        "set reminders",
        "set timers",
        "focus mode",
        "break mode",
    ]


def _help_voice_text(lang: str) -> str:
    if lang == "pl":
        return (
            "Mogę pomagać ci na kilka głównych sposobów. "
            "Mogę zapamiętywać informacje, ustawiać przypomnienia, ustawiać timer, "
            "uruchamiać focus mode oraz break mode. "
            "To są teraz moje główne funkcje."
        )

    return (
        "I can help you in a few main ways. "
        "I can remember information, set reminders, set timers, "
        "and start focus mode or break mode. "
        "These are my main features right now."
    )


def handle_help(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    assistant.display.show_block(
        assistant._localized(lang, "JAK MOGĘ POMÓC", "HOW I CAN HELP"),
        _help_screen_lines(lang),
        duration=12.0,
    )

    assistant.voice_out.speak(_help_voice_text(lang), language=lang)
    return True


def handle_introduce_self(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    normalized_last = ""
    try:
        normalized_last = assistant._normalize_text(
            getattr(getattr(assistant, "parser", None), "_last_raw_text", "")
        )
    except Exception:
        normalized_last = ""

    # Fallback: rely on last raw text passed through handle_command if available.
    if not normalized_last:
        normalized_last = getattr(assistant, "_last_normalized_command_text", "")

    asks_only_name = normalized_last in {
        "jak sie nazywasz",
        "what is your name",
        "what s your name",
        "tell me your name",
        "say your name",
    }

    if asks_only_name:
        if lang == "pl":
            title = "NeXa"
            lines = [
                "nazywam sie NeXa",
            ]
            spoken = "Nazywam się NeXa."
        else:
            title = "NeXa"
            lines = [
                "my name is NeXa",
            ]
            spoken = "My name is NeXa."

        assistant.display.show_block(title, lines, duration=6.0)
        assistant.voice_out.speak(spoken, language=lang)
        return True

    if lang == "pl":
        title = "NeXa"
        lines = [
            "nazywam sie NeXa",
            "asystent AI",
            "raspberry pi 5",
            "ucze sie swiata",
        ]
        spoken = (
            "Nazywam się NeXa i jestem asystentem AI rozwijanym na Raspberry Pi 5. "
            "Szybko się uczę, bardzo chętnie poznaję świat i lubię pomagać ludziom."
        )
    else:
        title = "NeXa"
        lines = [
            "my name is NeXa",
            "AI assistant",
            "raspberry pi 5",
            "learning the world",
        ]
        spoken = (
            "My name is NeXa and I am an AI assistant being developed on Raspberry Pi 5. "
            "I learn quickly, I am very curious about the world, and I really enjoy helping people."
        )

    assistant.display.show_block(title, lines, duration=10.0)
    assistant.voice_out.speak(spoken, language=lang)
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