from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from modules.shared.persistence.paths import APP_ROOT, resolve_optional_path

from .defaults import DEFAULT_SETTINGS
from .loading import load_settings
from .normalize import _normalize_runtime_path_value
from .persistence import save_settings


def get_setting(path: str, default: Any = None, *, settings: dict[str, Any] | None = None) -> Any:
    """
    Read a nested setting using dotted notation.

    Example:
        get_setting("voice_input.engine")
        get_setting("display.width", 128)
    """
    if not path:
        return default

    data = settings if settings is not None else load_settings()
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]

    return deepcopy(current)


def set_setting(path: str, value: Any) -> dict[str, Any]:
    """
    Update a single nested setting using dotted notation and persist it.
    """
    if not path:
        raise ValueError("path cannot be empty.")

    current = load_settings()
    target = current
    parts = path.split(".")

    for part in parts[:-1]:
        next_value = target.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            target[part] = next_value
        target = next_value

    target[parts[-1]] = deepcopy(value)
    return save_settings(current)


def resolve_settings_path(path_value: str | Path | None) -> Path | None:
    """
    Resolve a path stored inside the settings file.

    Relative paths are treated as project-root relative.
    """
    normalized_value = _normalize_runtime_path_value(path_value)
    return resolve_optional_path(normalized_value)


def export_default_settings() -> dict[str, Any]:
    """
    Return a fresh deep copy of the canonical default settings.
    """
    return deepcopy(DEFAULT_SETTINGS)


def project_root() -> Path:
    """
    Return the resolved NeXa project root.
    """
    return APP_ROOT


__all__ = [
    "export_default_settings",
    "get_setting",
    "project_root",
    "resolve_settings_path",
    "set_setting",
]