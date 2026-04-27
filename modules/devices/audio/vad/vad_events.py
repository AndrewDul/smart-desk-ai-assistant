from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.devices.audio.realtime.audio_frame import AudioFrame


class VadEventType(str, Enum):
    """High-level VAD events consumed by Voice Engine v2."""

    SPEECH_STARTED = "speech_started"
    SPEECH_CONTINUED = "speech_continued"
    SPEECH_ENDED = "speech_ended"
    SILENCE = "silence"


@dataclass(frozen=True, slots=True)
class VadDecision:
    """Frame-level VAD decision produced by a VAD engine."""

    is_speech: bool
    score: float
    threshold: float
    timestamp_monotonic: float
    frame_sequence: int
    frame_duration_seconds: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        if self.timestamp_monotonic < 0:
            raise ValueError("timestamp_monotonic must not be negative")
        if self.frame_sequence < 0:
            raise ValueError("frame_sequence must not be negative")
        if self.frame_duration_seconds <= 0:
            raise ValueError("frame_duration_seconds must be greater than zero")

    @classmethod
    def from_score(
        cls,
        *,
        frame: AudioFrame,
        score: float,
        threshold: float,
    ) -> VadDecision:
        return cls(
            is_speech=score >= threshold,
            score=score,
            threshold=threshold,
            timestamp_monotonic=frame.timestamp_monotonic,
            frame_sequence=frame.sequence,
            frame_duration_seconds=frame.duration_seconds,
        )


@dataclass(frozen=True, slots=True)
class VadEvent:
    """Endpointing event emitted from a stream of VAD decisions."""

    event_type: VadEventType
    timestamp_monotonic: float
    frame_sequence: int
    speech_start_timestamp: float | None = None
    speech_end_timestamp: float | None = None
    speech_duration_seconds: float = 0.0
    silence_duration_seconds: float = 0.0
    score: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp_monotonic < 0:
            raise ValueError("timestamp_monotonic must not be negative")
        if self.frame_sequence < 0:
            raise ValueError("frame_sequence must not be negative")
        if self.speech_duration_seconds < 0:
            raise ValueError("speech_duration_seconds must not be negative")
        if self.silence_duration_seconds < 0:
            raise ValueError("silence_duration_seconds must not be negative")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")