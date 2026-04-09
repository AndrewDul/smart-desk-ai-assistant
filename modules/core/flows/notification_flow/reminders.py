from __future__ import annotations

from typing import Any

from modules.shared.logging.logger import append_log


class NotificationFlowReminders:
    """Reminder-specific helpers for async notification delivery."""

    assistant: Any

    def reminder_language(self, reminder: dict[str, Any]) -> str:
        assistant = self.assistant
        stored = reminder.get("language") or reminder.get("lang")

        normalize_lang = getattr(assistant, "_normalize_lang", None)
        if callable(normalize_lang):
            try:
                return str(normalize_lang(stored or assistant.last_language))
            except Exception:
                pass

        normalized = str(stored or getattr(assistant, "last_language", "en")).strip().lower()
        return "pl" if normalized.startswith("pl") else "en"

    def deliver_due_reminder(self, reminder: dict[str, Any]) -> None:
        assistant = self.assistant
        message = str(reminder.get("message", "Reminder triggered.")).strip() or "Reminder triggered."
        lang = self.reminder_language(reminder)

        localized = getattr(assistant, "_localized")
        spoken_text = localized(
            lang,
            f"Przypomnienie. {message}",
            f"Reminder. {message}",
        )

        self.deliver_async_notification(
            lang=lang,
            spoken_text=spoken_text,
            display_title=localized(lang, "PRZYPOMNIENIE", "REMINDER"),
            display_lines=[message],
            source="reminder",
            route_kind="reminder",
            action="reminder_due",
            display_duration=max(float(getattr(assistant, "default_overlay_seconds", 8.0)), 12.0),
            extra_metadata={
                "reminder_id": reminder.get("id"),
                "reminder_status": reminder.get("status"),
                "reminder_due_at": reminder.get("due_at"),
                "triggered_at": reminder.get("triggered_at"),
            },
        )

        append_log(
            f"Reminder delivered: id={reminder.get('id')}, lang={lang}, message={message}"
        )


__all__ = ["NotificationFlowReminders"]