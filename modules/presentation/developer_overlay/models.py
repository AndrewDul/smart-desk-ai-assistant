from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DeveloperOverlayPayload:
    """Compact idle overlay state rendered on the device for developer telemetry."""

    title: str
    lines: list[str] = field(default_factory=list)
    runtime_label: str = ""
    llm_label: str = ""
    benchmark_available: bool = False
    audio_available: bool = False
    audio_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "lines": list(self.lines),
            "runtime_label": self.runtime_label,
            "llm_label": self.llm_label,
            "benchmark_available": self.benchmark_available,
            "audio_available": self.audio_available,
            "audio_line": self.audio_line,
        }


__all__ = ["DeveloperOverlayPayload"]