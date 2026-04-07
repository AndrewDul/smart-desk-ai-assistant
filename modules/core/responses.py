from __future__ import annotations

from datetime import datetime

from modules.core.language import localized, speak_localized


_DAYS_EN = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_DAYS_PL = [
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
]

_MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

_MONTHS_PL = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]


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
        "JAK MOGĘ POMÓC",
        "HOW I CAN HELP",
        [
            "zapamietywanie informacji",
            "przypomnienia",
            "timer",
            "focus mode",
            "break mode",
        ],
        [
            "remember information",
            "set reminders",
            "set timers",
            "focus mode",
            "break mode",
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
    # Premium flow:
    # do not ask whether something should be shown.
    # If this helper is still called from any older code path,
    # just show the content directly and do not create any follow-up state.
    assistant.pending_follow_up = None
    assistant.display.show_block(
        title,
        lines,
        duration=assistant.default_overlay_seconds,
    )

    if speak_prompt:
        # Intentionally no spoken question here.
        # This keeps backward compatibility without bringing back
        # the old "show on screen?" conversational interruption.
        return


def action_label(action: str, lang: str) -> str:
    labels = {
        "help": {"pl": "pomoc", "en": "help"},
        "status": {"pl": "stan", "en": "status"},
        "memory_list": {"pl": "pamięć", "en": "memory"},
        "memory_clear": {"pl": "wyczyść pamięć", "en": "clear memory"},
        "memory_store": {"pl": "zapamiętaj", "en": "remember"},
        "memory_recall": {"pl": "odczytaj pamięć", "en": "recall memory"},
        "memory_forget": {"pl": "usuń z pamięci", "en": "forget from memory"},
        "reminders_list": {"pl": "przypomnienia", "en": "reminders"},
        "reminder_create": {"pl": "ustaw przypomnienie", "en": "create reminder"},
        "reminder_delete": {"pl": "usuń przypomnienie", "en": "delete reminder"},
        "reminders_clear": {"pl": "wyczyść przypomnienia", "en": "clear reminders"},
        "timer_start": {"pl": "timer", "en": "timer"},
        "timer_stop": {"pl": "zatrzymaj timer", "en": "stop timer"},
        "focus_start": {"pl": "focus mode", "en": "focus mode"},
        "break_start": {"pl": "break mode", "en": "break mode"},
        "introduce_self": {"pl": "przedstaw się", "en": "introduce yourself"},
        "ask_time": {"pl": "godzina", "en": "time"},
        "show_time": {"pl": "pokaż godzinę", "en": "show time"},
        "ask_date": {"pl": "data", "en": "date"},
        "show_date": {"pl": "pokaż datę", "en": "show date"},
        "ask_day": {"pl": "dzień", "en": "day"},
        "show_day": {"pl": "pokaż dzień", "en": "show day"},
        "ask_year": {"pl": "rok", "en": "year"},
        "show_year": {"pl": "pokaż rok", "en": "show year"},
        "exit": {"pl": "zamknij asystenta", "en": "close assistant"},
        "shutdown": {"pl": "wyłącz system", "en": "shut down system"},
    }
    return labels.get(action, {}).get(lang, action)


def _time_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()
    digital_value = now.strftime("%H:%M")

    if lang == "pl":
        spoken = f"Jest {digital_value}."
        title = "GODZINA"
        lines = [
            digital_value,
            "aktualny czas",
        ]
        return spoken, title, lines

    spoken_value = now.strftime("%I:%M %p").lstrip("0")
    spoken = f"It is {spoken_value}."
    title = "TIME"
    lines = [
        digital_value,
        "current time",
    ]
    return spoken, title, lines


def _date_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()

    if lang == "pl":
        weekday = _DAYS_PL[now.weekday()]
        month = _MONTHS_PL[now.month - 1]
        spoken = f"Dzisiaj jest {weekday}, {now.day} {month} {now.year}."
        title = "DATA"
        lines = [
            now.strftime("%d-%m-%Y"),
            weekday,
        ]
        return spoken, title, lines

    weekday = _DAYS_EN[now.weekday()]
    month = _MONTHS_EN[now.month - 1]
    spoken = f"Today is {weekday}, {month} {now.day}, {now.year}."
    title = "DATE"
    lines = [
        now.strftime("%d-%m-%Y"),
        weekday,
    ]
    return spoken, title, lines


def _day_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()

    if lang == "pl":
        weekday = _DAYS_PL[now.weekday()]
        spoken = f"Dzisiaj jest {weekday}."
        title = "DZIEŃ"
        lines = [
            weekday,
            now.strftime("%d-%m-%Y"),
        ]
        return spoken, title, lines

    weekday = _DAYS_EN[now.weekday()]
    spoken = f"Today is {weekday}."
    title = "DAY"
    lines = [
        weekday,
        now.strftime("%d-%m-%Y"),
    ]
    return spoken, title, lines


def _year_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()
    year_text = str(now.year)

    if lang == "pl":
        spoken = f"Mamy rok {year_text}."
        title = "ROK"
        lines = [
            year_text,
            "aktualny rok",
        ]
        return spoken, title, lines

def _month_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()
    month_name_en = now.strftime("%B")
    month_name_pl = {
        1: "styczeń",
        2: "luty",
        3: "marzec",
        4: "kwiecień",
        5: "maj",
        6: "czerwiec",
        7: "lipiec",
        8: "sierpień",
        9: "wrzesień",
        10: "październik",
        11: "listopad",
        12: "grudzień",
    }[now.month]

    if lang == "pl":
        spoken = f"Mamy miesiąc {month_name_pl}."
        title = "MIESIĄC"
        lines = [
            month_name_pl,
            now.strftime("%m-%Y"),
        ]
        return spoken, title, lines

    spoken = f"The current month is {month_name_en}."
    title = "MONTH"
    lines = [
        month_name_en,
        now.strftime("%m-%Y"),
    ]
    return spoken, title, lines


def _year_payload(lang: str) -> tuple[str, str, list[str]]:
    now = datetime.now()
    year_text = str(now.year)

    if lang == "pl":
        spoken = f"Mamy rok {year_text}."
        title = "ROK"
        lines = [
            year_text,
            "aktualny rok",
        ]
        return spoken, title, lines

    spoken = f"The current year is {year_text}."
    title = "YEAR"
    lines = [
        year_text,
        "current year",
    ]
    return spoken, title, lines


def format_temporal_text(kind: str, lang: str) -> tuple[str, str, list[str]]:
    if kind == "time":
        return _time_payload(lang)
    if kind == "date":
        return _date_payload(lang)
    if kind == "day":
        return _day_payload(lang)
    if kind == "month":
        return _month_payload(lang)
    return _year_payload(lang)