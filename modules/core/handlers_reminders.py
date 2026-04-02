from __future__ import annotations

from datetime import datetime

from modules.system.utils import append_log


def _short_message(text: str, limit: int = 26) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _status_label(status: str, lang: str) -> str:
    if lang == "pl":
        return "oczekuje" if status == "pending" else "gotowe"
    return "pending" if status == "pending" else "done"


def _format_due_text(reminder: dict, lang: str) -> str:
    due_at_raw = str(reminder.get("due_at", "")).strip()
    if not due_at_raw:
        return ""

    try:
        due_at = datetime.fromisoformat(due_at_raw)
    except ValueError:
        return ""

    now = datetime.now()
    time_part = due_at.strftime("%H:%M")

    if due_at.date() == now.date():
        return f"dzis {time_part}" if lang == "pl" else f"today {time_part}"

    if due_at.date() == now.date().fromordinal(now.date().toordinal() + 1):
        return f"jutro {time_part}" if lang == "pl" else f"tomorrow {time_part}"

    date_part = due_at.strftime("%d-%m")
    return f"{date_part} {time_part}"


def _summary_line(reminder: dict, lang: str) -> str:
    status = _status_label(str(reminder.get("status", "pending")), lang)
    reminder_id = str(reminder.get("id", "")).strip()
    due_text = _format_due_text(reminder, lang)

    if due_text:
        return f"{reminder_id} {status} {due_text}"
    return f"{reminder_id} {status}"


def handle_reminders_list(assistant, lang: str) -> bool:
    reminders = assistant.reminders.list_all()
    if not reminders:
        assistant._show_localized_block(
            lang,
            "PRZYPOMNIENIA",
            "REMINDERS",
            ["brak zapisanych", "przypomnien"],
            ["no saved", "reminders"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Nie ma zapisanych przypomnień.",
            "There are no saved reminders.",
        )
        return True

    pending_count = len([item for item in reminders if item.get("status") == "pending"])
    total_count = len(reminders)
    first_items = reminders[:2]

    lines: list[str] = [
        assistant._localized(
            lang,
            f"razem: {total_count} oczekuje: {pending_count}",
            f"total: {total_count} pending: {pending_count}",
        )
    ]

    for reminder in first_items:
        lines.append(_summary_line(reminder, lang))
        lines.append(_short_message(str(reminder.get("message", "")), limit=24))

    assistant.display.show_block(
        assistant._localized(lang, "PRZYPOMNIENIA", "REMINDERS"),
        lines[:4],
        duration=assistant.default_overlay_seconds,
    )

    assistant._speak_localized(
        lang,
        f"Mam zapisane {total_count} przypomnienia. {pending_count} nadal oczekują.",
        f"I have {total_count} saved reminders. {pending_count} are still pending.",
    )
    return True


def handle_reminder_delete(assistant, result, lang: str) -> bool:
    reminder = None

    if "id" in result.data:
        reminder_id = result.data["id"].strip()
        reminder = assistant.reminders.find_by_id(reminder_id)
    elif "message" in result.data:
        reminder_message = result.data["message"].strip()
        reminder = assistant.reminders.find_by_message(reminder_message)

    if reminder is None:
        assistant._show_localized_block(
            lang,
            "PRZYPOMNIENIA",
            "REMINDERS",
            ["nie znaleziono", "przypomnienia"],
            ["reminder not", "found"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Nie mogę znaleźć takiego przypomnienia.",
            "I cannot find that reminder.",
        )
        return True

    reminder_id = str(reminder.get("id", "")).strip()
    reminder_message = str(reminder.get("message", "")).strip()
    due_text = _format_due_text(reminder, lang)

    assistant.pending_follow_up = {
        "type": "confirm_reminder_delete",
        "lang": lang,
        "reminder_id": reminder_id,
        "message": reminder_message,
    }

    lines = [_short_message(reminder_message, limit=24), reminder_id]
    if due_text:
        lines.append(due_text)

    assistant.display.show_block(
        assistant._localized(lang, "USUNĄĆ PRZYPOMNIENIE?", "DELETE REMINDER?"),
        lines[:3],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        f"Czy na pewno mam usunąć przypomnienie {_short_message(reminder_message, limit=40)}?",
        f"Are you sure I should delete the reminder {_short_message(reminder_message, limit=40)}?",
    )
    return True


def handle_reminders_clear(assistant, lang: str) -> bool:
    reminders = assistant.reminders.list_all()
    if not reminders:
        assistant._show_localized_block(
            lang,
            "PRZYPOMNIENIA",
            "REMINDERS",
            ["brak przypomnien", "do usuniecia"],
            ["no reminders", "to delete"],
            duration=6.0,
        )
        assistant._speak_localized(
            lang,
            "Nie ma przypomnień do usunięcia.",
            "There are no reminders to delete.",
        )
        return True

    pending_count = len([item for item in reminders if item.get("status") == "pending"])

    assistant.pending_follow_up = {
        "type": "confirm_reminders_clear",
        "lang": lang,
    }

    assistant.display.show_block(
        assistant._localized(lang, "USUNĄĆ WSZYSTKIE?", "DELETE ALL?"),
        [
            assistant._localized(lang, f"razem: {len(reminders)}", f"total: {len(reminders)}"),
            assistant._localized(lang, f"oczekuje: {pending_count}", f"pending: {pending_count}"),
        ],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        "Czy na pewno mam usunąć wszystkie przypomnienia?",
        "Are you sure I should delete all reminders?",
    )
    return True


def handle_reminder_create(assistant, result, lang: str) -> bool:
    seconds = int(result.data["seconds"])
    message = result.data["message"].strip()
    reminder = assistant.reminders.add_after_seconds(seconds, message)

    spoken_duration = assistant._format_duration_text(seconds, lang)
    reminder_id = str(reminder.get("id", "")).strip()

    assistant.display.show_block(
        assistant._localized(lang, "PRZYPOMNIENIE ZAPISANE", "REMINDER SAVED"),
        [
            _short_message(message, limit=24),
            assistant._localized(lang, f"za {spoken_duration}", f"in {spoken_duration}"),
            reminder_id,
        ],
        duration=8.0,
    )

    assistant._speak_localized(
        lang,
        f"Dobrze. Ustawiłam przypomnienie za {spoken_duration}.",
        f"Okay. I set a reminder for {spoken_duration}.",
    )

    append_log(f"Reminder created: {reminder_id} -> {message}")
    return True