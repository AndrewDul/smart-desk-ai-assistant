from __future__ import annotations

import time

from .constants import (
    VOICE_STATE_LISTENING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_THINKING,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_WAKE_DETECTED,
    _VALID_STATES,
)
from .models import VoiceSessionSnapshot


class VoiceSessionState:
    """State and active-window helpers for the voice session."""

    active_listen_window_seconds: float
    _lock: object
    _snapshot: VoiceSessionSnapshot

    @property
    def state(self) -> str:
        with self._lock:
            return self._snapshot.state

    @property
    def state_detail(self) -> str:
        with self._lock:
            return self._snapshot.detail

    def snapshot(self) -> VoiceSessionSnapshot:
        with self._lock:
            return VoiceSessionSnapshot(
                state=self._snapshot.state,
                active_until_monotonic=self._snapshot.active_until_monotonic,
                last_state_change_monotonic=self._snapshot.last_state_change_monotonic,
                detail=self._snapshot.detail,
                last_wake_detected_monotonic=self._snapshot.last_wake_detected_monotonic,
                last_command_accepted_monotonic=self._snapshot.last_command_accepted_monotonic,
                active_window_generation=self._snapshot.active_window_generation,
            )

    def set_state(self, state: str, detail: str = "") -> None:
        normalized_state = str(state or "").strip().lower()
        if normalized_state not in _VALID_STATES:
            normalized_state = VOICE_STATE_STANDBY

        with self._lock:
            self._snapshot.state = normalized_state
            self._snapshot.detail = str(detail or "").strip()
            self._snapshot.last_state_change_monotonic = time.monotonic()

            if normalized_state == VOICE_STATE_WAKE_DETECTED:
                self._snapshot.last_wake_detected_monotonic = self._snapshot.last_state_change_monotonic

    def state_age_seconds(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self._snapshot.last_state_change_monotonic)

    def open_active_window(self, *, seconds: float | None = None) -> None:
        duration = self._resolve_window_seconds(seconds)
        now = time.monotonic()
        with self._lock:
            self._snapshot.active_until_monotonic = now + duration
            self._snapshot.active_window_generation += 1
            self._snapshot.state = VOICE_STATE_LISTENING
            self._snapshot.detail = "active_window_open"
            self._snapshot.last_state_change_monotonic = now

    def extend_active_window(self, *, seconds: float | None = None) -> None:
        duration = self._resolve_window_seconds(seconds)
        with self._lock:
            now = time.monotonic()
            current_deadline = max(self._snapshot.active_until_monotonic, now)
            self._snapshot.active_until_monotonic = current_deadline + duration

    def shorten_active_window(self, *, seconds: float) -> None:
        safe_seconds = max(float(seconds), 0.0)
        with self._lock:
            if self._snapshot.active_until_monotonic <= 0.0:
                return
            now = time.monotonic()
            target_deadline = now + safe_seconds
            self._snapshot.active_until_monotonic = min(
                self._snapshot.active_until_monotonic,
                target_deadline,
            )

    def close_active_window(self) -> None:
        with self._lock:
            self._snapshot.active_until_monotonic = 0.0
            self._snapshot.state = VOICE_STATE_STANDBY
            self._snapshot.detail = "active_window_closed"
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def active_window_open(self) -> bool:
        return self.active_window_remaining_seconds() > 0.0

    def active_window_remaining_seconds(self) -> float:
        with self._lock:
            remaining = self._snapshot.active_until_monotonic - time.monotonic()
            return max(0.0, remaining)

    def has_meaningful_active_window(self, *, minimum_seconds: float = 0.35) -> bool:
        return self.active_window_remaining_seconds() > max(0.0, float(minimum_seconds))

    def note_command_accepted(self) -> None:
        with self._lock:
            self._snapshot.last_command_accepted_monotonic = time.monotonic()

    def is_standby(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_STANDBY

    def is_listening(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_LISTENING

    def is_speaking(self) -> bool:
        with self._lock:
            return self._snapshot.state == VOICE_STATE_SPEAKING

    def is_busy(self) -> bool:
        with self._lock:
            return self._snapshot.state in {
                VOICE_STATE_WAKE_DETECTED,
                VOICE_STATE_LISTENING,
                VOICE_STATE_TRANSCRIBING,
                VOICE_STATE_ROUTING,
                VOICE_STATE_THINKING,
                VOICE_STATE_SPEAKING,
            }

    def _resolve_window_seconds(self, seconds: float | None) -> float:
        value = self.active_listen_window_seconds if seconds is None else float(seconds)
        return max(1.0, value)


__all__ = ["VoiceSessionState"]