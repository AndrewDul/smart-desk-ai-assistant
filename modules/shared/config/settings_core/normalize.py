from __future__ import annotations

from copy import deepcopy
from typing import Any

from .defaults import DEFAULT_SETTINGS

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
                for _, model_info in list(piper_models.items()):
                    if not isinstance(model_info, dict):
                        continue
                    for inner_key in ("model", "config"):
                        model_info[inner_key] = _normalize_runtime_path_value(model_info.get(inner_key))

    return normalized


__all__ = [
    "_deep_merge_dicts",
    "_normalize_runtime_path_value",
    "_normalize_settings_payload",
]