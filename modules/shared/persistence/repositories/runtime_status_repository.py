from __future__ import annotations

from typing import Any, Callable

from modules.shared.persistence.json_store import JsonReadResult, JsonStore


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

    def ensure_valid(self) -> dict[str, Any]:
        result = self._store.read_result()
        if result.exists and result.valid:
            return dict(result.value)
        return dict(self._store.write(dict(result.value or {})))

    def read_result(self) -> JsonReadResult[dict[str, Any]]:
        return self._store.read_result()

    def write(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return dict(self._store.write(dict(snapshot or {})))

    def read(self) -> dict[str, Any]:
        return dict(self._store.read())