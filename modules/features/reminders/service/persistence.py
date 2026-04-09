from __future__ import annotations

from typing import Any


class ReminderServicePersistence:
    """Persistence and reminder item normalization helpers."""

    store: Any

    def _load_reminders(self) -> list[dict[str, Any]]:
        data = self.store.read()
        if not isinstance(data, list):
            return []

        cleaned: list[dict[str, Any]] = []
        for item in data:
            cleaned_item = self._normalize_reminder_item(item)
            if cleaned_item is not None:
                cleaned.append(cleaned_item)

        return cleaned

    def _save_reminders(self, reminders: list[dict[str, Any]]) -> None:
        cleaned: list[dict[str, Any]] = []
        for item in reminders:
            cleaned_item = self._normalize_reminder_item(item)
            if cleaned_item is not None:
                cleaned.append(cleaned_item)

        self.store.write(cleaned)

    def _normalize_reminder_item(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        reminder_id = str(item.get("id", "")).strip()
        message = self._clean_message(str(item.get("message", "")))
        language = self._normalize_language(item.get("language"))
        created_at = str(item.get("created_at", "")).strip()
        due_at = str(item.get("due_at", "")).strip()
        status = self._normalize_status(item.get("status"))
        triggered_at = str(item.get("triggered_at", "")).strip()
        acknowledged = bool(item.get("acknowledged", False))
        acknowledged_at = str(item.get("acknowledged_at", "")).strip()
        delivered_count = self._safe_int(item.get("delivered_count", 0), default=0)

        if not reminder_id or not message or not due_at:
            return None

        cleaned_item = {
            "id": reminder_id,
            "message": message,
            "language": language,
            "created_at": created_at or due_at,
            "due_at": due_at,
            "status": status,
            "acknowledged": acknowledged,
            "delivered_count": delivered_count,
        }

        if triggered_at:
            cleaned_item["triggered_at"] = triggered_at

        if acknowledged_at:
            cleaned_item["acknowledged_at"] = acknowledged_at

        return cleaned_item


__all__ = ["ReminderServicePersistence"]