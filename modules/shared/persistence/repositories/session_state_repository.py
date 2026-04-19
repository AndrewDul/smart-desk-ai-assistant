from __future__ import annotations

from typing import Any

from .base_json_repository import BaseJsonRepository
from modules.shared.persistence.paths import SESSION_STATE_PATH


def _default_session_state() -> dict[str, Any]:
    return {
        "assistant_running": False,
        "focus_mode": False,
        "break_mode": False,
        "current_timer": None,
    }


class SessionStateRepository(BaseJsonRepository[dict[str, Any]]):
    def __init__(self, *, path: str = str(SESSION_STATE_PATH)) -> None:
        super().__init__(
            path=path,
            default_factory=_default_session_state,
        )