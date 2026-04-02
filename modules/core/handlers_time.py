from __future__ import annotations

from datetime import datetime


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


def _resolve_kind(action: str) -> str:
    if "time" in action:
        return "time"
    if "date" in action:
        return "date"
    if "day" in action:
        return "day"
    return "year"


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

    spoken = f"The current year is {year_text}."
    title = "YEAR"
    lines = [
        year_text,
        "current year",
    ]
    return spoken, title, lines


def _build_payload(kind: str, lang: str) -> tuple[str, str, list[str]]:
    if kind == "time":
        return _time_payload(lang)
    if kind == "date":
        return _date_payload(lang)
    if kind == "day":
        return _day_payload(lang)
    return _year_payload(lang)


def handle_temporal_intent(assistant, result, lang: str) -> bool:
    kind = _resolve_kind(result.action)
    spoken, title, lines = _build_payload(kind, lang)

    assistant.voice_out.speak(spoken, language=lang)

    if result.action.startswith("show_"):
        assistant.display.show_block(
            title,
            lines,
            duration=assistant.default_overlay_seconds,
        )
        return True

    assistant._offer_oled_display(
        lang,
        title,
        lines,
        speak_prompt=True,
    )
    return True