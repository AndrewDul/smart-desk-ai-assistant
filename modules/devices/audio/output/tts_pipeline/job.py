from __future__ import annotations

import threading
from pathlib import Path


class _SynthesisJob:
    """One cached Piper synthesis request."""

    __slots__ = (
        "key",
        "text",
        "lang",
        "cache_path",
        "event",
        "success",
        "error",
        "priority",
        "version",
    )

    def __init__(
        self,
        *,
        key: tuple[str, str],
        text: str,
        lang: str,
        cache_path: Path,
        priority: int,
    ) -> None:
        self.key = key
        self.text = text
        self.lang = lang
        self.cache_path = cache_path
        self.event = threading.Event()
        self.success = False
        self.error = ""
        self.priority = int(priority)
        self.version = 0


__all__ = ["_SynthesisJob"]