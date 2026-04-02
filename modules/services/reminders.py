from __future__ import annotations

import copy
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from modules.system.utils import REMINDERS_PATH, append_log, load_json, save_json


class ReminderManager:
    def __init__(self) -> None:
        self.path = REMINDERS_PATH
        self._cache: list[dict[str, Any]] | None = None
        self._cache_mtime_ns: int | None = None

    def add_after_seconds(self, seconds: int, message: str) -> dict[str, Any]:
        safe_seconds = max(1, int(seconds))
        clean_message = self._clean_message(message)

        reminders = self._load_reminders()
        now = datetime.now()

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "message": clean_message,
            "created_at": now.isoformat(),
            "due_at": (now + timedelta(seconds=safe_seconds)).isoformat(),
            "status": "pending",
        }

        reminders.append(reminder)
        self._save_reminders(reminders)

        append_log(
            f"Reminder added: id={reminder['id']}, seconds={safe_seconds}, message={clean_message}"
        )
        return reminder

    def list_all(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        reminders.sort(key=self._sort_key)
        return reminders

    def list_pending(self) -> list[dict[str, Any]]:
        return [item for item in self.list_all() if item.get("status") == "pending"]

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
                due_reminders.append(reminder)
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
                changed = True
                break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder marked done manually: id={reminder_id}")

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
        reminders = self._load_reminders()
        for reminder in reminders:
            if reminder.get("id") == reminder_id:
                return reminder
        return None

    def find_by_message(self, query: str) -> dict[str, Any] | None:
        reminders = self._load_reminders()
        if not reminders:
            return None

        query_clean = self._normalize_text(query)
        if not query_clean:
            return None

        exact_match = None
        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if message == query_clean:
                exact_match = reminder
                break

        if exact_match is not None:
            return exact_match

        substring_match = None
        for reminder in reminders:
            message = self._normalize_text(str(reminder.get("message", "")))
            if query_clean in message or message in query_clean:
                substring_match = reminder
                break

        if substring_match is not None:
            return substring_match

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

        if best_score >= 0.58:
            return best_match

        return None

    def clear(self) -> int:
        reminders = self._load_reminders()
        count = len(reminders)
        self._save_reminders([])
        append_log(f"All reminders cleared: removed {count} item(s).")
        return count

    def clear_done(self) -> int:
        reminders = self._load_reminders()
        kept = [item for item in reminders if item.get("status") != "done"]
        removed = len(reminders) - len(kept)

        if removed > 0:
            self._save_reminders(kept)
            append_log(f"Completed reminders cleared: removed {removed} item(s).")

        return removed

    def _get_file_mtime_ns(self) -> int | None:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def _read_reminders_from_disk(self) -> list[dict[str, Any]]:
        data = load_json(self.path, [])
        if not isinstance(data, list):
            return []

        cleaned: list[dict[str, Any]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            reminder_id = str(item.get("id", "")).strip()
            message = self._clean_message(str(item.get("message", "")))
            created_at = str(item.get("created_at", "")).strip()
            due_at = str(item.get("due_at", "")).strip()
            status = str(item.get("status", "pending")).strip() or "pending"
            triggered_at = str(item.get("triggered_at", "")).strip()

            if not reminder_id or not message or not due_at:
                continue

            cleaned_item = {
                "id": reminder_id,
                "message": message,
                "created_at": created_at or due_at,
                "due_at": due_at,
                "status": status,
            }

            if triggered_at:
                cleaned_item["triggered_at"] = triggered_at

            cleaned.append(cleaned_item)

        return cleaned

    def _load_reminders(self) -> list[dict[str, Any]]:
        current_mtime_ns = self._get_file_mtime_ns()

        cache_valid = (
            self._cache is not None
            and self._cache_mtime_ns == current_mtime_ns
        )
        if cache_valid:
            return copy.deepcopy(self._cache)

        cleaned = self._read_reminders_from_disk()
        self._cache = copy.deepcopy(cleaned)
        self._cache_mtime_ns = current_mtime_ns
        return copy.deepcopy(cleaned)

    def _save_reminders(self, reminders: list[dict[str, Any]]) -> None:
        save_json(self.path, reminders)

        cleaned: list[dict[str, Any]] = []
        for item in reminders:
            if not isinstance(item, dict):
                continue

            reminder_id = str(item.get("id", "")).strip()
            message = self._clean_message(str(item.get("message", "")))
            created_at = str(item.get("created_at", "")).strip()
            due_at = str(item.get("due_at", "")).strip()
            status = str(item.get("status", "pending")).strip() or "pending"
            triggered_at = str(item.get("triggered_at", "")).strip()

            if not reminder_id or not message or not due_at:
                continue

            cleaned_item = {
                "id": reminder_id,
                "message": message,
                "created_at": created_at or due_at,
                "due_at": due_at,
                "status": status,
            }

            if triggered_at:
                cleaned_item["triggered_at"] = triggered_at

            cleaned.append(cleaned_item)

        self._cache = copy.deepcopy(cleaned)
        self._cache_mtime_ns = self._get_file_mtime_ns()

    @staticmethod
    def _sort_key(reminder: dict[str, Any]) -> tuple[int, str]:
        status = str(reminder.get("status", "pending"))
        due_at = str(reminder.get("due_at", ""))
        return (0 if status == "pending" else 1, due_at)

    def _clean_message(self, message: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(message).strip())

        prefixes = ("about ", "to ", "o ")
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True

        return cleaned

    def _normalize_text(self, text: str) -> str:
        lowered = text.lower().strip()
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

        return len(common) / max(len(left_set), len(right_set))