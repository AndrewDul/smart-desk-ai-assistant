from __future__ import annotations

from dataclasses import dataclass

from modules.devices.audio.vad.vad_events import (
    VadDecision,
    VadEvent,
    VadEventType,
)


@dataclass(frozen=True, slots=True)
class EndpointingPolicyConfig:
    """Timing policy for speech start/end detection."""

    min_speech_ms: int = 120
    min_silence_ms: int = 250
    emit_continued_events: bool = False

    def __post_init__(self) -> None:
        if self.min_speech_ms <= 0:
            raise ValueError("min_speech_ms must be greater than zero")
        if self.min_silence_ms <= 0:
            raise ValueError("min_silence_ms must be greater than zero")

    @property
    def min_speech_seconds(self) -> float:
        return self.min_speech_ms / 1000.0

    @property
    def min_silence_seconds(self) -> float:
        return self.min_silence_ms / 1000.0


class EndpointingPolicy:
    """Stateful VAD endpointing policy for Voice Engine v2."""

    def __init__(self, config: EndpointingPolicyConfig | None = None) -> None:
        self._config = config or EndpointingPolicyConfig()
        self.reset()

    @property
    def config(self) -> EndpointingPolicyConfig:
        return self._config

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    @property
    def speech_start_timestamp(self) -> float | None:
        return self._speech_start_timestamp

    def reset(self) -> None:
        self._in_speech = False
        self._candidate_speech_start_timestamp: float | None = None
        self._candidate_speech_duration_seconds = 0.0
        self._speech_start_timestamp: float | None = None
        self._last_speech_timestamp: float | None = None
        self._silence_start_timestamp: float | None = None
        self._silence_duration_seconds = 0.0

    def process(self, decision: VadDecision) -> list[VadEvent]:
        if decision.is_speech:
            return self._process_speech(decision)
        return self._process_silence(decision)

    def _process_speech(self, decision: VadDecision) -> list[VadEvent]:
        self._silence_start_timestamp = None
        self._silence_duration_seconds = 0.0
        self._last_speech_timestamp = decision.timestamp_monotonic

        if self._in_speech:
            if not self._config.emit_continued_events:
                return []

            return [
                VadEvent(
                    event_type=VadEventType.SPEECH_CONTINUED,
                    timestamp_monotonic=decision.timestamp_monotonic,
                    frame_sequence=decision.frame_sequence,
                    speech_start_timestamp=self._speech_start_timestamp,
                    speech_duration_seconds=self._speech_duration_until(decision),
                    score=decision.score,
                )
            ]

        if self._candidate_speech_start_timestamp is None:
            self._candidate_speech_start_timestamp = decision.timestamp_monotonic
            self._candidate_speech_duration_seconds = 0.0

        self._candidate_speech_duration_seconds += decision.frame_duration_seconds

        if (
            self._candidate_speech_duration_seconds
            < self._config.min_speech_seconds
        ):
            return []

        self._in_speech = True
        self._speech_start_timestamp = self._candidate_speech_start_timestamp

        return [
            VadEvent(
                event_type=VadEventType.SPEECH_STARTED,
                timestamp_monotonic=decision.timestamp_monotonic,
                frame_sequence=decision.frame_sequence,
                speech_start_timestamp=self._speech_start_timestamp,
                speech_duration_seconds=self._candidate_speech_duration_seconds,
                score=decision.score,
            )
        ]

    def _process_silence(self, decision: VadDecision) -> list[VadEvent]:
        self._candidate_speech_start_timestamp = None
        self._candidate_speech_duration_seconds = 0.0

        if not self._in_speech:
            return []

        if self._silence_start_timestamp is None:
            self._silence_start_timestamp = decision.timestamp_monotonic
            self._silence_duration_seconds = 0.0

        self._silence_duration_seconds += decision.frame_duration_seconds

        if self._silence_duration_seconds < self._config.min_silence_seconds:
            return []

        speech_start = self._speech_start_timestamp
        speech_end = self._last_speech_timestamp or decision.timestamp_monotonic
        speech_duration = (
            0.0 if speech_start is None else max(0.0, speech_end - speech_start)
        )

        event = VadEvent(
            event_type=VadEventType.SPEECH_ENDED,
            timestamp_monotonic=decision.timestamp_monotonic,
            frame_sequence=decision.frame_sequence,
            speech_start_timestamp=speech_start,
            speech_end_timestamp=speech_end,
            speech_duration_seconds=speech_duration,
            silence_duration_seconds=self._silence_duration_seconds,
            score=decision.score,
        )

        self.reset()

        return [event]

    def _speech_duration_until(self, decision: VadDecision) -> float:
        if self._speech_start_timestamp is None:
            return 0.0
        return max(
            0.0,
            decision.timestamp_monotonic - self._speech_start_timestamp,
        )