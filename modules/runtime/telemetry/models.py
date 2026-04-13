from __future__ import annotations

from dataclasses import asdict, dataclass
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
    wake_backend: str = ""
    wake_latency_ms: float | None = None
    active_phase: str = ""
    route_kind: str = ""
    primary_intent: str = ""
    route_confidence: float = 0.0
    stt_backend: str = ""
    stt_mode: str = ""
    stt_latency_ms: float | None = None
    speech_duration_ms: float | None = None
    stt_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TurnBenchmarkSummary:
    sample_count: int = 0
    window_size: int = 0
    avg_total_turn_ms: float | None = None
    avg_response_first_audio_ms: float | None = None
    avg_response_first_chunk_ms: float | None = None
    avg_response_first_sentence_ms: float | None = None
    avg_route_to_first_audio_ms: float | None = None
    avg_llm_first_chunk_ms: float | None = None
    avg_llm_total_ms: float | None = None
    last_turn_id: str = ""
    last_result: str = ""
    last_total_turn_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "TurnBenchmarkSummary",
    "TurnBenchmarkTrace",
]