from __future__ import annotations

from typing import Any

from .base_json_repository import BaseJsonRepository
from modules.shared.persistence.paths import USER_PROFILE_PATH


class UserProfileRepository(BaseJsonRepository[dict[str, Any]]):
    def __init__(
        self,
        *,
        default_user_name: str,
        project_name: str,
        path: str = str(USER_PROFILE_PATH),
    ) -> None:
        def _default_user_profile() -> dict[str, Any]:
            return {
                "name": str(default_user_name or "Andrzej"),
                "conversation_partner_name": "",
                "project": str(project_name or "NeXa"),
            }

        super().__init__(
            path=path,
            default_factory=_default_user_profile,
        )