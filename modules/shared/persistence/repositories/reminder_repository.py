from __future__ import annotations

from typing import Any

from .base_json_repository import BaseJsonRepository
from modules.shared.persistence.paths import REMINDERS_PATH


class ReminderRepository(BaseJsonRepository[list[dict[str, Any]]]):
    def __init__(self, *, path: str = str(REMINDERS_PATH)) -> None:
        super().__init__(
            path=path,
            default_factory=list,
        )