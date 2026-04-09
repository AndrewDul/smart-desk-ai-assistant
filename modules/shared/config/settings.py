from __future__ import annotations

from modules.shared.persistence.paths import SETTINGS_EXAMPLE_PATH, SETTINGS_PATH

from .settings_core import (
    DEFAULT_SETTINGS,
    bootstrap_settings_files,
    ensure_settings_example_file,
    ensure_settings_file,
    export_default_settings,
    get_setting,
    load_settings,
    project_root,
    reset_settings_cache,
    resolve_settings_path,
    save_settings,
    set_setting,
    update_settings,
)

__all__ = [
    "DEFAULT_SETTINGS",
    "SETTINGS_PATH",
    "SETTINGS_EXAMPLE_PATH",
    "bootstrap_settings_files",
    "ensure_settings_example_file",
    "ensure_settings_file",
    "export_default_settings",
    "get_setting",
    "load_settings",
    "project_root",
    "reset_settings_cache",
    "resolve_settings_path",
    "save_settings",
    "set_setting",
    "update_settings",
]