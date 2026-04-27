from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AudioDeviceConfig:
    """Canonical audio device settings for realtime capture workers."""

    sample_rate: int = 16_000
    channels: int = 1
    blocksize: int = 512
    sample_width_bytes: int = 2
    device_index: int | None = None
    device_name_contains: str | None = None
    source_name: str = "microphone"

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be greater than zero")
        if self.channels <= 0:
            raise ValueError("channels must be greater than zero")
        if self.blocksize <= 0:
            raise ValueError("blocksize must be greater than zero")
        if self.sample_width_bytes <= 0:
            raise ValueError("sample_width_bytes must be greater than zero")
        if not self.source_name.strip():
            raise ValueError("source_name must not be empty")

    @property
    def block_duration_seconds(self) -> float:
        return self.blocksize / float(self.sample_rate)

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> AudioDeviceConfig:
        voice_input = settings.get("voice_input", settings)

        return cls(
            sample_rate=int(voice_input.get("sample_rate", 16_000)),
            channels=1,
            blocksize=int(voice_input.get("blocksize", 512)),
            sample_width_bytes=2,
            device_index=voice_input.get("device_index"),
            device_name_contains=voice_input.get("device_name_contains"),
            source_name=str(voice_input.get("device_name_contains") or "microphone"),
        )