from __future__ import annotations

from .base_json_repository import BaseJsonRepository
from modules.shared.persistence.paths import MEMORY_PATH


class MemoryRepository(BaseJsonRepository[dict[str, str]]):
    def __init__(self, *, path: str = str(MEMORY_PATH)) -> None:
        super().__init__(
            path=path,
            default_factory=dict,
        )