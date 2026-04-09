from __future__ import annotations

from typing import Any

from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import REMINDERS_PATH

from .helpers import ReminderServiceHelpers
from .mutations import ReminderServiceMutations
from .persistence import ReminderServicePersistence
from .queries import ReminderServiceQueries


class ReminderService(
    ReminderServicePersistence,
    ReminderServiceQueries,
    ReminderServiceMutations,
    ReminderServiceHelpers,
):
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


__all__ = [
    "ReminderService",
]