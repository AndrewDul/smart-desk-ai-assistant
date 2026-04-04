from __future__ import annotations


def _remember_system_reply(
    assistant,
    *,
    spoken: str,
    lang: str,
    action: str,
    extra_metadata: dict | None = None,
) -> None:
    if not hasattr(assistant, "_remember_assistant_turn"):
        return

    metadata = {
        "source": "system_handler",
        "route_kind": "action",
        "action": action,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    assistant._remember_assistant_turn(
        spoken,
        language=lang,
        metadata=metadata,
    )


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

    spoken = _help_voice_text(lang)

    assistant.display.show_block(
        assistant._localized(lang, "JAK MOGĘ POMÓC", "HOW I CAN HELP"),
        _help_screen_lines(lang),
        duration=12.0,
    )
    assistant.voice_out.speak(spoken, language=lang)

    _remember_system_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="help",
    )
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

        _remember_system_reply(
            assistant,
            spoken=spoken,
            lang=lang,
            action="introduce_self",
            extra_metadata={"variant": "name_only"},
        )
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

    _remember_system_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="introduce_self",
        extra_metadata={"variant": "full_intro"},
    )
    return True


def handle_status(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    timer_status = assistant.timer.status()
    memory_count = len(assistant.memory.get_all())
    reminder_count = len(assistant.reminders.list_all())
    current_timer = assistant.state.get("current_timer") or ("brak" if lang == "pl" else "none")
    timer_running = bool(timer_status.get("running"))

    if lang == "pl":
        lines = [
            f"focus: {'ON' if assistant.state.get('focus_mode') else 'OFF'}",
            f"przerwa: {'ON' if assistant.state.get('break_mode') else 'OFF'}",
            f"timer: {current_timer}",
            f"pamiec: {memory_count}",
            f"przypomnienia: {reminder_count}",
            f"dziala: {'TAK' if timer_running else 'NIE'}",
        ]
        spoken = (
            f"Aktualny stan wygląda tak. "
            f"Focus to {'włączony' if assistant.state.get('focus_mode') else 'wyłączony'}, "
            f"przerwa to {'włączona' if assistant.state.get('break_mode') else 'wyłączona'}, "
            f"timer to {current_timer}, "
            f"w pamięci mam {memory_count} wpisów, "
            f"a przypomnień jest {reminder_count}."
        )
    else:
        lines = [
            f"focus: {'ON' if assistant.state.get('focus_mode') else 'OFF'}",
            f"break: {'ON' if assistant.state.get('break_mode') else 'OFF'}",
            f"timer: {current_timer}",
            f"memory: {memory_count}",
            f"reminders: {reminder_count}",
            f"running: {'YES' if timer_running else 'NO'}",
        ]
        spoken = (
            f"Here is the current status. "
            f"Focus is {'on' if assistant.state.get('focus_mode') else 'off'}, "
            f"break is {'on' if assistant.state.get('break_mode') else 'off'}, "
            f"the timer is {current_timer}, "
            f"I have {memory_count} memory items, "
            f"and there are {reminder_count} reminders."
        )

    assistant.display.show_block(
        assistant._localized(lang, "STATUS", "STATUS"),
        lines,
        duration=assistant.default_overlay_seconds,
    )
    assistant.voice_out.speak(spoken, language=lang)

    _remember_system_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="status",
        extra_metadata={
            "focus_mode": bool(assistant.state.get("focus_mode")),
            "break_mode": bool(assistant.state.get("break_mode")),
            "current_timer": current_timer,
            "memory_count": memory_count,
            "reminder_count": reminder_count,
            "timer_running": timer_running,
        },
    )
    return True


def handle_exit(assistant, lang: str) -> bool:
    assistant.pending_confirmation = None
    assistant.pending_follow_up = {
        "type": "confirm_exit",
        "lang": lang,
    }

    spoken = assistant._localized(
        lang,
        "Czy na pewno mam zamknąć asystenta?",
        "Are you sure I should close the assistant?",
    )

    assistant.display.show_block(
        assistant._localized(lang, "ZAMKNĄĆ ASYSTENTA?", "CLOSE ASSISTANT?"),
        [assistant._localized(lang, "powiedz tak lub nie", "say yes or no")],
        duration=8.0,
    )
    assistant.voice_out.speak(spoken, language=lang)

    _remember_system_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="exit",
        extra_metadata={"phase": "confirmation_request"},
    )
    return True


def handle_shutdown(assistant, lang: str) -> bool:
    assistant.pending_confirmation = None
    assistant.pending_follow_up = {
        "type": "confirm_shutdown",
        "lang": lang,
    }

    spoken = assistant._localized(
        lang,
        "Czy na pewno mam wyłączyć system?",
        "Are you sure I should shut down the system?",
    )

    assistant.display.show_block(
        assistant._localized(lang, "WYŁĄCZYĆ SYSTEM?", "SHUT DOWN SYSTEM?"),
        [assistant._localized(lang, "powiedz tak lub nie", "say yes or no")],
        duration=8.0,
    )
    assistant.voice_out.speak(spoken, language=lang)

    _remember_system_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="shutdown",
        extra_metadata={"phase": "confirmation_request"},
    )
    return True