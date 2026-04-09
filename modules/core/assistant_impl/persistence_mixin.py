from __future__ import annotations

from typing import Any


class CoreAssistantPersistenceMixin:
    def _default_state_payload(self) -> dict[str, Any]:
        return {
            "assistant_running": False,
            "focus_mode": False,
            "break_mode": False,
            "current_timer": None,
        }

    def _default_user_profile_payload(self) -> dict[str, Any]:
        return {
            "name": self.default_user_name,
            "conversation_partner_name": "",
            "project": self.project_name,
        }

    def _save_state(self) -> None:
        self.state = self.state_store.write(self.state)

    def _save_user_profile(self) -> None:
        self.user_profile = self.user_profile_store.write(self.user_profile)