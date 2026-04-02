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

        name = match.group(1).strip().split()[0]
        if _looks_like_name_candidate(name):
            return _normalize_name_token(name)

    simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
    if len(simple_tokens) == 1:
        token = simple_tokens[0]
        if _looks_like_name_candidate(token):
            return _normalize_name_token(token)

    return None


def _yes_no_retry(assistant, lang: str) -> None:
    assistant._speak_localized(
        lang,
        "Powiedz tak albo nie.",
        "Please say yes or no.",
    )


def _try_interrupt_with_new_command(assistant, text: str, lang: str) -> bool | None:
    result = assistant.parser.parse(text)
    if result.action not in _INTERRUPTABLE_ACTIONS:
        return None

    assistant.pending_confirmation = None
    assistant.pending_follow_up = None
    return assistant._execute_intent(
        IntentResult(action=result.action, data=result.data, normalized_text=result.normalized_text),
        lang,
    )


def _parse_confirmation_choice(text: str) -> int | None:
    lowered = text.lower().strip()

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

    normalized = re.sub(r"\s+", " ", lowered)

    if normalized in first_markers:
        return 0
    if normalized in second_markers:
        return 1

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
        assistant._speak_localized(
            lang,
            "Dobrze. Powiedz to jeszcze raz inaczej.",
            "Okay. Please say it again in a different way.",
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

    if follow_type == "capture_name":
        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        name = extract_name(text)
        if not name:
            assistant._speak_localized(
                lang,
                "Nie usłyszałam wyraźnie imienia. Powiedz proszę jeszcze raz swoje imię.",
                "I did not catch your name clearly. Please say your name again.",
            )
            return True

        assistant.pending_follow_up = {
            "type": "confirm_save_name",
            "lang": lang,
            "name": name,
        }
        assistant._speak_localized(
            lang,
            f"Miło mi, {name}. Czy chcesz, żebym zapamiętała twoje imię?",
            f"Nice to meet you, {name}. Would you like me to remember your name?",
        )
        return True

    if follow_type == "confirm_save_name":
        name = follow_up.get("name", "")

        if assistant._is_yes(text):
            assistant.user_profile["conversation_partner_name"] = name
            assistant._save_user_profile()
            assistant.pending_follow_up = None
            assistant._show_localized_block(
                lang,
                "IMIĘ ZAPISANE",
                "NAME SAVED",
                [name, "zapamiętałam imię"],
                [name, "I remembered your name"],
                duration=8.0,
            )
            assistant._speak_localized(
                lang,
                f"Dobrze. Zapamiętałam twoje imię, {name}.",
                f"Okay. I will remember your name, {name}.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie zapisuję twojego imienia.",
                "Okay. I will not save your name.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_memory_forget":
        key = follow_up.get("key", "")

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            deleted_key, _ = assistant.memory.forget(key)

            if deleted_key is None:
                assistant._speak_localized(
                    lang,
                    "Nie mogę już znaleźć tej informacji w pamięci.",
                    "I cannot find that information in memory anymore.",
                )
                return True

            assistant.display.show_block(
                assistant._localized(lang, "USUNIĘTO", "DELETED"),
                [deleted_key],
                duration=6.0,
            )
            assistant._speak_localized(
                lang,
                f"Dobrze. Usunęłam z pamięci {deleted_key}.",
                f"Okay. I removed {deleted_key} from memory.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie usuwam tej informacji z pamięci.",
                "Okay. I will not remove that information from memory.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_memory_clear":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            removed = assistant.memory.clear()
            assistant.display.show_block(
                assistant._localized(lang, "PAMIĘĆ WYCZYSZCZONA", "MEMORY CLEARED"),
                [assistant._localized(lang, f"usunięto: {removed}", f"removed: {removed}")],
                duration=6.0,
            )
            assistant._speak_localized(
                lang,
                f"Dobrze. Wyczyściłam pamięć. Usunięto {removed} wpisów.",
                f"Okay. I cleared memory. Removed {removed} items.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie czyszczę pamięci.",
                "Okay. I will not clear memory.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_reminder_delete":
        reminder_id = follow_up.get("reminder_id", "")
        reminder_message = follow_up.get("message", "")

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            deleted = assistant.reminders.delete(reminder_id)
            if not deleted:
                assistant._speak_localized(
                    lang,
                    "Nie mogę już znaleźć tego przypomnienia.",
                    "I cannot find that reminder anymore.",
                )
                return True

            assistant.display.show_block(
                assistant._localized(lang, "USUNIĘTO", "DELETED"),
                [reminder_message or reminder_id],
                duration=6.0,
            )
            assistant._speak_localized(
                lang,
                f"Dobrze. Usunęłam przypomnienie {reminder_message}.",
                f"Okay. I deleted the reminder {reminder_message}.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie usuwam przypomnienia.",
                "Okay. I will not delete the reminder.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_reminders_clear":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            removed = assistant._delete_all_reminders()
            assistant.display.show_block(
                assistant._localized(lang, "PRZYPOMNIENIA WYCZYSZCZONE", "REMINDERS CLEARED"),
                [assistant._localized(lang, f"usunięto: {removed}", f"removed: {removed}")],
                duration=6.0,
            )
            assistant._speak_localized(
                lang,
                f"Dobrze. Usunęłam wszystkie przypomnienia. Usunięto {removed}.",
                f"Okay. I deleted all reminders. Removed {removed}.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie usuwam przypomnień.",
                "Okay. I will not delete reminders.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_exit":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant._show_localized_block(
                lang,
                "DO WIDZENIA",
                "GOODBYE",
                ["zamykam asystenta"],
                ["closing assistant"],
                duration=4.0,
            )
            assistant._speak_localized(
                lang,
                "Dobrze. Zamykam asystenta.",
                "Okay. Closing the assistant.",
            )
            return False

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Zostaję włączona.",
                "Okay. I will stay on.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "confirm_shutdown":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant.shutdown_requested = True
            assistant._show_localized_block(
                lang,
                "WYŁĄCZANIE",
                "SHUTTING DOWN",
                ["zamykam system"],
                ["shutting down system"],
                duration=4.0,
            )
            assistant._speak_localized(
                lang,
                "Dobrze. Wyłączam system.",
                "Okay. Shutting down the system.",
            )
            return False

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie wyłączam systemu.",
                "Okay. I will not shut down the system.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type in {"timer_duration", "focus_duration", "break_duration"}:
        minutes = assistant._extract_minutes_from_text(text)

        if minutes is None or minutes <= 0:
            interrupted = _try_interrupt_with_new_command(assistant, text, lang)
            if interrupted is not None:
                return interrupted

            assistant._speak_localized(
                lang,
                "Podaj proszę czas w minutach albo sekundach.",
                "Please tell me the duration in minutes or seconds.",
            )
            return True

        assistant.pending_follow_up = None

        if follow_type == "timer_duration":
            return assistant._start_timer_mode(minutes, "timer", lang)
        if follow_type == "focus_duration":
            return assistant._start_timer_mode(minutes, "focus", lang)
        return assistant._start_timer_mode(minutes, "break", lang)

    if follow_type == "display_offer":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant.display.show_block(
                follow_up.get("title", "INFO"),
                follow_up.get("lines", []),
                duration=assistant.default_overlay_seconds,
            )
            assistant._speak_localized(
                lang,
                "Dobrze. Pokazuję to na ekranie.",
                "Okay. I am showing it on the screen.",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze.",
                "Okay.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        _yes_no_retry(assistant, lang)
        return True

    if follow_type == "post_focus_break_offer":
        direct_minutes = assistant._extract_minutes_from_text(text)
        if direct_minutes is not None and direct_minutes > 0 and not assistant._is_no(text):
            assistant.pending_follow_up = None
            return assistant._start_timer_mode(direct_minutes, "break", lang)

        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            default_break = float(getattr(assistant.parser, "default_break_minutes", 5))
            return assistant._start_timer_mode(default_break, "break", lang)

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie uruchamiam przerwy.",
                "Okay. I will not start a break.",
            )
            return True

        interrupted = _try_interrupt_with_new_command(assistant, text, lang)
        if interrupted is not None:
            return interrupted

        assistant._speak_localized(
            lang,
            "Powiedz tak, nie albo od razu podaj długość przerwy.",
            "Say yes, no, or tell me the break duration right away.",
        )
        return True

    assistant.pending_follow_up = None
    return None