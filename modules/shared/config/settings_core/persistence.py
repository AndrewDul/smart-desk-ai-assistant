from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import (
    SETTINGS_EXAMPLE_PATH,
    SETTINGS_PATH,
    ensure_runtime_directories,
)

from .defaults import DEFAULT_SETTINGS
from .loading import load_settings, reset_settings_cache
from .normalize import _deep_merge_dicts, _normalize_settings_payload


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Save the full settings payload.

    I merge the incoming payload with defaults before persisting it so the file
    stays complete and stable over time.
    """
    if not isinstance(settings, dict):
        raise TypeError("settings must be a dictionary.")

    ensure_runtime_directories()

    merged = _deep_merge_dicts(DEFAULT_SETTINGS, settings)
    normalized = _normalize_settings_payload(merged)

    store = JsonStore(path=SETTINGS_PATH, default_factory=lambda: deepcopy(DEFAULT_SETTINGS))
    store.write(normalized)

    reset_settings_cache()
    return load_settings(force_reload=True)


def update_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """
    Merge a partial settings payload into the current settings and persist it.
    """
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dictionary.")

    current = load_settings()
    merged = _deep_merge_dicts(current, updates)
    return save_settings(merged)


def ensure_settings_file() -> dict[str, Any]:
    """
    Create the main settings file from defaults if it does not exist.
    """
    ensure_runtime_directories()

    if SETTINGS_PATH.exists():
        return load_settings()

    store = JsonStore(path=SETTINGS_PATH, default_factory=lambda: deepcopy(DEFAULT_SETTINGS))
    store.ensure_exists()
    reset_settings_cache()
    return load_settings(force_reload=True)


def ensure_settings_example_file() -> Path:
    """
    Create config/settings.example.json when it is missing.
    """
    ensure_runtime_directories()

    if SETTINGS_EXAMPLE_PATH.exists():
        return SETTINGS_EXAMPLE_PATH

    store = JsonStore(
        path=SETTINGS_EXAMPLE_PATH,
        default_factory=lambda: deepcopy(DEFAULT_SETTINGS),
    )
    store.ensure_exists()
    return SETTINGS_EXAMPLE_PATH


def bootstrap_settings_files() -> dict[str, Any]:
    """
    Ensure both settings files exist and return the live settings.
    """
    ensure_settings_example_file()
    return ensure_settings_file()


__all__ = [
    "bootstrap_settings_files",
    "ensure_settings_example_file",
    "ensure_settings_file",
    "save_settings",
    "update_settings",
]