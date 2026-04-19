from __future__ import annotations

from typing import Callable, Generic, TypeVar

from modules.shared.persistence.json_store import JsonStore

T = TypeVar("T")


class BaseJsonRepository(Generic[T]):
    """Small repository wrapper around JsonStore for feature-level persistence contracts."""

    def __init__(
        self,
        *,
        path: str,
        default_factory: Callable[[], T],
    ) -> None:
        self._store = JsonStore(path=path, default_factory=default_factory)

    @property
    def store(self) -> JsonStore[T]:
        return self._store

    def ensure_exists(self) -> T:
        return self._store.ensure_exists()

    def read(self) -> T:
        return self._store.read()

    def write(self, payload: T) -> T:
        return self._store.write(payload)

    def update(self, updater):
        return self._store.update(updater)

    def reset(self) -> T:
        return self._store.reset()