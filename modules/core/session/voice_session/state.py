from __future__ import annotations

import time

from .constants import (
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_PHASE_COMMAND,
    VOICE_PHASE_WAKE_GATE,
    VOICE_STATE_LISTENING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_THINKING,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_WAKE_DETECTED,
    _VALID_INPUT_OWNERS,
    _VALID_PHASES,
    _VALID_STATES,
)
from .models import VoiceSessionSnapshot


class VoiceSessionState:
    """State, ownership, and active-window helpers for the voice session."""

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
                interaction_phase=self._snapshot.interaction_phase,
                input_owner=self._snapshot.input_owner,
                last_response_started_monotonic=self._snapshot.last_response_started_monotonic,
                last_response_finished_monotonic=self._snapshot.last_response_finished_monotonic,
                last_interrupt_requested_monotonic=self._snapshot.last_interrupt_requested_monotonic,
            )

    def set_state(self, state: str, detail: str = "") -> None:
        normalized_state = self._normalize_state(state)

        with self._lock:
            self._snapshot.state = normalized_state
            self._snapshot.detail = str(detail or "").strip()
            self._snapshot.last_state_change_monotonic = time.monotonic()

            if normalized_state == VOICE_STATE_WAKE_DETECTED:
                self._snapshot.last_wake_detected_monotonic = self._snapshot.last_state_change_monotonic
            elif normalized_state == VOICE_STATE_SPEAKING:
                self._snapshot.last_response_started_monotonic = self._snapshot.last_state_change_monotonic
            elif normalized_state == VOICE_STATE_STANDBY:
                self._snapshot.last_response_finished_monotonic = self._snapshot.last_state_change_monotonic

    def state_age_seconds(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self._snapshot.last_state_change_monotonic)

    def open_active_window(
        self,
        *,
        seconds: float | None = None,
        phase: str | None = None,
        input_owner: str | None = None,
        detail: str = "active_window_open",
    ) -> None:
        duration = self._resolve_window_seconds(seconds)
        now = time.monotonic()
        with self._lock:
            self._snapshot.active_until_monotonic = now + duration
            self._snapshot.active_window_generation += 1
            self._snapshot.state = VOICE_STATE_LISTENING
            self._snapshot.detail = str(detail or "active_window_open").strip()
            self._snapshot.last_state_change_monotonic = now
            if phase is not None:
                self._snapshot.interaction_phase = self._normalize_phase(phase)
            if input_owner is not None:
                self._snapshot.input_owner = self._normalize_input_owner(input_owner)

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

    def close_active_window(
        self,
        *,
        detail: str = "active_window_closed",
        phase: str = VOICE_PHASE_WAKE_GATE,
        input_owner: str = VOICE_INPUT_OWNER_WAKE_GATE,
    ) -> None:
        with self._lock:
            self._snapshot.active_until_monotonic = 0.0
            self._snapshot.state = VOICE_STATE_STANDBY
            self._snapshot.detail = str(detail or "active_window_closed").strip()
            self._snapshot.last_state_change_monotonic = time.monotonic()
            self._snapshot.interaction_phase = self._normalize_phase(phase)
            self._snapshot.input_owner = self._normalize_input_owner(input_owner)

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

    @staticmethod
    def _normalize_state(state: str | None) -> str:
        normalized_state = str(state or "").strip().lower()
        if normalized_state not in _VALID_STATES:
            return VOICE_STATE_STANDBY
        return normalized_state

    @staticmethod
    def _normalize_phase(phase: str | None) -> str:
        normalized_phase = str(phase or "").strip().lower()
        if normalized_phase not in _VALID_PHASES:
            return VOICE_PHASE_COMMAND
        return normalized_phase

    @staticmethod
    def _normalize_input_owner(input_owner: str | None) -> str:
        normalized_owner = str(input_owner or "").strip().lower()
        if normalized_owner not in _VALID_INPUT_OWNERS:
            return VOICE_INPUT_OWNER_NONE
        return normalized_owner


__all__ = ["VoiceSessionState"]