# modules/devices/vision/perception/objects/hailo_runtime/errors.py
from __future__ import annotations


class HailoRuntimeError(RuntimeError):
    """Generic Hailo runtime error."""


class HailoUnavailableError(HailoRuntimeError):
    """
    Raised when the Hailo device or the hailo_platform module is not available.
    This is a recoverable condition — the caller should fall back to a null
    detector rather than crash the vision pipeline.
    """