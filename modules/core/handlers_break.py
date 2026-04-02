from __future__ import annotations

from modules.system.utils import append_log


def handle_break_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")

    if minutes is None:
        assistant.pending_follow_up = {"type": "break_duration", "lang": lang}
        assistant._show_localized_block(
            lang,
            "BREAK MODE",
            "BREAK MODE",
            ["podaj dlugosc przerwy", "w minutach lub sekundach"],
            ["tell me the break duration", "in minutes or seconds"],
            duration=8.0,
        )
        assistant._speak_localized(
            lang,
            "Jak długa ma być przerwa?",
            "How long should the break be?",
        )
        return True

    return start_break(assistant, float(minutes), lang)


def start_break(assistant, minutes: float, lang: str) -> bool:
    if minutes <= 0:
        assistant._speak_localized(
            lang,
            "Czas musi być większy od zera.",
            "The duration must be greater than zero.",
        )
        return True

    assistant.pending_follow_up = None
    assistant.pending_confirmation = None

    ok, message = assistant.timer.start(float(minutes), "break")
    if not ok:
        assistant._show_localized_block(
            lang,
            "BREAK MODE",
            "BREAK MODE",
            ["inny timer juz dziala"],
            ["another timer is already running"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Inny timer już działa. Najpierw go zatrzymaj.",
            "Another timer is already running. Please stop it first.",
        )
        append_log(message)
        return True

    return True


def on_break_started(assistant, minutes: float) -> None:
    assistant.state["current_timer"] = "break"
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = True
    assistant._save_state()

    append_log(f"Break mode started for {minutes:g} minute(s).")

    lang = assistant.last_language
    total_seconds = int(round(minutes * 60))
    spoken_duration = assistant._format_duration_text(total_seconds, lang)

    assistant.display.show_block(
        assistant._localized(lang, "BREAK MODE", "BREAK MODE"),
        [
            f"{minutes:g} min",
            assistant._localized(lang, "czas na przerwe", "time for a break"),
        ],
        duration=6.0,
    )

    assistant._speak_localized(
        lang,
        f"Uruchomiłam break mode na {spoken_duration}.",
        f"I started break mode for {spoken_duration}.",
    )


def on_break_finished(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Break mode finished.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "BREAK DONE", "BREAK DONE"),
        [
            assistant._localized(lang, "przerwa zakonczona", "break finished"),
            assistant._localized(lang, "wracaj kiedy chcesz", "come back when ready"),
        ],
        duration=8.0,
    )

    assistant._speak_localized(
        lang,
        "Przerwa dobiegła końca. Możesz wrócić do pracy albo nauki, kiedy będziesz gotowy.",
        "Your break is finished. You can go back to work or studying whenever you are ready.",
    )


def on_break_stopped(assistant) -> None:
    assistant.state["current_timer"] = None
    assistant.state["focus_mode"] = False
    assistant.state["break_mode"] = False
    assistant._save_state()

    append_log("Break mode stopped.")

    lang = assistant.last_language

    assistant.display.show_block(
        assistant._localized(lang, "BREAK STOP", "BREAK STOP"),
        [
            assistant._localized(lang, "przerwa zatrzymana", "break stopped"),
        ],
        duration=6.0,
    )

    assistant._speak_localized(
        lang,
        "Zatrzymałam break mode.",
        "I stopped break mode.",
    )