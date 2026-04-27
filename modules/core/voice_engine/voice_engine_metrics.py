from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class VoiceEngineMetrics:
    """Timing metrics for one Voice Engine v2 turn."""

    turn_started_monotonic: float
    speech_end_monotonic: float | None = None
    command_started_monotonic: float | None = None
    command_finished_monotonic: float | None = None
    resolver_started_monotonic: float | None = None
    resolver_finished_monotonic: float | None = None
    finished_monotonic: float | None = None
    fallback_used: bool = False
    fallback_reason: str = ""

    def __post_init__(self) -> None:
        if self.turn_started_monotonic < 0:
            raise ValueError("turn_started_monotonic must not be negative")
        if self.speech_end_monotonic is not None and self.speech_end_monotonic < 0:
            raise ValueError("speech_end_monotonic must not be negative")

    @property
    def command_recognition_ms(self) -> float | None:
        return self._duration_ms(
            self.command_started_monotonic,
            self.command_finished_monotonic,
        )

    @property
    def intent_resolution_ms(self) -> float | None:
        return self._duration_ms(
            self.resolver_started_monotonic,
            self.resolver_finished_monotonic,
        )

    @property
    def total_turn_ms(self) -> float | None:
        return self._duration_ms(
            self.turn_started_monotonic,
            self.finished_monotonic,
        )

    @property
    def speech_end_to_finish_ms(self) -> float | None:
        if self.speech_end_monotonic is None:
            return None
        return self._duration_ms(
            self.speech_end_monotonic,
            self.finished_monotonic,
        )

    def mark_command_started(self, timestamp_monotonic: float) -> None:
        self._validate_timestamp(timestamp_monotonic)
        self.command_started_monotonic = timestamp_monotonic

    def mark_command_finished(self, timestamp_monotonic: float) -> None:
        self._validate_timestamp(timestamp_monotonic)
        self.command_finished_monotonic = timestamp_monotonic

    def mark_resolver_started(self, timestamp_monotonic: float) -> None:
        self._validate_timestamp(timestamp_monotonic)
        self.resolver_started_monotonic = timestamp_monotonic

    def mark_resolver_finished(self, timestamp_monotonic: float) -> None:
        self._validate_timestamp(timestamp_monotonic)
        self.resolver_finished_monotonic = timestamp_monotonic

    def mark_finished(self, timestamp_monotonic: float) -> None:
        self._validate_timestamp(timestamp_monotonic)
        self.finished_monotonic = timestamp_monotonic

    def mark_fallback(self, reason: str) -> None:
        self.fallback_used = True
        self.fallback_reason = reason

    @staticmethod
    def _duration_ms(start: float | None, end: float | None) -> float | None:
        if start is None or end is None:
            return None
        return max(0.0, (end - start) * 1000.0)

    @staticmethod
    def _validate_timestamp(timestamp_monotonic: float) -> None:
        if timestamp_monotonic < 0:
            raise ValueError("timestamp_monotonic must not be negative")