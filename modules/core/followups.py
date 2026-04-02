from __future__ import annotations

import re
from typing import Any

from modules.parsing.intent_parser import IntentResult


def extract_name(text: str) -> str | None:
    raw = text.strip()

    patterns = [
        r"\b(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem)\s+([A-Za-zÀ-ÿ' -]{2,})$",
        r"\b(?:my name is|i am|i'm)\s+([A-Za-zÀ-ÿ' -]{2,})$",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            name = match.group(1).strip().split()[0]
            return name[:1].upper() + name[1:].lower()

    simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
    if 1 <= len(simple_tokens) <= 2:
        token = simple_tokens[0]
        blocked = {
            "help",
            "pomoc",
            "status",
            "stan",
            "tak",
            "nie",
            "yes",
            "no",
            "focus",
            "break",
            "time",
            "godzina",
        }
        if token.lower() not in blocked and len(token) >= 2:
            return token[:1].upper() + token[1:].lower()

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
    result = assistant.parser.parse(text)
    suggestions = assistant.pending_confirmation.get("suggestions", []) if assistant.pending_confirmation else []
    allowed_actions = [item["action"] for item in suggestions]

    if result.action == "confirm_yes":
        chosen = suggestions[0]["action"] if suggestions else None
        assistant.pending_confirmation = None
        if chosen:
            return assistant._execute_intent(IntentResult(action=chosen, data={}, normalized_text=text), lang)
        return True

    if result.action == "confirm_no":
        assistant.pending_confirmation = None
        assistant._speak_localized(
            lang,
            "Dobrze. Powiedz to jeszcze raz inaczej.",
            "Okay. Please say it again in a different way.",
        )
        return True

    direct_choice = assistant.parser.find_action_in_text(text, allowed_actions=allowed_actions)
    if direct_choice:
        assistant.pending_confirmation = None
        return assistant._execute_intent(IntentResult(action=direct_choice, data={}, normalized_text=text), lang)

    assistant._speak_localized(
        lang,
        "Powiedz tak albo nie.",
        "Please say yes or no.",
    )
    return True


def handle_pending_follow_up(assistant, text: str, lang: str) -> bool | None:
    follow_up = assistant.pending_follow_up or {}
    follow_type = follow_up.get("type")

    if follow_type == "capture_name":
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
        return True

    if follow_type == "confirm_exit":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
        return True

    if follow_type == "confirm_shutdown":
        if assistant._is_yes(text):
            assistant.pending_follow_up = None
            assistant.shutdown_requested = True
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
        return True

    if follow_type in {"timer_duration", "focus_duration", "break_duration"}:
        minutes = assistant._extract_minutes_from_text(text)
        if minutes is None or minutes <= 0:
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

        assistant._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
        return True

    if follow_type == "post_focus_break_offer":
        direct_minutes = assistant._extract_minutes_from_text(text)
        if direct_minutes is not None and direct_minutes > 0 and not assistant._is_no(text):
            assistant.pending_follow_up = None
            return assistant._start_timer_mode(direct_minutes, "break", lang)

        if assistant._is_yes(text):
            assistant.pending_follow_up = {
                "type": "break_duration",
                "lang": lang,
            }
            assistant._speak_localized(
                lang,
                "Jak długa ma być przerwa?",
                "How long should the break be?",
            )
            return True

        if assistant._is_no(text):
            assistant.pending_follow_up = None
            assistant._speak_localized(
                lang,
                "Dobrze. Nie uruchamiam przerwy.",
                "Okay. I will not start a break.",
            )
            return True

        assistant._speak_localized(
            lang,
            "Powiedz tak, nie albo od razu podaj długość przerwy.",
            "Say yes, no, or tell me the break duration right away.",
        )
        return True

    assistant.pending_follow_up = None
    return None