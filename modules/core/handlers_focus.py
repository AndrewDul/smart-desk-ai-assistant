from __future__ import annotations

from modules.system.utils import append_log


def _remember_focus_reply(
    assistant,
    *,
    spoken: str,
    lang: str,
    action: str,
    extra_metadata: dict | None = None,
) -> None:
    if not hasattr(assistant, "_remember_assistant_turn"):
        return

    cleaned = " ".join(str(spoken or "").split()).strip()
    if not cleaned:
        return

    metadata = {
        "source": "focus_handler",
        "route_kind": "action",
        "action": action,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    assistant._remember_assistant_turn(
        cleaned,
        language=lang,
        metadata=metadata,
    )


def _speak_and_remember_localized(
    assistant,
    lang: str,
    pl_text: str,
    en_text: str,
    *,
    action: str,
    extra_metadata: dict | None = None,
) -> None:
    assistant._speak_localized(lang, pl_text, en_text)
    spoken = assistant._localized(lang, pl_text, en_text)
    _remember_focus_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action=action,
        extra_metadata=extra_metadata,
    )


def handle_focus_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")

    if minutes is None:
        assistant.pending_follow_up = {"type": "focus_duration", "lang": lang}
        assistant._show_localized_block(
            lang,
            "FOCUS MODE",
            "FOCUS MODE",
            ["podaj dlugosc sesji", "w minutach lub sekundach"],
            ["tell me the session duration", "in minutes or seconds"],
            duration=8.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            "Jak długa ma być sesja focus?",
            "How long should the focus session be?",
            action="focus_start",
            extra_metadata={"phase": "request_duration"},
        )
        return True

    return start_focus(assistant, float(minutes), lang)


def start_focus(assistant, minutes: float, lang: str) -> bool:
    if minutes <= 0:
        _speak_and_remember_localized(
            assistant,
            lang,
            "Czas musi być większy od zera.",
            "The duration must be greater than zero.",
            action="focus_start",
            extra_metadata={"phase": "invalid_duration", "minutes": minutes},
        )
        return True

    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    ok, message = assistant.timer.start(float(minutes), "focus")
    if not ok:
        assistant._show_localized_block(
            lang,
            "FOCUS MODE",
            "FOCUS MODE",
            ["inny timer juz dziala"],
            ["another timer is already running"],
            duration=6.0,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            "Inny timer już działa. Najpierw go zatrzymaj.",
            "Another timer is already running. Please stop it first.",
            action="focus_start",
            extra_metadata={"phase": "busy", "minutes": minutes},
        )
        append_log(message)
        return True

    return True


def on_focus_started(assistant, minutes: float) -> None:
    assistant.state["current_timer"] = "focus"
    assistant.state["focus_mode"] = True
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log(f"Focus mode started for {minutes:g} minute(s).")

    lang = assistant.last_language
    total_seconds = int(round(minutes * 60))
    spoken_duration = assistant._format_duration_text(total_seconds, lang)

    assistant.display.show_block(
        assistant._localized(lang, "FOCUS MODE", "FOCUS MODE"),
        [
            f"{minutes:g} min",
            assistant._localized(lang, "czas na skupienie", "time to focus"),
        ],
        duration=6.0,
    )

    spoken = assistant._localized(
        lang,
        f"Uruchomiłam focus mode na {spoken_duration}.",
        f"I started focus mode for {spoken_duration}.",
    )
    assistant.voice_out.speak(spoken, language=lang)
    _remember_focus_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="focus_start",
        extra_metadata={
            "phase": "started",
            "minutes": minutes,
            "seconds": total_seconds,
        },
    )


def on_focus_finished(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Focus mode finished.")

    lang = assistant.last_language
    spoken = assistant._localized(
        lang,
        "Sesja focus dobiegła końca. Kiedy będziesz gotowy, powiedz NeXa i mogę uruchomić przerwę.",
        "Your focus session is finished. When you are ready, say NeXa and I can start a break.",
    )

    assistant._deliver_async_notification(
        lang=lang,
        spoken_text=spoken,
        display_title=assistant._localized(lang, "FOCUS DONE", "FOCUS DONE"),
        display_lines=[
            assistant._localized(lang, "sesja zakonczona", "session finished"),
            assistant._localized(lang, "powiedz nexa po przerwe", "say NeXa for a break"),
        ],
        source="focus",
        route_kind="focus",
        action="focus_finished",
        display_duration=8.0,
        extra_metadata={"phase": "finished_return_to_standby"},
    )
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Focus mode finished.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "FOCUS DONE", "FOCUS DONE"),
        [
            assistant._localized(lang, "sesja zakonczona", "session finished"),
            assistant._localized(lang, "powiedz yes/no lub czas", "say yes/no or duration"),
        ],
        duration=8.0,
    )

    assistant.pending_follow_up = {
        "type": "post_focus_break_offer",
        "lang": lang,
    }

    spoken = assistant._localized(
        lang,
        "Sesja focus dobiegła końca. Mogę teraz uruchomić przerwę. Powiedz tak, nie, albo od razu podaj długość przerwy.",
        "Your focus session is finished. I can start a break now. Say yes, no, or tell me the break duration right away.",
    )
    assistant.voice_out.speak(spoken, language=lang)
    _remember_focus_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="focus_finished",
        extra_metadata={"phase": "finished_break_offer"},
    )


def on_focus_stopped(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Focus mode stopped.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "FOCUS STOP", "FOCUS STOP"),
        [
            assistant._localized(lang, "focus zatrzymany", "focus stopped"),
        ],
        duration=6.0,
    )

    spoken = assistant._localized(
        lang,
        "Zatrzymałam focus mode.",
        "I stopped focus mode.",
    )
    assistant.voice_out.speak(spoken, language=lang)
    _remember_focus_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        action="focus_stop",
        extra_metadata={"phase": "stopped"},
    )