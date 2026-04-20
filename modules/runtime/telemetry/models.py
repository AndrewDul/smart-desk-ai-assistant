from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TurnBenchmarkTrace:
    turn_id: str = ""
    turn_started_at_monotonic: float = 0.0
    wake_detected_at_monotonic: float = 0.0
    listening_started_at_monotonic: float = 0.0
    speech_finalized_at_monotonic: float = 0.0
    route_resolved_at_monotonic: float = 0.0
    user_text: str = ""
    input_source: str = "voice"
    language: str = ""
    wake_source: str = ""
    wake_input_source: str = "voice"
    wake_latency_ms: float = 0.0
    wake_backend_label: str = ""
    wake_ack_latency_ms: float = 0.0
    wake_ack_text: str = ""
    wake_ack_strategy: str = ""
    wake_ack_output_hold_seconds: float = 0.0
    speech_input_source: str = "voice"
    speech_language: str = ""
    speech_latency_ms: float = 0.0
    speech_audio_duration_ms: float = 0.0
    speech_backend_label: str = ""
    speech_mode: str = ""
    speech_confidence: float = 0.0
    active_phase: str = ""
    route_kind: str = ""
    primary_intent: str = ""
    route_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TurnBenchmarkSummary:
    sample_count: int = 0
    window_size: int = 0
    avg_total_turn_ms: float | None = None
    avg_response_first_audio_ms: float | None = None
    avg_route_to_first_audio_ms: float | None = None
    avg_llm_first_chunk_ms: float | None = None
    avg_llm_total_ms: float | None = None
    last_turn_id: str = ""
    last_result: str = ""
    last_total_turn_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TurnBenchmarkSnapshot:
    latest_sample: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    overlay_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "TurnBenchmarkSnapshot",
    "TurnBenchmarkSummary",
    "TurnBenchmarkTrace",
]