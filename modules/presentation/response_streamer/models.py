from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StreamExecutionReport:
    chunks_spoken: int
    full_text: str
    display_title: str
    display_lines: list[str]


__all__ = ["StreamExecutionReport"]