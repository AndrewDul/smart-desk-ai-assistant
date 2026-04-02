from __future__ import annotations

from modules.system.utils import append_log


def handle_timer_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")

    if minutes is None:
        assistant.pending_follow_up = {"type": "timer_duration", "lang": lang}
        assistant._show_localized_block(
            lang,
            "TIMER",
            "TIMER",
            ["podaj czas", "w minutach lub sekundach"],
            ["tell me the duration", "in minutes or seconds"],
            duration=8.0,
        )
        assistant._speak_localized(
            lang,
            "Na jak długo mam ustawić timer?",
            "How long should I set the timer for?",
        )
        return True

    return start_timer(assistant, float(minutes), lang)


def handle_timer_stop(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None

    ok, _ = assistant.timer.stop()
    if not ok:
        assistant._show_localized_block(
            lang,
            "TIMER",
            "TIMER",
            ["timer nie dziala"],
            ["no timer is running"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Żaden timer nie jest teraz uruchomiony.",
            "No timer is currently running.",
        )

    return True


def start_timer(assistant, minutes: float, lang: str) -> bool:
    if minutes <= 0:
        assistant._speak_localized(
            lang,
            "Czas musi być większy od zera.",
            "The duration must be greater than zero.",
        )
        return True

    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    ok, message = assistant.timer.start(float(minutes), "timer")
    if not ok:
        assistant._show_localized_block(
            lang,
            "TIMER",
            "TIMER",
            ["inny timer juz dziala"],
            ["another timer is already running"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Timer już działa. Najpierw go zatrzymaj.",
            "A timer is already running. Please stop it first.",
        )
        append_log(message)
        return True

    return True


def on_timer_started(assistant, minutes: float) -> None:
    assistant.state["current_timer"] = "timer"
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log(f"Timer started for {minutes:g} minute(s).")

    lang = assistant.last_language
    total_seconds = int(round(minutes * 60))
    spoken_duration = assistant._format_duration_text(total_seconds, lang)

    assistant.display.show_block(
        assistant._localized(lang, "TIMER START", "TIMER START"),
        [
            f"{minutes:g} min",
            assistant._localized(lang, "timer uruchomiony", "timer started"),
        ],
        duration=6.0,
    )

    assistant._speak_localized(
        lang,
        f"Ustawiłam timer na {spoken_duration}.",
        f"I set a timer for {spoken_duration}.",
    )


def on_timer_finished(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Timer finished.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "TIME IS UP", "TIME IS UP"),
        [
            assistant._localized(lang, "timer zakonczony", "timer finished"),
        ],
        duration=6.0,
    )

    assistant._speak_localized(
        lang,
        "Minął ustawiony czas.",
        "Your timer has finished.",
    )


def on_timer_stopped(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Timer stopped.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "TIMER STOP", "TIMER STOP"),
        [
            assistant._localized(lang, "timer zatrzymany", "timer stopped"),
        ],
        duration=6.0,
    )

    assistant._speak_localized(
        lang,
        "Zatrzymałam timer.",
        "I stopped the timer.",
    )