from __future__ import annotations


_TEMPORAL_KIND_BY_ACTION = {
    "ask_time": "time",
    "show_time": "time",
    "ask_date": "date",
    "show_date": "date",
    "ask_day": "day",
    "show_day": "day",
    "ask_year": "year",
    "show_year": "year",
}


def _resolve_kind(action: str) -> str:
    normalized = str(action or "").strip().lower()
    return _TEMPORAL_KIND_BY_ACTION.get(normalized, "time")


def _should_show_on_display(action: str) -> bool:
    normalized = str(action or "").strip().lower()
    return normalized.startswith("show_")


def _build_display_offer_prompt(assistant, lang: str, spoken: str) -> str:
    prompt = assistant._localized(
        lang,
        "Czy chcesz, żebym pokazała to na ekranie?",
        "Would you like me to show that on the screen?",
    )
    return f"{spoken} {prompt}".strip()


def _remember_temporal_reply(
    assistant,
    *,
    spoken: str,
    lang: str,
    action: str,
    kind: str,
    mode: str,
) -> None:
    if not hasattr(assistant, "_remember_assistant_turn"):
        return

    assistant._remember_assistant_turn(
        spoken,
        language=lang,
        metadata={
            "source": "temporal_handler",
            "route_kind": "action",
            "action": action,
            "temporal_kind": kind,
            "temporal_mode": mode,
        },
    )


def _set_display_offer_follow_up(
    assistant,
    *,
    lang: str,
    title: str,
    lines: list[str],
    action: str,
    kind: str,
) -> None:
    assistant.pending_follow_up = {
        "type": "display_offer",
        "lang": lang,
        "title": title,
        "lines": list(lines),
        "action": action,
        "temporal_kind": kind,
    }


def handle_temporal_intent(assistant, result, lang: str) -> bool:
    action = str(getattr(result, "action", "") or "").strip().lower()
    kind = _resolve_kind(action)

    spoken, title, lines = assistant._format_temporal_text(kind, lang)

    assistant.pending_confirmation = None

    if _should_show_on_display(action):
        assistant.pending_follow_up = None
        assistant.voice_out.speak(spoken, language=lang)
        assistant.display.show_block(
            title,
            lines,
            duration=assistant.default_overlay_seconds,
        )
        _remember_temporal_reply(
            assistant,
            spoken=spoken,
            lang=lang,
            action=action,
            kind=kind,
            mode="show_immediately",
        )
        return True

    spoken_with_offer = _build_display_offer_prompt(assistant, lang, spoken)
    _set_display_offer_follow_up(
        assistant,
        lang=lang,
        title=title,
        lines=lines,
        action=action,
        kind=kind,
    )
    assistant.voice_out.speak(spoken_with_offer, language=lang)

    _remember_temporal_reply(
        assistant,
        spoken=spoken_with_offer,
        lang=lang,
        action=action,
        kind=kind,
        mode="offer_display",
    )

    return True