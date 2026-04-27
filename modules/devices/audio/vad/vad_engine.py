from __future__ import annotations

from typing import Protocol

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad.vad_events import VadDecision


class VadEngine(Protocol):
    """Protocol for VAD engines used by Voice Engine v2."""

    def score_frame(self, frame: AudioFrame) -> VadDecision:
        """Return a speech/silence decision for one audio frame."""

    def reset(self) -> None:
        """Reset any internal streaming state."""