from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StreamExecutionReport:
    chunks_spoken: int
    full_text: str
    display_title: str
    display_lines: list[str]
    first_audio_latency_ms: float = 0.0
    total_elapsed_ms: float = 0.0
    started_at_monotonic: float = 0.0
    first_audio_started_at_monotonic: float = 0.0
    finished_at_monotonic: float = 0.0
    chunk_kinds: list[str] = field(default_factory=list)
    live_streaming: bool = False


__all__ = ["StreamExecutionReport"]