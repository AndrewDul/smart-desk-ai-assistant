from __future__ import annotations

from collections.abc import Callable

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad.vad_engine import VadEngine
from modules.devices.audio.vad.vad_events import VadDecision

VadScoreProvider = Callable[[AudioFrame], float]


class SileroVadEngine(VadEngine):
    """Silero-compatible VAD adapter for Voice Engine v2.

    Stage 2 intentionally injects the scoring provider instead of importing
    torch or loading a real Silero model. This keeps the endpointing contract
    testable and prevents accidental changes to the current production audio
    runtime. The real model loader should be added only when Voice Engine v2
    integration starts behind the existing config gate.
    """

    def __init__(
        self,
        *,
        score_provider: VadScoreProvider,
        speech_threshold: float = 0.5,
    ) -> None:
        if not 0.0 <= speech_threshold <= 1.0:
            raise ValueError("speech_threshold must be between 0.0 and 1.0")

        self._score_provider = score_provider
        self._speech_threshold = speech_threshold

    @property
    def speech_threshold(self) -> float:
        return self._speech_threshold

    def score_frame(self, frame: AudioFrame) -> VadDecision:
        score = float(self._score_provider(frame))
        if not 0.0 <= score <= 1.0:
            raise ValueError("score_provider must return a value between 0.0 and 1.0")

        return VadDecision.from_score(
            frame=frame,
            score=score,
            threshold=self._speech_threshold,
        )

    def reset(self) -> None:
        return None