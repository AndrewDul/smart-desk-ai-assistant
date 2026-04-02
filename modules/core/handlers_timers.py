from __future__ import annotations


def handle_timer_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")
    if minutes is None:
        assistant.pending_follow_up = {"type": "timer_duration", "lang": lang}
        assistant._speak_localized(
            lang,
            "Na jak długo mam ustawić timer?",
            "How long should I set the timer for?",
        )
        return True

    return assistant._start_timer_mode(float(minutes), "timer", lang)


def handle_focus_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")
    if minutes is None:
        assistant.pending_follow_up = {"type": "focus_duration", "lang": lang}
        assistant._speak_localized(
            lang,
            "Jak długa ma być sesja focus?",
            "How long should the focus session be?",
        )
        return True

    return assistant._start_timer_mode(float(minutes), "focus", lang)


def handle_break_start(assistant, result, lang: str) -> bool:
    minutes = result.data.get("minutes")
    if minutes is None:
        assistant.pending_follow_up = {"type": "break_duration", "lang": lang}
        assistant._speak_localized(
            lang,
            "Jak długa ma być przerwa?",
            "How long should the break be?",
        )
        return True

    return assistant._start_timer_mode(float(minutes), "break", lang)


def handle_timer_stop(assistant, lang: str) -> bool:
    assistant.pending_follow_up = None
    ok, _ = assistant.timer.stop()
    if not ok:
        assistant._speak_localized(
            lang,
            "Żaden timer nie jest teraz uruchomiony.",
            "No timer is currently running.",
        )
    return True