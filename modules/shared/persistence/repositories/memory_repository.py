from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.shared.persistence.paths import MEMORY_PATH


class MemoryRepository:
    """
    JSON repository for persistent user memory.

    This repository intentionally accepts two shapes:

    - dict: legacy key/value memory format
    - list: product-grade memory record format

    The MemoryService owns migration and normalization. The repository only
    guarantees safe JSON read/write and must not erase legacy data before the
    service can migrate it.
    """

    def __init__(self, *, path: str = str(MEMORY_PATH)) -> None:
        self.path = Path(path)

    def ensure_valid(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.path.exists():
            self.write([])
            return

        try:
            data = json.loads(self.path.read_text() or "[]")
        except json.JSONDecodeError:
            self.write([])
            return

        if isinstance(data, (dict, list)):
            return

        self.write([])

    def read(self) -> Any:
        self.ensure_valid()

        try:
            return json.loads(self.path.read_text() or "[]")
        except json.JSONDecodeError:
            self.write([])
            return []

    def write(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not isinstance(data, (dict, list)):
            data = []

        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
