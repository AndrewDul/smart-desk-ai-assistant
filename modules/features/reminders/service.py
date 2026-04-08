from __future__ import annotations

import copy
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from modules.shared.logging.logger import append_log
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import REMINDERS_PATH


@dataclass(slots=True)
class ReminderMatch:
    reminder: dict[str, Any]
    score: float
    exact: bool = False


class ReminderService:
    """
    Persistent reminder service for NeXa.

    Data model:
    - id
    - message
    - language
    - created_at
    - due_at
    - status: pending | done
    - acknowledged: bool
    - delivered_count: int
    - triggered_at?: str
    - acknowledged_at?: str
    """

    def __init__(self, store: JsonStore[list[dict[str, Any]]] | None = None) -> None:
        self.store = store or JsonStore(
            path=REMINDERS_PATH,
            default_factory=list,
        )
        self.store.ensure_exists()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_after_seconds(
        self,
        *,
        seconds: int,
        message: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        safe_seconds = max(1, int(seconds))
        clean_message = self._clean_message(message)
        reminder_language = self._normalize_language(language)
        now = datetime.now()

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "message": clean_message,
            "language": reminder_language,
            "created_at": now.isoformat(),
            "due_at": (now + timedelta(seconds=safe_seconds)).isoformat(),
            "status": "pending",
            "acknowledged": False,
            "delivered_count": 0,
        }

        reminders = self._load_reminders()
        reminders.append(reminder)
        self._save_reminders(reminders)

        append_log(
            "Reminder added: "
            f"id={reminder['id']}, seconds={safe_seconds}, language={reminder_language}, message={clean_message}"
        )
        return copy.deepcopy(reminder)

    def list_all(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        reminders.sort(key=self._sort_key)
        return reminders

    def list_pending(self) -> list[dict[str, Any]]:
        return [item for item in self.list_all() if item.get("status") == "pending"]

    def count(self) -> int:
        return len(self._load_reminders())

    def has_any(self) -> bool:
        return bool(self._load_reminders())

    def check_due_reminders(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        due_reminders: list[dict[str, Any]] = []
        changed = False
        now = datetime.now()

        for reminder in reminders:
            if reminder.get("status") != "pending":
                continue

            due_at_raw = reminder.get("due_at")
            if not due_at_raw:
                continue

            try:
                due_time = datetime.fromisoformat(str(due_at_raw))
            except ValueError:
                append_log(f"Reminder skipped due to invalid due_at: {reminder}")
                continue

            if now >= due_time:
                reminder["status"] = "done"
                reminder["triggered_at"] = now.isoformat()
                reminder["acknowledged"] = False
                reminder["delivered_count"] = int(reminder.get("delivered_count", 0)) + 1
                due_reminders.append(copy.deepcopy(reminder))
                changed = True

        if changed:
            self._save_reminders(reminders)

        return due_reminders

    def mark_done(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        changed = False

        for reminder in reminders:
            if reminder.get("id") == reminder_id and reminder.get("status") != "done":
                reminder["status"] = "done"
                reminder["triggered_at"] = datetime.now().isoformat()
                reminder["acknowledged"] = False
                reminder["delivered_count"] = int(reminder.get("delivered_count", 0)) + 1
                changed = True
                break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder marked done manually: id={reminder_id}")

        return changed

    def mark_acknowledged(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        changed = False

        for reminder in reminders:
            if reminder.get("id") != reminder_id:
                continue

            if not bool(reminder.get("acknowledged", False)):
                reminder["acknowledged"] = True
                reminder["acknowledged_at"] = datetime.now().isoformat()
                changed = True
            break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder acknowledged: id={reminder_id}")

        return changed

    def delete(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        new_reminders = [item for item in reminders if item.get("id") != reminder_id]

        if len(new_reminders) == len(reminders):
            return False

        self._save_reminders(new_reminders)
        append_log(f"Reminder deleted: id={reminder_id}")
        return True

    def delete_by_message(self, query: str) -> tuple[str | None, str | None]:
        reminders = self._load_reminders()
        if not reminders:
            return None, None

        matched = self.find_by_message(query)
        if matched is None:
            return None, None

        matched_id = str(matched["id"])
        matched_message = str(matched["message"])

        new_reminders = [item for item in reminders if item.get("id") != matched_id]
        self._save_reminders(new_reminders)

        append_log(f"Reminder deleted by message: id={matched_id}, message={matched_message}")
        return matched_id, matched_message

    def find_by_id(self, reminder_id: str) -> dict[str, Any] | None:
        clean_id = str(reminder_id or "").strip()
        if not clean_id:
            return None

        for reminder in self._load_reminders():
            if str(reminder.get("id", "")).strip() == clean_id:
                return copy.deepcopy(reminder)
        return None

    def find_by_message(self, query: str) -> dict[str, Any] | None:
        reminders = self._load_reminders()
        if not reminders:
            return None

        match = self.match_by_message(query)
        if match is None:
            return None

        return copy.deepcopy(match.reminder)

    def match_by_message(self, query: str) -> ReminderMatch | None:
        reminders = self._load_reminders()
        if not reminders:
            return None

        query_clean = self._normalize_text(query)
        if not query_clean:
            return None

        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if message == query_clean:
                return ReminderMatch(
                    reminder=copy.deepcopy(reminder),
                    score=1.0,
                    exact=True,
                )

        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if query_clean in message or message in query_clean:
                return ReminderMatch(
                    reminder=copy.deepcopy(reminder),
                    score=0.92,
                    exact=False,
                )

        query_tokens = self._tokenize(query_clean)
        best_match: dict[str, Any] | None = None
        best_score = 0.0

        for reminder in reminders:
            raw_message = str(reminder.get("message", ""))
            normalized_message = self._normalize_text(raw_message)
            message_tokens = self._tokenize(normalized_message)

            overlap_score = self._token_overlap_score(query_tokens, message_tokens)
            similarity_score = SequenceMatcher(None, query_clean, normalized_message).ratio()
            combined_score = max(overlap_score, similarity_score)

            if combined_score > best_score:
                best_score = combined_score
                best_match = reminder

        if best_match is not None and best_score >= 0.58:
            return ReminderMatch(
                reminder=copy.deepcopy(best_match),
                score=best_score,
                exact=False,
            )

        return None

    def clear(self) -> int:
        reminders = self._load_reminders()
        count = len(reminders)
        self._save_reminders([])
        append_log(f"All reminders cleared: removed {count} item(s).")
        return count

    def clear_all(self) -> int:
        return self.clear()

    def delete_all(self) -> int:
        return self.clear()

    def clear_done(self) -> int:
        reminders = self._load_reminders()
        kept = [item for item in reminders if item.get("status") != "done"]
        removed = len(reminders) - len(kept)

        if removed > 0:
            self._save_reminders(kept)
            append_log(f"Completed reminders cleared: removed {removed} item(s).")

        return removed

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_key(reminder: dict[str, Any]) -> tuple[int, str]:
        status = str(reminder.get("status", "pending"))
        due_at = str(reminder.get("due_at", ""))
        return (0 if status == "pending" else 1, due_at)

    @staticmethod
    def _clean_message(message: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(message or "").strip())

        prefixes = ("about ", "to ", "o ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    changed = True

        return cleaned

    @staticmethod
    def _normalize_status(status: Any) -> str:
        normalized = str(status or "pending").strip().lower()
        if normalized not in {"pending", "done"}:
            return "pending"
        return normalized

    @staticmethod
    def _normalize_language(language: Any) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.split() if token]

    @staticmethod
    def _token_overlap_score(left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0

        left_set = set(left_tokens)
        right_set = set(right_tokens)
        common = left_set & right_set

        if not common:
            return 0.0

        return float(len(common) / max(len(left_set), len(right_set)))

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = [
    "ReminderMatch",
    "ReminderService",
]