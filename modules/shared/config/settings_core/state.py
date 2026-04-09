from __future__ import annotations

from threading import RLock
from typing import Any

_SETTINGS_LOCK = RLock()
_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_MTIME_NS: int | None = None


def settings_lock() -> RLock:
    return _SETTINGS_LOCK


def get_settings_cache() -> tuple[dict[str, Any] | None, int | None]:
    return _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS


def set_settings_cache(settings: dict[str, Any], mtime_ns: int | None) -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS

    _SETTINGS_CACHE = settings
    _SETTINGS_CACHE_MTIME_NS = mtime_ns


def reset_cache_state() -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS

    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_MTIME_NS = None


__all__ = [
    "get_settings_cache",
    "reset_cache_state",
    "set_settings_cache",
    "settings_lock",
]