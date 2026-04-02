from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_MTIME_NS: int | None = None


def _find_project_root(start_file: Path) -> Path:
    """
    Resolve the real project root even after refactors.
    Expected root contains at least: main.py and modules/.
    """
    current = start_file.resolve()

    for candidate in [current.parent, *current.parents]:
        if (candidate / "main.py").exists() and (candidate / "modules").exists():
            return candidate

    # Safe fallback for current structure: modules/system/utils.py -> project root
    return current.parents[2]


BASE_DIR = _find_project_root(Path(__file__))
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
CACHE_DIR = BASE_DIR / "cache"

REMINDERS_PATH = DATA_DIR / "reminders.json"
MEMORY_PATH = DATA_DIR / "memory.json"
SESSION_STATE_PATH = DATA_DIR / "session_state.json"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
SYSTEM_LOG_PATH = LOGS_DIR / "system.log"

SETTINGS_PATH = CONFIG_DIR / "settings.json"
SETTINGS_EXAMPLE_PATH = CONFIG_DIR / "settings.example.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "project": {
        "name": "Smart Desk AI Assistant",
        "version": "0.4.0-premium-core",
        "stage": "stage-1-stationary-premium-core",
    },
    "user": {
        "name": "Andrzej",
    },
    "voice_input": {
        "enabled": True,
        "engine": "whisper",
        "device_index": None,
        "device_name_contains": "USB PnP Sound Device",
        "timeout_seconds": 8,
        "debug": False,
        "sample_rate": None,
        "max_record_seconds": 5.5,
        "silence_threshold": 350.0,
        "end_silence_seconds": 0.6,
        "pre_roll_seconds": 0.35,
        "threads": 4,
        "language": "auto",
        "vad_enabled": False,
        "whisper_cli_path": "whisper.cpp/build/bin/whisper-cli",
        "model_path": "models/ggml-base.bin",
        "vad_model_path": "models/ggml-silero-v6.2.0.bin",
    },
    "voice_output": {
        "enabled": True,
        "engine": "piper",
        "default_language": "en",
        "speed": 155,
        "pitch": 58,
        "voices": {
            "pl": "pl+f3",
            "en": "en+f3",
        },
        "piper_models": {
            "pl": {
                "model": "voices/piper/pl_PL-gosia-medium.onnx",
                "config": "voices/piper/pl_PL-gosia-medium.onnx.json",
            },
            "en": {
                "model": "voices/piper/en_GB-jenny_dioco-medium.onnx",
                "config": "voices/piper/en_GB-jenny_dioco-medium.onnx.json",
            },
        },
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
        "boot_overlay_seconds": 2.8,
    },
    "timers": {
        "default_focus_minutes": 25,
        "default_break_minutes": 5,
    },
    "logging": {
        "enabled": True,
        "log_file": "logs/system.log",
        "max_bytes": 1_000_000,
        "backup_count": 2,
    },
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data
    except (FileNotFoundError, json.JSONDecodeError, TypeError, OSError, ValueError):
        return deepcopy(default)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_settings(force_reload: bool = False) -> dict[str, Any]:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS

    try:
        current_mtime_ns = SETTINGS_PATH.stat().st_mtime_ns
    except OSError:
        current_mtime_ns = None

    cache_valid = (
        not force_reload
        and _SETTINGS_CACHE is not None
        and _SETTINGS_CACHE_MTIME_NS == current_mtime_ns
    )
    if cache_valid:
        return deepcopy(_SETTINGS_CACHE)

    file_settings = load_json(SETTINGS_PATH, {})
    if not isinstance(file_settings, dict):
        file_settings = {}

    merged_settings = _deep_merge_dicts(DEFAULT_SETTINGS, file_settings)
    _SETTINGS_CACHE = deepcopy(merged_settings)
    _SETTINGS_CACHE_MTIME_NS = current_mtime_ns
    return merged_settings


def _rotate_log_if_needed(log_path: Path, max_bytes: int, backup_count: int) -> None:
    if max_bytes <= 0:
        return
    if not log_path.exists():
        return

    try:
        size = log_path.stat().st_size
    except OSError:
        return

    if size < max_bytes:
        return

    if backup_count < 1:
        try:
            log_path.unlink()
        except OSError:
            pass
        return

    oldest_backup = log_path.with_name(f"{log_path.name}.{backup_count}")
    if oldest_backup.exists():
        try:
            oldest_backup.unlink()
        except OSError:
            pass

    for index in range(backup_count - 1, 0, -1):
        src = log_path.with_name(f"{log_path.name}.{index}")
        dst = log_path.with_name(f"{log_path.name}.{index + 1}")
        if src.exists():
            try:
                src.replace(dst)
            except OSError:
                pass

    first_backup = log_path.with_name(f"{log_path.name}.1")
    try:
        log_path.replace(first_backup)
    except OSError:
        pass


def append_log(message: str) -> None:
    settings = load_settings()
    logging_cfg = settings.get("logging", {})
    if not logging_cfg.get("enabled", True):
        return

    log_relative_path = logging_cfg.get("log_file", "logs/system.log")
    log_path = BASE_DIR / log_relative_path if not Path(log_relative_path).is_absolute() else Path(log_relative_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = int(logging_cfg.get("max_bytes", 1_000_000))
    backup_count = int(logging_cfg.get("backup_count", 2))
    _rotate_log_if_needed(log_path, max_bytes=max_bytes, backup_count=backup_count)

    try:
        with log_path.open("a", encoding="utf-8") as file:
            file.write(f"[{now_str()}] {message}\n")
    except OSError:
        pass


def ensure_project_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
                "conversation_partner_name": "",
                "project": "Smart Desk AI Assistant",
            },
        )

    if not SYSTEM_LOG_PATH.exists():
        try:
            SYSTEM_LOG_PATH.touch()
        except OSError:
            pass

    if not SETTINGS_EXAMPLE_PATH.exists():
        save_json(SETTINGS_EXAMPLE_PATH, DEFAULT_SETTINGS)

    if not SETTINGS_PATH.exists():
        save_json(SETTINGS_PATH, DEFAULT_SETTINGS)