from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from modules.shared.config.settings import get_setting, resolve_settings_path
from modules.shared.persistence.paths import SYSTEM_LOG_PATH, ensure_runtime_directories

_LOGGER_LOCK = threading.RLock()
_LOGGER_CACHE: dict[str, logging.Logger] = {}
_LOGGER_SIGNATURES: dict[str, tuple[str, int, int, bool]] = {}


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _logging_enabled() -> bool:
    return _safe_bool(get_setting("logging.enabled", True), True)


def _console_logging_enabled() -> bool:
    return _safe_bool(get_setting("logging.console_enabled", False), False)


def _configured_log_path() -> Path:
    configured = get_setting("logging.log_file", str(SYSTEM_LOG_PATH))
    resolved = resolve_settings_path(configured)
    if resolved is None:
        return SYSTEM_LOG_PATH
    return resolved


def _configured_max_bytes() -> int:
    return max(0, _safe_int(get_setting("logging.max_bytes", 1_000_000), 1_000_000))


def _configured_backup_count() -> int:
    return max(0, _safe_int(get_setting("logging.backup_count", 2), 2))


def _logger_signature(log_path: Path, max_bytes: int, backup_count: int, console_enabled: bool) -> tuple[str, int, int, bool]:
    return (str(log_path.resolve()), max_bytes, backup_count, console_enabled)


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_file_handler(log_path: Path, max_bytes: int, backup_count: int) -> RotatingFileHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    return RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )


def _remove_all_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _configure_logger(logger_name: str) -> logging.Logger:
    ensure_runtime_directories()

    log_path = _configured_log_path()
    max_bytes = _configured_max_bytes()
    backup_count = _configured_backup_count()
    console_enabled = _console_logging_enabled()

    signature = _logger_signature(
        log_path=log_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
        console_enabled=console_enabled,
    )

    logger = _LOGGER_CACHE.get(logger_name)
    if logger is None:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _LOGGER_CACHE[logger_name] = logger

    if _LOGGER_SIGNATURES.get(logger_name) == signature and logger.handlers:
        return logger

    _remove_all_handlers(logger)

    formatter = _build_formatter()

    file_handler = _build_file_handler(
        log_path=log_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console_enabled:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    _LOGGER_SIGNATURES[logger_name] = signature
    return logger


def get_logger(name: str = "nexa") -> logging.Logger:
    """
    Return a configured product logger.

    I keep configuration lazy so the logger can safely be imported
    from low-level modules without forcing a heavy startup sequence.
    """
    with _LOGGER_LOCK:
        return _configure_logger(name)


def reset_logger_cache() -> None:
    """
    Clear cached logger configuration.

    Call this after changing logging settings at runtime.
    """
    with _LOGGER_LOCK:
        for logger in _LOGGER_CACHE.values():
            _remove_all_handlers(logger)

        _LOGGER_CACHE.clear()
        _LOGGER_SIGNATURES.clear()


def append_log(message: str, *, logger_name: str = "nexa") -> None:
    """
    Compatibility helper for the current codebase.

    This keeps the existing call style:
        append_log("Wake phrase detected.")

    while the project migrates toward structured logger usage.
    """
    if not _logging_enabled():
        return

    try:
        logger = get_logger(logger_name)
        logger.info(str(message))
    except Exception:
        # Logging must never crash the product.
        pass


def log_warning(message: str, *, logger_name: str = "nexa") -> None:
    if not _logging_enabled():
        return

    try:
        logger = get_logger(logger_name)
        logger.warning(str(message))
    except Exception:
        pass


def log_error(message: str, *, logger_name: str = "nexa") -> None:
    if not _logging_enabled():
        return

    try:
        logger = get_logger(logger_name)
        logger.error(str(message))
    except Exception:
        pass


def log_exception(
    message: str,
    exception: BaseException,
    *,
    logger_name: str = "nexa",
) -> None:
    if not _logging_enabled():
        return

    try:
        logger = get_logger(logger_name)
        logger.error("%s | %s: %s", str(message), exception.__class__.__name__, str(exception))
    except Exception:
        pass


__all__ = [
    "append_log",
    "get_logger",
    "log_error",
    "log_exception",
    "log_warning",
    "reset_logger_cache",
]