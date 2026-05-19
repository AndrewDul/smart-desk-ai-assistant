from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StreamExecutionReport:
    chunks_spoken: int
    full_text: str
    display_title: str
    display_lines: list[str]
    chunk_count: int = 0
    first_audio_latency_ms: float = 0.0
    first_audio_ms: float = 0.0
    tts_first_audio_ms: float = 0.0
    first_chunk_latency_ms: float = 0.0
    llm_request_started: bool = False
    llm_first_token_ms: float = 0.0
    llm_first_content_chunk_ms: float = 0.0
    first_token_latency_ms: float = 0.0
    first_speakable_chunk_latency_ms: float = 0.0
    first_sentence_latency_ms: float = 0.0
    max_spoken_gap_ms: float = 0.0
    average_spoken_gap_ms: float = 0.0
    heartbeat_count: int = 0
    heartbeat_first_ms: float = 0.0
    heartbeat_cancelled: bool = False
    heartbeat_cancelled_reason: str = ""
    presence_skipped_reason_count: int = 0
    first_real_audio_after_tts_started_ms: float = 0.0
    first_chunk_chars: int = 0
    first_chunk_synthesis_ms: float = 0.0
    prepare_next_ms: float = 0.0
    total_elapsed_ms: float = 0.0
    total_response_ms: float = 0.0
    started_at_monotonic: float = 0.0
    first_audio_started_at_monotonic: float = 0.0
    first_chunk_started_at_monotonic: float = 0.0
    first_token_started_at_monotonic: float = 0.0
    first_speakable_chunk_started_at_monotonic: float = 0.0
    first_sentence_started_at_monotonic: float = 0.0
    finished_at_monotonic: float = 0.0
    chunk_kinds: list[str] = field(default_factory=list)
    live_streaming: bool = False


__all__ = ["StreamExecutionReport"]
