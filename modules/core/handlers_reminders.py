from __future__ import annotations

from modules.system.utils import append_log


def handle_reminders_list(assistant, lang: str) -> bool:
    reminders = assistant.reminders.list_all()
    if not reminders:
        assistant._speak_localized(
            lang,
            "Nie ma zapisanych przypomnień.",
            "There are no saved reminders.",
        )
        return True

    reminder_lines = [f"{item['id']} {item['status']}" for item in reminders[:5]]
    assistant.display.show_block(
        assistant._localized(lang, "PRZYPOMNIENIA", "REMINDERS"),
        reminder_lines,
        duration=assistant.default_overlay_seconds,
    )
    assistant._speak_localized(
        lang,
        "Pokazuję zapisane przypomnienia.",
        "I am showing the saved reminders.",
    )
    return True


def handle_reminder_delete(assistant, result, lang: str) -> bool:
    reminder = None
    reminder_id = None
    reminder_message = None

    if "id" in result.data:
        reminder_id = result.data["id"].strip()
        reminder = assistant.reminders.find_by_id(reminder_id)
    elif "message" in result.data:
        reminder_message = result.data["message"].strip()
        reminder = assistant.reminders.find_by_message(reminder_message)

    if reminder is None:
        assistant._speak_localized(
            lang,
            "Nie mogę znaleźć takiego przypomnienia.",
            "I cannot find that reminder.",
        )
        return True

    reminder_id = reminder.get("id", "")
    reminder_message = reminder.get("message", "")

    assistant.pending_follow_up = {
        "type": "confirm_reminder_delete",
        "lang": lang,
        "reminder_id": reminder_id,
        "message": reminder_message,
    }

    assistant.display.show_block(
        assistant._localized(lang, "USUNĄĆ PRZYPOMNIENIE?", "DELETE REMINDER?"),
        [reminder_message, reminder_id],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        f"Czy na pewno mam usunąć przypomnienie {reminder_message}?",
        f"Are you sure I should delete the reminder {reminder_message}?",
    )
    return True


def handle_reminders_clear(assistant, lang: str) -> bool:
    reminders = assistant.reminders.list_all()
    if not reminders:
        assistant._speak_localized(
            lang,
            "Nie ma przypomnień do usunięcia.",
            "There are no reminders to delete.",
        )
        return True

    assistant.pending_follow_up = {
        "type": "confirm_reminders_clear",
        "lang": lang,
    }
    assistant.display.show_block(
        assistant._localized(lang, "USUNĄĆ WSZYSTKIE?", "DELETE ALL?"),
        [assistant._localized(lang, f"przypomnienia: {len(reminders)}", f"reminders: {len(reminders)}")],
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

    assistant.display.show_block(
        assistant._localized(lang, "PRZYPOMNIENIE", "REMINDER"),
        [message, assistant._localized(lang, f"za {spoken_duration}", f"in {spoken_duration}")],
        duration=8.0,
    )
    assistant._speak_localized(
        lang,
        f"Dobrze. Przypomnę ci o tym za {spoken_duration}.",
        f"Okay. I will remind you about that in {spoken_duration}.",
    )
    append_log(f"Reminder created: {reminder['id']}")
    return True