from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import (
    APP_ROOT,
    SETTINGS_EXAMPLE_PATH,
    SETTINGS_PATH,
    ensure_runtime_directories,
    resolve_optional_path,
)

_SETTINGS_LOCK = RLock()
_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_MTIME_NS: int | None = None

_RUNTIME_PATH_MIGRATIONS: dict[str, str] = {
    "logs/system.log": "var/logs/system.log",
    "data/reminders.json": "var/data/reminders.json",
    "data/memory.json": "var/data/memory.json",
    "data/session_state.json": "var/data/session_state.json",
    "data/user_profile.json": "var/data/user_profile.json",
    "cache": "var/cache",
    "logs": "var/logs",
    "data": "var/data",
}


DEFAULT_SETTINGS: dict[str, Any] = {
    "project": {
        "name": "NeXa",
        "version": "0.7.0",
        "stage": "premium-product-foundation",
    },
    "user": {
        "name": "Andrzej",
    },
    "voice_input": {
        "enabled": True,
        "engine": "faster_whisper",
        "wake_engine": "openwakeword",
        "wake_model_path": "models/wake/nexa.onnx",
        "wake_threshold": 0.5,
        "wake_trigger_level": 2,
        "wake_block_ms": 80,
        "wake_vad_threshold": 0.28,
        "wake_enable_speex_noise_suppression": True,
        "wake_debug": False,
        "device_index": None,
        "device_name_contains": None,
        "timeout_seconds": 7,
        "active_listen_window_seconds": 6.0,
        "thinking_ack_seconds": 1.2,
        "debug": False,
        "sample_rate": 16000,
        "max_record_seconds": 6.5,
        "end_silence_seconds": 0.6,
        "pre_roll_seconds": 0.45,
        "blocksize": 512,
        "min_speech_seconds": 0.2,
        "transcription_timeout_seconds": 10.0,
        "threads": 4,
        "language": "auto",
        "vad_enabled": True,
        "vad_threshold": 0.3,
        "vad_min_speech_ms": 120,
        "vad_min_silence_ms": 250,
        "vad_speech_pad_ms": 180,
        "compute_type": "int8",
        "beam_size": 1,
        "best_of": 1,
        "model_size_or_path": "tiny",
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
        "driver": "waveshare_2inch",
        "interface": "spi",
        "port": 1,
        "address": 60,
        "rotate": 0,
        "width": 240,
        "height": 320,
        "gpio_dc": 25,
        "gpio_rst": 27,
        "gpio_light": 18,
        "spi_port": 0,
        "spi_device": 0,
        "default_overlay_seconds": 8,
        "boot_overlay_seconds": 2.4,
    },
    "timers": {
        "default_focus_minutes": 25,
        "default_break_minutes": 5,
    },
    "streaming": {
        "dialogue_stream_mode": "sentence",
        "inter_chunk_pause_seconds": 0.0,
        "max_display_lines": 2,
        "max_display_chars_per_line": 20,
    },
    "audio_coordination": {
        "self_hearing_hold_seconds": 0.9,
        "listen_resume_poll_seconds": 0.04,
    },
    "conversation": {
        "max_turns": 8,
        "max_total_chars": 1800,
    },
    "llm": {
        "enabled": False,
        "runner": "llama-cli",
        "command": "llama-cli",
        "model_path": "models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
        "n_predict": 96,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "ctx_size": 2048,
        "threads": 4,
        "timeout_seconds": 18.0,
        "repeat_penalty": 1.1,
        "max_prompt_chars": 2400,
        "prefer_json": False,
        "server_url": "http://127.0.0.1:8080",
        "server_chat_path": "/v1/chat/completions",
        "server_health_path": "/health",
        "server_api_key": "",
        "server_model_name": "",
        "server_use_openai_compat": True,
        "server_connect_timeout_seconds": 3.0,
    },
    "logging": {
        "enabled": True,
        "console_enabled": False,
        "log_file": "var/logs/system.log",
        "max_bytes": 1_000_000,
        "backup_count": 2,
    },
    "system": {
        "allow_shutdown_commands": False,
        "shutdown_command": ["systemctl", "poweroff"],
    },
    "fast_command_lane": {
        "enabled": True,
    },
    "vision": {
        "enabled": False,
        "camera_index": 0,
        "frame_width": 1280,
        "frame_height": 720,
        "face_detection_enabled": False,
        "object_detection_enabled": False,
        "scene_understanding_enabled": False,
        "gesture_recognition_enabled": False,
        "behavior_interpretation_enabled": False,
    },
    "mobility": {
        "enabled": False,
        "base_type": "differential",
        "safety_stop_enabled": True,
        "max_linear_speed": 0.3,
        "max_turn_speed": 0.5,
    },
}


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge nested dictionaries.

    Values from `override` always win.
    """
    result = deepcopy(base)

    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def _normalize_runtime_path_value(value: Any) -> Any:
    """
    Migrate known legacy runtime-relative paths to the canonical `var/...` layout.

    Only string values that exactly match known legacy paths are rewritten.
    All other values are preserved unchanged.
    """
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if not normalized:
        return value

    normalized = normalized.replace("\\", "/")
    return _RUNTIME_PATH_MIGRATIONS.get(normalized, value)


def _normalize_settings_payload(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize live settings so runtime code sees a consistent schema.

    This keeps older `config/settings.json` files working after path and schema
    migrations without forcing manual edits first.
    """
    normalized = deepcopy(settings)

    logging_cfg = normalized.get("logging")
    if not isinstance(logging_cfg, dict):
        logging_cfg = {}
        normalized["logging"] = logging_cfg

    logging_cfg["log_file"] = _normalize_runtime_path_value(
        logging_cfg.get("log_file", DEFAULT_SETTINGS["logging"]["log_file"])
    )

    if "console_enabled" not in logging_cfg:
        logging_cfg["console_enabled"] = DEFAULT_SETTINGS["logging"]["console_enabled"]

    for section_name in ("voice_input", "voice_output", "llm"):
        section = normalized.get(section_name)
        if not isinstance(section, dict):
            continue

        for key, value in list(section.items()):
            if not isinstance(value, str):
                continue
            section[key] = _normalize_runtime_path_value(value)

        if section_name == "voice_output":
            piper_models = section.get("piper_models")
            if isinstance(piper_models, dict):
                for lang, model_info in list(piper_models.items()):
                    if not isinstance(model_info, dict):
                        continue
                    for inner_key in ("model", "config"):
                        model_info[inner_key] = _normalize_runtime_path_value(model_info.get(inner_key))

    return normalized


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
    global _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS

    with _SETTINGS_LOCK:
        _SETTINGS_CACHE = None
        _SETTINGS_CACHE_MTIME_NS = None


def load_settings(*, force_reload: bool = False) -> dict[str, Any]:
    """
    Load merged application settings.

    Merge order:
    1. DEFAULT_SETTINGS
    2. config/settings.json

    This keeps the product resilient when new settings are introduced
    but older config files still exist on disk.
    """
    global _SETTINGS_CACHE, _SETTINGS_CACHE_MTIME_NS

    ensure_runtime_directories()

    with _SETTINGS_LOCK:
        current_mtime_ns = _current_settings_mtime_ns(SETTINGS_PATH)

        cache_valid = (
            not force_reload
            and _SETTINGS_CACHE is not None
            and _SETTINGS_CACHE_MTIME_NS == current_mtime_ns
        )
        if cache_valid:
            return deepcopy(_SETTINGS_CACHE)

        file_settings = _read_raw_settings_file(SETTINGS_PATH)
        merged = _deep_merge_dicts(DEFAULT_SETTINGS, file_settings)
        normalized = _normalize_settings_payload(merged)

        _SETTINGS_CACHE = deepcopy(normalized)
        _SETTINGS_CACHE_MTIME_NS = current_mtime_ns
        return deepcopy(normalized)


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