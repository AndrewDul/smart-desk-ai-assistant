from __future__ import annotations

from datetime import datetime

from modules.core.language import localized, speak_localized


def show_localized_block(
    assistant,
    lang: str,
    title_pl: str,
    title_en: str,
    lines_pl: list[str],
    lines_en: list[str],
    duration: float | None = None,
) -> None:
    assistant.display.show_block(
        localized(lang, title_pl, title_en),
        lines_pl if lang == "pl" else lines_en,
        duration=assistant.default_overlay_seconds if duration is None else duration,
    )


def show_capabilities(assistant, lang: str) -> None:
    show_localized_block(
        assistant,
        lang,
        "CO POTRAFIĘ",
        "HOW I CAN HELP",
        [
            "pamiec i przypomnienia",
            "timery focus przerwa",
            "godzina data dzien",
            "ekran oled i status",
            "pl i en",
        ],
        [
            "memory and reminders",
            "timers focus break",
            "time date and day",
            "oled and status",
            "polish and english",
        ],
        duration=12.0,
    )


def offer_oled_display(
    assistant,
    lang: str,
    title: str,
    lines: list[str],
    speak_prompt: bool = True,
) -> None:
    assistant.pending_follow_up = {
        "type": "display_offer",
        "lang": lang,
        "title": title,
        "lines": lines,
    }

    if speak_prompt:
        speak_localized(
            assistant,
            lang,
            "Czy chcesz, żebym pokazała to na ekranie?",
            "Would you like me to show that on the screen?",
        )


def action_label(action: str, lang: str) -> str:
    labels = {
        "help": {"pl": "pomoc", "en": "help"},
        "status": {"pl": "stan", "en": "status"},
        "memory_list": {"pl": "pamięć", "en": "memory"},
        "memory_clear": {"pl": "wyczyść pamięć", "en": "clear memory"},
        "reminders_list": {"pl": "przypomnienia", "en": "reminders"},
        "reminder_delete": {"pl": "usuń przypomnienie", "en": "delete reminder"},
        "reminders_clear": {"pl": "wyczyść przypomnienia", "en": "clear reminders"},
        "timer_stop": {"pl": "wyłącz timer", "en": "stop timer"},
        "introduce_self": {"pl": "przedstaw się", "en": "introduce yourself"},
        "ask_time": {"pl": "godzina", "en": "time"},
        "show_time": {"pl": "pokaż godzinę", "en": "show time"},
        "ask_date": {"pl": "data", "en": "date"},
        "show_date": {"pl": "pokaż datę", "en": "show date"},
        "ask_day": {"pl": "dzień", "en": "day"},
        "show_day": {"pl": "pokaż dzień", "en": "show day"},
        "ask_year": {"pl": "rok", "en": "year"},
        "show_year": {"pl": "pokaż rok", "en": "show year"},
        "timer_start": {"pl": "timer", "en": "timer"},
        "focus_start": {"pl": "focus mode", "en": "focus mode"},
        "break_start": {"pl": "tryb przerwy", "en": "break mode"},
        "memory_store": {"pl": "zapamiętywanie", "en": "remembering"},
        "memory_recall": {"pl": "odczyt pamięci", "en": "memory recall"},
        "memory_forget": {"pl": "usuwanie z pamięci", "en": "memory delete"},
        "exit": {"pl": "wyjście", "en": "exit"},
        "shutdown": {"pl": "wyłącz system", "en": "shutdown"},
    }
    return labels.get(action, {}).get(lang, action)


def format_temporal_text(kind: str, lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()

    if kind == "time":
        value = now.strftime("%H:%M")
        spoken = localized(lang, f"Jest {value}.", f"It is {value}.")
        title = localized(lang, "GODZINA", "TIME")
        lines = [value]
        return spoken, title, lines

    if kind == "date":
        value = now.strftime("%d-%m-%Y")
        spoken = localized(lang, f"Dzisiejsza data to {value}.", f"Today's date is {value}.")
        title = localized(lang, "DATA", "DATE")
        lines = [value]
        return spoken, title, lines

    if kind == "day":
        days_en = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        days_pl = [
            "poniedziałek",
            "wtorek",
            "środa",
            "czwartek",
            "piątek",
            "sobota",
            "niedziela",
        ]
        value = days_pl[now.weekday()] if lang == "pl" else days_en[now.weekday()]
        spoken = localized(lang, f"Dzisiaj jest {value}.", f"Today is {value}.")
        title = localized(lang, "DZIEŃ", "DAY")
        lines = [value]
        return spoken, title, lines

    value = str(now.year)
    spoken = localized(lang, f"Mamy rok {value}.", f"The year is {value}.")
    title = localized(lang, "ROK", "YEAR")
    lines = [value]
    return spoken, title, lines