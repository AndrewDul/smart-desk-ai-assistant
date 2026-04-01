from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

REMINDERS_PATH = DATA_DIR / "reminders.json"
MEMORY_PATH = DATA_DIR / "memory.json"
SESSION_STATE_PATH = DATA_DIR / "session_state.json"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
SYSTEM_LOG_PATH = LOGS_DIR / "system.log"

SETTINGS_PATH = CONFIG_DIR / "settings.json"
SETTINGS_EXAMPLE_PATH = CONFIG_DIR / "settings.example.json"

DEFAULT_SETTINGS = {
    "project": {
        "name": "Smart Desk AI Assistant",
        "version": "0.1.0-alpha",
        "stage": "stage-1-stationary-core",
    },
    "user": {
        "name": "Andrzej",
    },
    "voice_input": {
        "enabled": True,
        "device_index": 2,
        "use_grammar": False,
        "timeout_seconds": 8,
        "debug": False,
        "model_path": "models/vosk-model-small-en-us-0.15",
    },
    "voice_output": {
        "enabled": True,
        "engine": "espeak-ng",
    },
    "display": {
        "enabled": True,
        "driver": "ssd1306",
        "interface": "i2c",
        "port": 1,
        "address": 60,
        "rotate": 0,
        "width": 128,
        "height": 64,
        "default_overlay_seconds": 10,
        "boot_overlay_seconds": 4,
    },
    "timers": {
        "default_focus_minutes": 25,
        "default_break_minutes": 5,
    },
    "logging": {
        "enabled": True,
        "log_file": "logs/system.log",
    },
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)

    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_settings() -> dict[str, Any]:
    file_settings = load_json(SETTINGS_PATH, {})
    if not isinstance(file_settings, dict):
        file_settings = {}

    return _deep_merge_dicts(DEFAULT_SETTINGS, file_settings)


def append_log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with SYSTEM_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{now_str()}] {message}\n")


def ensure_project_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not REMINDERS_PATH.exists():
        save_json(REMINDERS_PATH, [])

    if not MEMORY_PATH.exists():
        save_json(MEMORY_PATH, {})

    if not SESSION_STATE_PATH.exists():
        save_json(
            SESSION_STATE_PATH,
            {
                "assistant_running": False,
                "focus_mode": False,
                "break_mode": False,
                "current_timer": None,
            },
        )

    if not USER_PROFILE_PATH.exists():
        save_json(
            USER_PROFILE_PATH,
            {
                "name": "Andrzej",
                "project": "Smart Desk AI Assistant",
            },
        )

    if not SYSTEM_LOG_PATH.exists():
        SYSTEM_LOG_PATH.touch()

    if not SETTINGS_EXAMPLE_PATH.exists():
        save_json(SETTINGS_EXAMPLE_PATH, DEFAULT_SETTINGS)

    if not SETTINGS_PATH.exists():
        save_json(SETTINGS_PATH, DEFAULT_SETTINGS)