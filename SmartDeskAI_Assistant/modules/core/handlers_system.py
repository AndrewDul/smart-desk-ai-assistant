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
            "rozmowa po polsku i angielsku",
            "zapamietywanie informacji",
            "przypomnienia i timery",
            "focus mode i break mode",
            "pomoc przy biurku",
        ]

    return [
        "conversation in polish and english",
        "remember information",
        "reminders and timers",
        "focus mode and break mode",
        "desk help",
    ]


def _help_voice_text(lang: str) -> str:
    if lang == "pl":
        return (
            "Mogę pomagać ci na kilka głównych sposobów. "
            "Mogę rozmawiać z tobą po polsku i po angielsku, zapamiętywać informacje, "
            "ustawiać przypomnienia i timery oraz uruchamiać focus mode i break mode. "
            "To są teraz moje najważniejsze funkcje."
        )

    return (
        "I can help you in a few main ways. "
        "I can talk with you in Polish and English, remember information, "
        "set reminders and timers, and start focus mode or break mode. "
        "These are my main features right now."
    )


def _name_only_payload(lang: str) -> tuple[str, list[str], str]:
    if lang == "pl":
        return (
            "NeXa",
            ["nazywam sie NeXa"],
            "Nazywam się NeXa.",
        )

    return (
        "NeXa",
        ["my name is NeXa"],
        "My name is NeXa.",
    )


def _full_intro_payload(lang: str) -> tuple[str, list[str], str]:
    if lang == "pl":
        title = "NeXa"
        lines = [
            "lokalny desk companion",
            "polski i english",
            "raspberry pi 5",
            "rozmowa i narzedzia",
        ]
        spoken = (
            "Jestem NeXa, lokalnym desk companionem działającym na Raspberry Pi 5. "
            "Mogę rozmawiać z tobą po polsku i po angielsku, pomagać w prostych zadaniach "
            "i wspierać cię przy biurku."
        )
        return title, lines, spoken

    title = "NeXa"
    lines = [
        "local desk companion",
        "polish and english",
        "raspberry pi 5",
        "conversation and tools",
    ]
    spoken = (
        "I am NeXa, a local desk companion running on Raspberry Pi 5. "
        "I can talk with you in Polish and English, help with simple tasks, "
        "and support you at your desk."
    )
    return title, lines, spoken


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

    normalized_last = getattr(assistant, "_last_normalized_command_text", "") or ""

    asks_only_name = normalized_last in {
        "jak sie nazywasz",
        "what is your name",
        "what s your name",
        "tell me your name",
        "say your name",
    }

    if asks_only_name:
        title, lines, spoken = _name_only_payload(lang)
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

    title, lines, spoken = _full_intro_payload(lang)

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
            "Aktualny stan wygląda tak. "
            f"Focus jest {'włączony' if assistant.state.get('focus_mode') else 'wyłączony'}, "
            f"przerwa jest {'włączona' if assistant.state.get('break_mode') else 'wyłączona'}, "
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
            "Here is the current status. "
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
        "Czy chcesz, żebym zamknęła asystenta?",
        "Do you want me to close the assistant?",
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
    assistant.pending_follow_up = None

    system_cfg = assistant.settings.get("system", {})
    allow_shutdown = bool(system_cfg.get("allow_shutdown_commands", False))

    if not allow_shutdown:
        spoken = assistant._localized(
            lang,
            "Wyłączanie systemu jest teraz wyłączone w ustawieniach.",
            "System shutdown is currently disabled in settings.",
        )

        assistant.display.show_block(
            "SHUTDOWN DISABLED",
            [assistant._localized(lang, "sprawdź ustawienia systemu", "check system settings")],
            duration=6.0,
        )
        assistant.voice_out.speak(spoken, language=lang)

        _remember_system_reply(
            assistant,
            spoken=spoken,
            lang=lang,
            action="shutdown",
            extra_metadata={"phase": "blocked_by_config"},
        )
        return True

    assistant.pending_follow_up = {
        "type": "confirm_shutdown",
        "lang": lang,
    }

    spoken = assistant._localized(
        lang,
        "Czy chcesz, żebym wyłączyła system?",
        "Do you want me to shut down the system?",
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
