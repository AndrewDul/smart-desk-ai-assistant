from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.shared.config.settings import (
    DEFAULT_SETTINGS,
    ensure_settings_example_file,
    ensure_settings_file,
    load_settings as _load_shared_settings,
)
from modules.shared.logging.logger import append_log
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import (
    APP_ROOT,
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    MEMORY_PATH,
    REMINDERS_PATH,
    SESSION_STATE_PATH,
    SETTINGS_EXAMPLE_PATH,
    SETTINGS_PATH,
    SYSTEM_LOG_PATH,
    USER_PROFILE_PATH,
    ensure_runtime_directories,
)

# ---------------------------------------------------------------------------
# Backward-compatible path aliases
# ---------------------------------------------------------------------------

BASE_DIR = APP_ROOT

# ---------------------------------------------------------------------------
# Simple helpers kept for backward compatibility
# ---------------------------------------------------------------------------


def now_str() -> str:
    """
    Return the current local timestamp in the legacy string format.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    """
    Backward-compatible safe JSON loader.

    Existing modules still call:
        load_json(SOME_PATH, {})
        load_json(SOME_PATH, [])

    Internally I now route everything through the shared JsonStore.
    """
    store = JsonStore(path=path, default_factory=lambda: deepcopy(default))
    return store.read()


def save_json(path: Path, data: Any) -> None:
    """
    Backward-compatible atomic JSON writer.
    """
    store = JsonStore(path=path, default_factory=lambda: deepcopy(data))
    store.write(data)


def load_settings(force_reload: bool = False) -> dict[str, Any]:
    """
    Backward-compatible settings loader.

    Old code imports this from modules.system.utils, but the real logic now
    lives in modules.shared.config.settings.
    """
    return _load_shared_settings(force_reload=force_reload)


def ensure_project_files() -> None:
    """
    Ensure the minimum runtime files and folders required by the current app.

    I keep this function because the current codebase still calls it from
    several places, especially during startup.
    """
    ensure_runtime_directories()
    ensure_settings_example_file()
    settings = ensure_settings_file()

    _ensure_json_file(REMINDERS_PATH, [])
    _ensure_json_file(MEMORY_PATH, {})
    _ensure_json_file(
        SESSION_STATE_PATH,
        {
            "assistant_running": False,
            "focus_mode": False,
            "break_mode": False,
            "current_timer": None,
        },
    )
    _ensure_json_file(
        USER_PROFILE_PATH,
        {
            "name": str(settings.get("user", {}).get("name", "Andrzej")),
            "conversation_partner_name": "",
            "project": str(settings.get("project", {}).get("name", "NeXa")),
        },
    )

    _ensure_log_file(SYSTEM_LOG_PATH)


def _ensure_json_file(path: Path, default: Any) -> None:
    """
    Create a JSON file with a default payload when it does not exist.
    """
    store = JsonStore(path=path, default_factory=lambda: deepcopy(default))
    store.ensure_exists()


def _ensure_log_file(path: Path) -> None:
    """
    Ensure the primary log file exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    try:
        path.touch()
    except OSError:
        pass


__all__ = [
    "APP_ROOT",
    "BASE_DIR",
    "CACHE_DIR",
    "CONFIG_DIR",
    "DATA_DIR",
    "DEFAULT_SETTINGS",
    "LOGS_DIR",
    "MEMORY_PATH",
    "REMINDERS_PATH",
    "SESSION_STATE_PATH",
    "SETTINGS_EXAMPLE_PATH",
    "SETTINGS_PATH",
    "SYSTEM_LOG_PATH",
    "USER_PROFILE_PATH",
    "append_log",
    "ensure_project_files",
    "load_json",
    "load_settings",
    "now_str",
    "save_json",
]