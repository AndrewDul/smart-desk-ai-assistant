from __future__ import annotations

from typing import Any, Callable

from modules.shared.persistence.json_store import JsonStore


class RuntimeStatusRepository:
    """Thin persistence contract for the runtime product snapshot."""

    def __init__(
        self,
        *,
        path: str = "var/data/runtime_status.json",
        default_factory: Callable[[], dict[str, Any]],
    ) -> None:
        self._store = JsonStore(path=path, default_factory=default_factory)

    def ensure_exists(self) -> dict[str, Any]:
        return dict(self._store.ensure_exists())

    def write(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return dict(self._store.write(dict(snapshot or {})))

    def read(self) -> dict[str, Any]:
        return dict(self._store.read())