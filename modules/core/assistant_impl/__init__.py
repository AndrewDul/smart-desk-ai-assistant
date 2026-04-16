from __future__ import annotations

__all__ = ["CoreAssistant"]


def __getattr__(name: str):
    if name == "CoreAssistant":
        from .core import CoreAssistant

        return CoreAssistant
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")