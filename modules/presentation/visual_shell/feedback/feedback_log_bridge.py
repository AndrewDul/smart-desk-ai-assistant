"""Feedback log bridge for the Visual Shell dashboard."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any


_ATTACHED_HANDLER: "FeedbackLogHandler | None" = None
_ATTACHED_LOGGERS: list[logging.Logger] = []


def _classify_record(record: logging.LogRecord) -> tuple[str, str]:
    name = str(record.name or "").lower()
    message = str(record.getMessage() or "").lower()
    text = f"{name} {message}"

    if any(token in text for token in ("vision", "camera", "detector", "perception", "capture")):
        return ("VISION", "camera / perception")
    if any(token in text for token in ("voice_engine", "speech_recognition", "command_asr", "faster_whisper", "vosk", "stt")):
        return ("STT", "speech / command recognition")
    if any(token in text for token in ("wake", "openwakeword")):
        return ("WAKE", "wake word detection")
    if any(token in text for token in ("tts", "piper", "voice_output", "speaker", "audio coordinator")):
        return ("AUDIO", "speech output / playback")
    if any(token in text for token in ("llm", "dialogue", "ollama", "qwen")):
        return ("LLM", "language model")
    if any(token in text for token in ("visual_shell", "display", "godot", "ui")):
        return ("UI", "visual shell / display")
    return ("SYSTEM", "runtime / orchestration")


class FeedbackLogHandler(logging.Handler):
    """Forward product log records to the Visual Shell feedback dashboard."""

    def __init__(self, controller: Any, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._controller = controller
        self._lock = threading.Lock()
        self._fail_count = 0
        self.setFormatter(logging.Formatter("%(name)s — %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record).replace("\n", " ⏎ ").strip()
        except Exception:
            return

        if not message:
            return

        if len(message) > 560:
            message = message[:557] + "..."

        component, responsibility = _classify_record(record)
        dashboard_message = f"{component} | {responsibility} | {message}"
        ts_ms = int(time.time() * 1000)

        try:
            with self._lock:
                self._controller.feedback_log_append(
                    level=str(record.levelname or "INFO").lower(),
                    message=dashboard_message,
                    ts_ms=ts_ms,
                    source="nexa-feedback-bridge",
                )
                self._fail_count = 0
        except Exception:
            self._fail_count += 1
            if self._fail_count >= 25:
                detach_feedback_log_handler()


def _candidate_loggers() -> list[logging.Logger]:
    loggers: list[logging.Logger] = []

    root_logger = logging.getLogger()
    loggers.append(root_logger)

    for name in ("nexa", "modules", "modules.shared", "modules.core", "modules.runtime", "modules.devices"):
        logger = logging.getLogger(name)
        if logger not in loggers:
            loggers.append(logger)

    try:
        from modules.shared.logging import logger as product_logger_module

        cache = getattr(product_logger_module, "_LOGGER_CACHE", {})
        if isinstance(cache, dict):
            for logger in cache.values():
                if isinstance(logger, logging.Logger) and logger not in loggers:
                    loggers.append(logger)
    except Exception:
        pass

    return loggers


def refresh_feedback_log_targets() -> None:
    if _ATTACHED_HANDLER is None:
        return

    for logger in _candidate_loggers():
        if _ATTACHED_HANDLER not in logger.handlers:
            logger.addHandler(_ATTACHED_HANDLER)
        if logger not in _ATTACHED_LOGGERS:
            _ATTACHED_LOGGERS.append(logger)


def attach_feedback_log_handler(controller: Any) -> FeedbackLogHandler:
    global _ATTACHED_HANDLER

    detach_feedback_log_handler()

    handler = FeedbackLogHandler(controller=controller, level=logging.INFO)
    _ATTACHED_HANDLER = handler
    refresh_feedback_log_targets()

    try:
        handler.emit(
            logging.LogRecord(
                name="nexa.feedback",
                level=logging.INFO,
                pathname=__file__,
                lineno=0,
                msg="Feedback log bridge attached to product loggers.",
                args=(),
                exc_info=None,
            )
        )
    except Exception:
        pass

    return handler


def detach_feedback_log_handler() -> None:
    global _ATTACHED_HANDLER
    global _ATTACHED_LOGGERS

    handler = _ATTACHED_HANDLER
    if handler is None:
        return

    for logger in list(_ATTACHED_LOGGERS):
        try:
            if handler in logger.handlers:
                logger.removeHandler(handler)
        except Exception:
            pass

    _ATTACHED_LOGGERS = []
    _ATTACHED_HANDLER = None


__all__ = [
    "FeedbackLogHandler",
    "attach_feedback_log_handler",
    "detach_feedback_log_handler",
    "refresh_feedback_log_targets",
]
