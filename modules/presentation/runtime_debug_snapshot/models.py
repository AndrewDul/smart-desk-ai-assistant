from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeDebugSnapshotPayload:
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    benchmark_snapshot: dict[str, Any] = field(default_factory=dict)
    audio_runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    ai_broker_snapshot: dict[str, Any] = field(default_factory=dict)
    runtime_label: str = ""
    llm_label: str = ""
    wake_backend: str = "n/a"
    stt_backend: str = "n/a"
    llm_backend: str = "n/a"
    last_turn_ms: float | None = None
    avg_response_first_audio_ms: float | None = None
    avg_llm_first_chunk_ms: float | None = None
    completed_turn_trace: dict[str, Any] = field(default_factory=dict)
    completed_turn_lines: list[str] = field(default_factory=list)
    audio_lines: list[str] = field(default_factory=list)
    audio_overlay_line: str = ""
    ai_broker_line: str = ""
    developer_overlay_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["RuntimeDebugSnapshotPayload"]