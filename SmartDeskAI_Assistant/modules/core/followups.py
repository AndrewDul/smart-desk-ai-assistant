from __future__ import annotations

import re
from typing import Any

from modules.parsing.intent_parser import IntentResult


_NAME_BLOCKLIST = {
    "a",
    "an",
    "and",
    "assistant",
    "break",
    "bye",
    "cancel",
    "command",
    "commands",
    "date",
    "day",
    "exit",
    "focus",
    "godzina",
    "hello",
    "help",
    "hi",
    "menu",
    "minute",
    "minutes",
    "name",
    "nie",
    "no",
    "number",
    "okay",
    "pan",
    "pani",
    "please",
    "pomoc",
    "przerwa",
    "quit",
    "reminder",
    "second",
    "seconds",
    "show",
    "stan",
    "status",
    "system",
    "tak",
    "test",
    "time",
    "timer",
    "today",
    "yes",
}

_POLISH_NOISE_NAME_TOKENS = {
    "eee",
    "yyy",
    "hmm",
    "hm",
    "uh",
    "um",
}

_INTERRUPTABLE_ACTIONS = {
    "help",
    "status",
    "memory_list",
    "memory_clear",
    "memory_store",
    "memory_recall",
    "memory_forget",
    "reminders_list",
    "reminders_clear",
    "reminder_create",
    "reminder_delete",
    "timer_start",
    "timer_stop",
    "focus_start",
    "break_start",
    "introduce_self",
    "ask_time",
    "show_time",
    "ask_date",
    "show_date",
    "ask_day",
    "show_day",
    "ask_year",
    "show_year",
    "exit",
    "shutdown",
}

_TIMER_LIKE_ACTIONS = {"timer_start", "focus_start", "break_start"}

_MIXED_REPEAT_MARKERS = {
    "en": {
        "what",
        "what?",
        "repeat",
        "repeat that",
        "say that again",
        "again",
        "options",
        "what are the options",
        "what can i choose",
        "which options",
        "what did you say",
    },
    "pl": {
        "co",
        "co?",
        "powtorz",
        "powtórz",
        "jeszcze raz",
        "opcje",
        "jakie opcje",
        "jakie mam opcje",
        "co moge wybrac",
        "co mogę wybrać",
        "co powiedzialas",
        "co powiedziałaś",
    },
}

_SHUTDOWN_DELAY_SECONDS = 2.2


def _current_followup_type(assistant) -> str:
    follow_up = assistant.pending_follow_up or {}
    return str(follow_up.get("type", "")).strip() or "follow_up"


def _remember_followup_reply(
    assistant,
    *,
    spoken: str,
    lang: str,
    follow_type: str,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    if not hasattr(assistant, "_remember_assistant_turn"):
        return

    cleaned = " ".join(str(spoken or "").split()).strip()
    if not cleaned:
        return

    metadata: dict[str, Any] = {
        "source": "follow_up_handler",
        "route_kind": "follow_up",
        "follow_up_type": follow_type,
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
    follow_type: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    assistant._speak_localized(lang, pl_text, en_text)
    spoken = assistant._localized(lang, pl_text, en_text)
    _remember_followup_reply(
        assistant,
        spoken=spoken,
        lang=lang,
        follow_type=follow_type or _current_followup_type(assistant),
        extra_metadata=extra_metadata,
    )


def _normalize_name_token(token: str) -> str:
    cleaned = token.strip(" '-")
    if not cleaned:
        return ""
    return cleaned[:1].upper() + cleaned[1:].lower()


def _looks_like_name_candidate(token: str) -> bool:
    if not token:
        return False

    lowered = token.lower()
    if lowered in _NAME_BLOCKLIST:
        return False

    if lowered in _POLISH_NOISE_NAME_TOKENS:
        return False

    if not re.fullmatch(r"[A-Za-zÀ-ÿ'-]{2,20}", token):
        return False

    return True


def extract_name(text: str) -> str | None:
    raw = text.strip()

    patterns = [
        r"\b(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem)\s+([A-Za-zÀ-ÿ' -]{2,})$",
        r"\b(?:my name is|i am|i'm)\s+([A-Za-zÀ-ÿ' -]{2,})$",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if not match:
            continue

        first_token = match.group(1).strip().split()[0]
        if _looks_like_name_candidate(first_token):
            return _normalize_name_token(first_token)

    simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
    if len(simple_tokens) == 1:
        token = simple_tokens[0]
        if _looks_like_name_candidate(token):
            return _normalize_name_token(token)

    return None


def _yes_no_retry(assistant, lang: str) -> None:
    _speak_and_remember_localized(
        assistant,
        lang,
        "Powiedz tak albo nie.",
        "Please say yes or no.",
        follow_type=_current_followup_type(assistant),
        extra_metadata={"phase": "retry_yes_no"},
    )


def _short_line(text: str, limit: int = 24) -> str:
    cleaned = " ".join(str(text).strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _follow_up_language(assistant, current_lang: str) -> str:
    follow_up = assistant.pending_follow_up or {}
    stored = str(follow_up.get("lang", "")).strip().lower()
    if stored in {"pl", "en"}:
        return stored
    return current_lang


def _try_interrupt_with_new_command(assistant, text: str, lang: str) -> bool | None:
    result = assistant.parser.parse(text)
    if result.action not in _INTERRUPTABLE_ACTIONS:
        return None

    assistant.pending_confirmation = None
    assistant.pending_follow_up = None
    return assistant._execute_intent(
        IntentResult(
            action=result.action,
            data=result.data,
            normalized_text=result.normalized_text,
        ),
        lang,
    )


def _parse_confirmation_choice(text: str) -> int | None:
    lowered = text.lower().strip()
    normalized = re.sub(r"\s+", " ", lowered)

    first_markers = {
        "1",
        "one",
        "first",
        "option one",
        "option 1",
        "number one",
        "the first one",
        "pierwsza",
        "pierwszy",
        "opcja pierwsza",
        "opcja jeden",
        "numer jeden",
    }
    second_markers = {
        "2",
        "two",
        "second",
        "option two",
        "option 2",
        "number two",
        "the second one",
        "druga",
        "drugi",
        "opcja druga",
        "opcja dwa",
        "numer dwa",
    }

    if normalized in first_markers:
        return 0
    if normalized in second_markers:
        return 1

    return None


def _handle_display_offer_follow_up(assistant, follow_up: dict[str, Any], text: str, lang: str) -> bool:
    title = str(follow_up.get("title", "")).strip()
    lines = [str(line) for line in follow_up.get("lines", []) if str(line).strip()]
    action = str(follow_up.get("action", "")).strip().lower()
    temporal_kind = str(follow_up.get("temporal_kind", "")).strip().lower()

    if assistant._is_yes(text):
        assistant.pending_follow_up = None
        assistant.display.show_block(
            title,
            lines,
            duration=assistant.default_overlay_seconds,
        )
        _speak_and_remember_localized(
            assistant,
            lang,
            "Dobrze. Pokazuję to na ekranie.",
            "Okay. I am showing it on the screen.",
            follow_type="display_offer",
            extra_metadata={
                "phase": "accepted",
                "action": action,
                "temporal_kind": temporal_kind,
            },
        )
        return True

    if assistant._is_no(text):
        assistant.pending_follow_up = None
        _speak_and_remember_localized(
            assistant,
            lang,
            "Dobrze. Nie pokazuję tego na ekranie.",
            "Okay. I will not show it on the screen.",
            follow_type="display_offer",
            extra_metadata={
                "phase": "declined",
                "action": action,
                "temporal_kind": temporal_kind,
            },
        )
        return True

    interrupted = _try_interrupt_with_new_command(assistant, text, lang)
    if interrupted is not None:
        return interrupted

    _yes_no_retry(assistant, lang)
    return True


def _default_minutes_for_action(assistant, action: str) -> float | None:
    if action == "focus_start":
        return float(getattr(assistant.parser, "default_focus_minutes", 25))
    if action == "break_start":
        return float(getattr(assistant.parser, "default_break_minutes", 5))
    if action == "timer_start":
        return 10.0
    return None


def _suggestion_prompt_texts(assistant, actions: list[str], lang: str) -> tuple[str, str]:
    labels_pl = [assistant._action_label(action, "pl") for action in actions]
    labels_en = [assistant._action_label(action, "en") for action in actions]

    if not actions:
        return (
            "Powiedz proszę, co wybrać.",
            "Please tell me what to choose.",
        )

    if len(actions) == 1:
        return (
            f"Powiedz tak, jeśli chcesz {labels_pl[0]}, albo nie, jeśli chcesz anulować.",
            f"Say yes if you want {labels_en[0]}, or no if you want to cancel.",
        )

    joined_pl = ", ".join(labels_pl[:-1]) + " albo " + labels_pl[-1]
    joined_en = ", ".join(labels_en[:-1]) + " or " + labels_en[-1]

    return (
        f"Powiedz, co wybierasz: {joined_pl}.",
        f"Tell me what you choose: {joined_en}.",
    )


def _mixed_repeat_prompt_texts(assistant, actions: list[str]) -> tuple[str, str]:
    labels_pl = [assistant._action_label(action, "pl") for action in actions]
    labels_en = [assistant._action_label(action, "en") for action in actions]

    if not actions:
        return (
            "Na razie nie mam żadnej gotowej opcji.",
            "I do not have a ready option right now.",
        )

    if len(actions) == 1:
        return (
            f"Mogę teraz {labels_pl[0]}.",
            f"I can {labels_en[0]} right now.",
        )

    if len(actions) == 2:
        return (
            f"Mogę teraz {labels_pl[0]} albo {labels_pl[1]}.",
            f"I can {labels_en[0]} or {labels_en[1]} right now.",
        )

    joined_pl = ", ".join(labels_pl[:-1]) + " albo " + labels_pl[-1]
    joined_en = ", ".join(labels_en[:-1]) + " or " + labels_en[-1]

    return (
        f"Mogę teraz {joined_pl}.",
        f"I can {joined_en} right now.",
    )


def _is_repeat_request(assistant, text: str, lang: str) -> bool:
    normalized = assistant._normalize_text(text)
    if normalized in _MIXED_REPEAT_MARKERS.get(lang, set()):
        return True

    if lang == "en":
        return any(
            phrase in normalized
            for phrase in [
                "repeat",
                "options",
                "what are the options",
                "what can i choose",
                "say that again",
                "what did you say",
            ]
        )

    return any(
        phrase in normalized
        for phrase in [
            "powtorz",
            "powtórz",
            "opcje",
            "jakie mam opcje",
            "co moge wybrac",
            "co mogę wybrać",
            "co powiedzialas",
            "co powiedziałaś",
        ]
    )


def _execute_suggested_action(
    assistant,
    action: str,
    lang: str,
    *,
    duration_minutes: float | None = None,
) -> bool:
    assistant.pending_follow_up = None

    if action in _TIMER_LIKE_ACTIONS:
        minutes = duration_minutes if duration_minutes is not None and duration_minutes > 0 else _default_minutes_for_action(assistant, action)

        mode = "timer"
        if action == "focus_start":
            mode = "focus"
        elif action == "break_start":
            mode = "break"

        return assistant._start_timer_mode(float(minutes), mode, lang)

    if action == "reminder_create":
        _speak_and_remember_localized(
            assistant,
            lang,
            "Jasne. Powiedz teraz pełne przypomnienie, na przykład: przypomnij mi za 10 minut, żeby napić się wody.",
            "Sure. Now say the full reminder, for example: remind me in 10 minutes to drink water.",
            follow_type="mixed_action_offer",
            extra_metadata={"selected_action": action, "phase": "request_full_reminder"},
        )
        return True

    return assistant._execute_intent(
        IntentResult(
            action=action,
            data={},
            normalized_text=action,
        ),
        lang,
    )


def _resolve_suggested_action_choice(
    assistant,
    text: str,
    suggested_actions: list[str],
) -> str | None:
    if not suggested_actions:
        return None

    ordinal_choice = _parse_confirmation_choice(text)
    if ordinal_choice is not None and ordinal_choice < len(suggested_actions):
        return suggested_actions[ordinal_choice]

    direct_choice = assistant.parser.find_action_in_text(text, allowed_actions=suggested_actions)
    if direct_choice:
        return direct_choice

    normalized = assistant._normalize_text(text)

    action_keyword_map = {
        "focus_start": {
            "focus",
            "focus mode",
            "focus session",
            "short focus",
            "skupienie",
            "tryb skupienia",
        },
        "break_start": {
            "break",
            "break mode",
            "short break",
            "take a break",
            "przerwa",
            "krotka przerwa",
            "krótka przerwa",
            "tryb przerwy",
        },
        "timer_start": {
            "timer",
            "short timer",
            "stoper",
            "odliczanie",
        },
        "reminder_create": {
            "reminder",
            "set a reminder",
            "przypomnienie",
        },
    }

    for action in suggested_actions:
        if normalized in action_keyword_map.get(action, set()):
            return action

    return None


def ask_for_confirmation(assistant, suggestions: list[dict[str, Any]], lang: str) -> bool:
    assistant.pending_confirmation = {
        "suggestions": suggestions,
        "language": lang,
    }

    first = assistant._action_label(suggestions[0]["action"], lang)
    second = assistant._action_label(suggestions[1]["action"], lang) if len(suggestions) > 1 else None

    if lang == "pl":
        lines = [f"1: {first}"]
        voice_text = f"Czy chodziło ci o {first}"
        if second:
            lines.append(f"2: {second}")
            voice_text += f" czy o {second}"
        lines.append("powiedz tak lub nie")
        voice_text += "? Powiedz tak albo nie."
        title = "POTWIERDŹ"
    else:
        lines = [f"1: {first}"]
        voice_text = f"Did you mean {first}"
        if second:
            lines.append(f"2: {second}")
            voice_text += f" or {second}"
        lines.append("say yes or no")
        voice_text += "? Say yes or no."
        title = "CONFIRM"

    assistant.display.show_block(title, lines, duration=assistant.default_overlay_seconds)
    assistant.voice_out.speak(voice_text, language=lang)
    _remember_followup_reply(
        assistant,
        spoken=voice_text,
        lang=lang,
        follow_type="confirmation_prompt",
        extra_metadata={"suggestions": [item["action"] for item in suggestions]},
    )
    return True


def handle_pending_confirmation(assistant, text: str, current_lang: str) -> bool:
    lang = assistant.pending_confirmation.get("language", current_lang) if assistant.pending_confirmation else current_lang
    suggestions = assistant.pending_confirmation.get("suggestions", []) if assistant.pending_confirmation else []
    allowed_actions = [item["action"] for item in suggestions]

    if assistant._is_yes(text):
        chosen = suggestions[0]["action"] if suggestions else None
        assistant.pending_confirmation = None
        if chosen:
            return assistant._execute_intent(IntentResult(action=chosen, data={}, normalized_text=text), lang)
        return True

    if assistant._is_no(text):
        assistant.pending_confirmation = None
        _speak_and_remember_localized(
            assistant,
            lang,
            "Dobrze. Powiedz to jeszcze raz inaczej.",
            "Okay. Please say it again in a different way.",
            follow_type="confirmation_prompt",
            extra_metadata={"phase": "declined"},
        )
        return True

    ordinal_choice = _parse_confirmation_choice(text)
    if ordinal_choice is not None and ordinal_choice < len(suggestions):
        chosen = suggestions[ordinal_choice]["action"]
        assistant.pending_confirmation = None
        return assistant._execute_intent(IntentResult(action=chosen, data={}, normalized_text=text), lang)

    direct_choice = assistant.parser.find_action_in_text(text, allowed_actions=allowed_actions)
    if direct_choice:
        assistant.pending_confirmation = None
        return assistant._execute_intent(IntentResult(action=direct_choice, data={}, normalized_text=text), lang)

    interrupted = _try_interrupt_with_new_command(assistant, text, lang)
    if interrupted is not None:
        return interrupted

    _yes_no_retry(assistant, lang)
    return True


def handle_pending_follow_up(assistant, text: str, lang: str) -> bool | None:
    follow_up = assistant.pending_follow_up or {}
    follow_type = follow_up.get("type")
    follow_lang = _follow_up_language(assistant, lang)

    if follow_type == "display_offer":
        return _handle_display_offer_follow_up(assistant, follow_up, text, follow_lang)

    if follow_type == "mixed_action_offer":
        suggested_actions = [str(item).strip() for item in follow_up.get("suggested_actions", []) if str(item).strip()]
        default_action = str(follow_up.get("default_action", "")).strip() or None
        if default_action not in suggested_actions:
            default_action = None

        direct_minutes = assistant._extract_minutes_from_text(text)

        if _is_repeat_request(assistant, text, follow_lang):
            prompt_pl, prompt_en = _mixed_repeat_prompt_texts(assistant, suggested_actions)
            question_pl, question_en = _suggestion_prompt_texts(assistant, suggested_actions, follow_lang)

            assistant._speak_localized(
                follow_lang,
                f"{prompt_pl} {question_pl}",
                f"{prompt_en} {question_en}",
            )
            _remember_followup_reply(
                assistant,
                spoken=assistant._localized(follow_lang, f"{prompt_pl} {question_pl}", f"{prompt_en} {question_en}"),
                lang=follow_lang,
                follow_type="mixed_action_offer",
                extra_metadata={"phase": "repeat_options", "suggested_actions": suggested_actions},
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Zostajemy przy rozmowie.",
                "Okay. We can stay with the conversation.",
                follow_type="mixed_action_offer",
                extra_metadata={"phase": "declined", "suggested_actions": suggested_actions},
            )
            return True

        chosen_action = _resolve_suggested_action_choice(assistant, text, suggested_actions)
        if chosen_action:
            return _execute_suggested_action(
                assistant,
                chosen_action,
                follow_lang,
                duration_minutes=direct_minutes,
            )

        if assistant._is_yes(text):
            if default_action is not None:
                return _execute_suggested_action(
                    assistant,
                    default_action,
                    follow_lang,
                    duration_minutes=direct_minutes,
                )

            if len(suggested_actions) == 1:
                return _execute_suggested_action(
                    assistant,
                    suggested_actions[0],
                    follow_lang,
                    duration_minutes=direct_minutes,
                )

        if direct_minutes is not None and direct_minutes > 0:
            timer_like_suggestions = [action for action in suggested_actions if action in _TIMER_LIKE_ACTIONS]
            chosen_timer_action = None

            if default_action in _TIMER_LIKE_ACTIONS:
                chosen_timer_action = default_action
            elif len(timer_like_suggestions) == 1:
                chosen_timer_action = timer_like_suggestions[0]

            if chosen_timer_action is not None:
                return _execute_suggested_action(
                    assistant,
                    chosen_timer_action,
                    follow_lang,
                    duration_minutes=direct_minutes,
                )

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        prompt_pl, prompt_en = _suggestion_prompt_texts(assistant, suggested_actions, follow_lang)
        _speak_and_remember_localized(
            assistant,
            follow_lang,
            prompt_pl,
            prompt_en,
            follow_type="mixed_action_offer",
            extra_metadata={"phase": "reprompt", "suggested_actions": suggested_actions},
        )
        return True

    if follow_type == "capture_name":
        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        name = extract_name(text)
        if not name:
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Nie usłyszałam wyraźnie imienia. Powiedz proszę jeszcze raz swoje imię.",
                "I did not catch your name clearly. Please say your name again.",
                follow_type="capture_name",
                extra_metadata={"phase": "retry_capture_name"},
            )
            return True

        assistant.pending_follow_up = {
            "type": "confirm_save_name",
            "lang": follow_lang,
            "name": name,
        }

        assistant.display.show_block(
            assistant._localized(follow_lang, "ZAPISAĆ IMIĘ?", "SAVE NAME?"),
            [
                name,
                assistant._localized(follow_lang, "powiedz tak lub nie", "say yes or no"),
            ],
            duration=8.0,
        )
        assistant._speak_localized(
            follow_lang,
            f"Miło mi, {name}. Czy chcesz, żebym zapamiętała twoje imię?",
            f"Nice to meet you, {name}. Would you like me to remember your name?",
        )
        _remember_followup_reply(
            assistant,
            spoken=assistant._localized(
                follow_lang,
                f"Miło mi, {name}. Czy chcesz, żebym zapamiętała twoje imię?",
                f"Nice to meet you, {name}. Would you like me to remember your name?",
            ),
            lang=follow_lang,
            follow_type="confirm_save_name",
            extra_metadata={"phase": "offer_save_name", "name": name},
        )
        return True

    if follow_type == "confirm_save_name":
        name = str(follow_up.get("name", "")).strip()

        if assistant._is_yes(text):
            assistant.user_profile["conversation_partner_name"] = name
            assistant._save_user_profile()
            assistant.pending_follow_up = None
            assistant._show_localized_block(
                follow_lang,
                "IMIĘ ZAPISANE",
                "NAME SAVED",
                [name, "zapamiętałam imię"],
                [name, "I remembered your name"],
                duration=8.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                f"Dobrze. Zapamiętałam twoje imię, {name}.",
                f"Okay. I will remember your name, {name}.",
                follow_type="confirm_save_name",
                extra_metadata={"phase": "saved_name", "name": name},
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie zapisuję twojego imienia.",
                "Okay. I will not save your name.",
                follow_type="confirm_save_name",
                extra_metadata={"phase": "declined_save_name", "name": name},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_memory_forget":
        key = str(follow_up.get("key", "")).strip()

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            deleted_key, _ = assistant.memory.forget(key)

            if deleted_key is None:
                _speak_and_remember_localized(
                    assistant,
                    follow_lang,
                    "Nie mogę już znaleźć tej informacji w pamięci.",
                    "I cannot find that information in memory anymore.",
                    follow_type="confirm_memory_forget",
                    extra_metadata={"phase": "not_found", "key": key},
                )
                return True

            assistant.display.show_block(
                assistant._localized(follow_lang, "USUNIĘTO", "DELETED"),
                [_short_line(deleted_key)],
                duration=6.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                f"Dobrze. Usunęłam z pamięci {deleted_key}.",
                f"Okay. I removed {deleted_key} from memory.",
                follow_type="confirm_memory_forget",
                extra_metadata={"phase": "deleted", "key": deleted_key},
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie usuwam tej informacji z pamięci.",
                "Okay. I will not remove that information from memory.",
                follow_type="confirm_memory_forget",
                extra_metadata={"phase": "declined", "key": key},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_memory_clear":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            removed = assistant.memory.clear()
            assistant.display.show_block(
                assistant._localized(follow_lang, "PAMIĘĆ WYCZYSZCZONA", "MEMORY CLEARED"),
                [assistant._localized(follow_lang, f"usunięto: {removed}", f"removed: {removed}")],
                duration=6.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                f"Dobrze. Wyczyściłam pamięć. Usunięto {removed} wpisów.",
                f"Okay. I cleared memory. Removed {removed} items.",
                follow_type="confirm_memory_clear",
                extra_metadata={"phase": "cleared", "removed": removed},
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie czyszczę pamięci.",
                "Okay. I will not clear memory.",
                follow_type="confirm_memory_clear",
                extra_metadata={"phase": "declined"},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_reminder_delete":
        reminder_id = str(follow_up.get("reminder_id", "")).strip()
        reminder_message = str(follow_up.get("message", "")).strip()

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            deleted = assistant.reminders.delete(reminder_id)

            if not deleted:
                _speak_and_remember_localized(
                    assistant,
                    follow_lang,
                    "Nie mogę już znaleźć tego przypomnienia.",
                    "I cannot find that reminder anymore.",
                    follow_type="confirm_reminder_delete",
                    extra_metadata={"phase": "not_found", "reminder_id": reminder_id},
                )
                return True

            assistant.display.show_block(
                assistant._localized(follow_lang, "USUNIĘTO", "DELETED"),
                [_short_line(reminder_message or reminder_id)],
                duration=6.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                f"Dobrze. Usunęłam przypomnienie {_short_line(reminder_message or reminder_id, limit=40)}.",
                f"Okay. I deleted the reminder {_short_line(reminder_message or reminder_id, limit=40)}.",
                follow_type="confirm_reminder_delete",
                extra_metadata={
                    "phase": "deleted",
                    "reminder_id": reminder_id,
                    "message": reminder_message,
                },
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie usuwam przypomnienia.",
                "Okay. I will not delete the reminder.",
                follow_type="confirm_reminder_delete",
                extra_metadata={"phase": "declined", "reminder_id": reminder_id},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_reminders_clear":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            removed = assistant._delete_all_reminders()
            assistant.display.show_block(
                assistant._localized(follow_lang, "PRZYPOMNIENIA WYCZYSZCZONE", "REMINDERS CLEARED"),
                [assistant._localized(follow_lang, f"usunięto: {removed}", f"removed: {removed}")],
                duration=6.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                f"Dobrze. Usunęłam wszystkie przypomnienia. Usunięto {removed}.",
                f"Okay. I deleted all reminders. Removed {removed}.",
                follow_type="confirm_reminders_clear",
                extra_metadata={"phase": "cleared", "removed": removed},
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie usuwam przypomnień.",
                "Okay. I will not delete reminders.",
                follow_type="confirm_reminders_clear",
                extra_metadata={"phase": "declined"},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_exit":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant._show_localized_block(
                follow_lang,
                "DO WIDZENIA",
                "GOODBYE",
                ["zamykam asystenta"],
                ["closing assistant"],
                duration=4.0,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Zamykam asystenta.",
                "Okay. Closing the assistant.",
                follow_type="confirm_exit",
                extra_metadata={"phase": "confirmed_exit"},
            )
            return False

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Zostaję włączona.",
                "Okay. I will stay on.",
                follow_type="confirm_exit",
                extra_metadata={"phase": "declined_exit"},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type == "confirm_shutdown":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant.shutdown_requested = True
            assistant._show_localized_block(
                follow_lang,
                "WYŁĄCZANIE",
                "SHUTTING DOWN",
                ["zamykam asystenta", "i system"],
                ["closing assistant", "and system"],
                duration=_SHUTDOWN_DELAY_SECONDS,
            )
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Zamykam asystenta i wyłączam system.",
                "Okay. I am closing the assistant and shutting down the system.",
                follow_type="confirm_shutdown",
                extra_metadata={"phase": "confirmed_shutdown"},
            )
            return False

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie wyłączam systemu.",
                "Okay. I will not shut down the system.",
                follow_type="confirm_shutdown",
                extra_metadata={"phase": "declined_shutdown"},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, follow_lang)
        return True

    if follow_type in {"timer_duration", "focus_duration", "break_duration"}:
        minutes = assistant._extract_minutes_from_text(text)

        if minutes is None or minutes <= 0:
            interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
            if interrupted is not None:
                return interrupted

            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Podaj proszę czas w minutach albo sekundach.",
                "Please tell me the duration in minutes or seconds.",
                follow_type=follow_type,
                extra_metadata={"phase": "retry_duration"},
            )
            return True

        assistant.pending_follow_up = None

        if follow_type == "timer_duration":
            return assistant._start_timer_mode(minutes, "timer", follow_lang)
        if follow_type == "focus_duration":
            return assistant._start_timer_mode(minutes, "focus", follow_lang)
        return assistant._start_timer_mode(minutes, "break", follow_lang)

    if follow_type == "post_focus_break_offer":
        direct_minutes = assistant._extract_minutes_from_text(text)
        if direct_minutes is not None and direct_minutes > 0 and not assistant._is_no(text):
            assistant.pending_follow_up = None
            return assistant._start_timer_mode(direct_minutes, "break", follow_lang)

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            default_break = float(getattr(assistant.parser, "default_break_minutes", 5))
            return assistant._start_timer_mode(default_break, "break", follow_lang)

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            _speak_and_remember_localized(
                assistant,
                follow_lang,
                "Dobrze. Nie uruchamiam przerwy.",
                "Okay. I will not start a break.",
                follow_type="post_focus_break_offer",
                extra_metadata={"phase": "declined_break_offer"},
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, follow_lang)
        if interrupted is not None:
            return interrupted

        _speak_and_remember_localized(
            assistant,
            follow_lang,
            "Powiedz tak, nie albo od razu podaj długość przerwy.",
            "Say yes, no, or tell me the break duration right away.",
            follow_type="post_focus_break_offer",
            extra_metadata={"phase": "reprompt_break_offer"},
        )
        return True

    assistant.pending_follow_up = None
    return None