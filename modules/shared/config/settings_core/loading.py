from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import SETTINGS_PATH, ensure_runtime_directories

from .defaults import DEFAULT_SETTINGS
from .normalize import _deep_merge_dicts, _normalize_settings_payload
from .state import get_settings_cache, reset_cache_state, set_settings_cache, settings_lock


def _read_raw_settings_file(path: Path) -> dict[str, Any]:
    """
    Read the main settings file defensively.

    Invalid or missing JSON never crashes the product startup.
    """
    store = JsonStore(path=path, default_factory=dict)
    data = store.read()
    return data if isinstance(data, dict) else {}


def _current_settings_mtime_ns(path: Path) -> int | None:
    """
    Return the nanosecond mtime for cache invalidation.
    """
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def reset_settings_cache() -> None:
    """
    Clear the in-process settings cache.
    """
    with settings_lock():
        reset_cache_state()


def load_settings(*, force_reload: bool = False) -> dict[str, Any]:
    """
    Load merged application settings.

    Merge order:
    1. DEFAULT_SETTINGS
    2. config/settings.json

    This keeps the product resilient when new settings are introduced
    but older config files still exist on disk.
    """
    ensure_runtime_directories()

    with settings_lock():
        current_mtime_ns = _current_settings_mtime_ns(SETTINGS_PATH)
        cached_settings, cached_mtime_ns = get_settings_cache()

        cache_valid = (
            not force_reload
            and cached_settings is not None
            and cached_mtime_ns == current_mtime_ns
        )
        if cache_valid:
            return deepcopy(cached_settings)

        file_settings = _read_raw_settings_file(SETTINGS_PATH)
        merged = _deep_merge_dicts(DEFAULT_SETTINGS, file_settings)
        normalized = _normalize_settings_payload(merged)

        set_settings_cache(deepcopy(normalized), current_mtime_ns)
        return deepcopy(normalized)


__all__ = [
    "load_settings",
    "reset_settings_cache",
]