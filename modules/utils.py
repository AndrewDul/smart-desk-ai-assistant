from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

REMINDERS_PATH = DATA_DIR / "reminders.json"
MEMORY_PATH = DATA_DIR / "memory.json"
SESSION_STATE_PATH = DATA_DIR / "session_state.json"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
SYSTEM_LOG_PATH = LOGS_DIR / "system.log"


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


def append_log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with SYSTEM_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"[{now_str()}] {message}\n")


def ensure_project_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
