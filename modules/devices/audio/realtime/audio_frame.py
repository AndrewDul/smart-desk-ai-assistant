from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """Immutable PCM audio frame shared by realtime voice components."""

    pcm: bytes
    sample_rate: int
    channels: int
    sample_width_bytes: int
    timestamp_monotonic: float
    sequence: int
    source: str = "unknown"

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be greater than zero")
        if self.channels <= 0:
            raise ValueError("channels must be greater than zero")
        if self.sample_width_bytes <= 0:
            raise ValueError("sample_width_bytes must be greater than zero")
        if self.timestamp_monotonic < 0:
            raise ValueError("timestamp_monotonic must not be negative")
        if self.sequence < 0:
            raise ValueError("sequence must not be negative")

        frame_width = self.channels * self.sample_width_bytes
        if len(self.pcm) % frame_width != 0:
            raise ValueError(
                "pcm length must be aligned to channels * sample_width_bytes"
            )

    @property
    def frame_width_bytes(self) -> int:
        return self.channels * self.sample_width_bytes

    @property
    def sample_count(self) -> int:
        return len(self.pcm) // self.frame_width_bytes

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / float(self.sample_rate)

    @property
    def byte_count(self) -> int:
        return len(self.pcm)

    def with_sequence(self, sequence: int) -> AudioFrame:
        return replace(self, sequence=sequence)

    def with_source(self, source: str) -> AudioFrame:
        return replace(self, source=source)