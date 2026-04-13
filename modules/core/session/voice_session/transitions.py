from __future__ import annotations

import time

from .constants import (
    VOICE_INPUT_OWNER_ASSISTANT_OUTPUT,
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_PHASE_COMMAND,
    VOICE_PHASE_ROUTE,
    VOICE_PHASE_SHUTDOWN,
    VOICE_PHASE_SPEAK,
    VOICE_PHASE_THINK,
    VOICE_PHASE_TRANSCRIBE,
    VOICE_PHASE_WAKE_ACK,
    VOICE_PHASE_WAKE_GATE,
    VOICE_STATE_LISTENING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_THINKING,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_WAKE_DETECTED,
)


class VoiceSessionTransitions:
    """High-level transitions for the NeXa voice session state machine."""

    _lock: object
    _snapshot: object

    def transition_to_standby(
        self,
        *,
        detail: str = "waiting_for_wake",
        phase: str = VOICE_PHASE_WAKE_GATE,
        input_owner: str = VOICE_INPUT_OWNER_WAKE_GATE,
        close_active_window: bool = False,
    ) -> None:
        with self._lock:
            if close_active_window:
                self._snapshot.active_until_monotonic = 0.0
            self._snapshot.state = VOICE_STATE_STANDBY
            self._snapshot.detail = str(detail or "waiting_for_wake").strip()
            self._snapshot.interaction_phase = self._normalize_phase(phase)
            self._snapshot.input_owner = self._normalize_input_owner(input_owner)
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def transition_to_wake_detected(self, *, detail: str = "wake_phrase_detected") -> None:
        with self._lock:
            now = time.monotonic()
            self._snapshot.state = VOICE_STATE_WAKE_DETECTED
            self._snapshot.detail = str(detail or "wake_phrase_detected").strip()
            self._snapshot.interaction_phase = VOICE_PHASE_WAKE_ACK
            self._snapshot.input_owner = VOICE_INPUT_OWNER_ASSISTANT_OUTPUT
            self._snapshot.last_state_change_monotonic = now
            self._snapshot.last_wake_detected_monotonic = now

    def transition_to_listening(
        self,
        *,
        detail: str,
        phase: str = VOICE_PHASE_COMMAND,
        input_owner: str = VOICE_INPUT_OWNER_VOICE_INPUT,
    ) -> None:
        with self._lock:
            self._snapshot.state = VOICE_STATE_LISTENING
            self._snapshot.detail = str(detail or "listening").strip()
            self._snapshot.interaction_phase = self._normalize_phase(phase)
            self._snapshot.input_owner = self._normalize_input_owner(input_owner)
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def transition_to_transcribing(
        self,
        *,
        detail: str = "speech_captured",
        phase: str = VOICE_PHASE_TRANSCRIBE,
    ) -> None:
        with self._lock:
            self._snapshot.state = VOICE_STATE_TRANSCRIBING
            self._snapshot.detail = str(detail or "speech_captured").strip()
            self._snapshot.interaction_phase = self._normalize_phase(phase)
            self._snapshot.input_owner = VOICE_INPUT_OWNER_NONE
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def transition_to_routing(self, *, detail: str = "route_command") -> None:
        with self._lock:
            self._snapshot.state = VOICE_STATE_ROUTING
            self._snapshot.detail = str(detail or "route_command").strip()
            self._snapshot.interaction_phase = VOICE_PHASE_ROUTE
            self._snapshot.input_owner = VOICE_INPUT_OWNER_NONE
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def transition_to_thinking(self, *, detail: str = "thinking") -> None:
        with self._lock:
            self._snapshot.state = VOICE_STATE_THINKING
            self._snapshot.detail = str(detail or "thinking").strip()
            self._snapshot.interaction_phase = VOICE_PHASE_THINK
            self._snapshot.input_owner = VOICE_INPUT_OWNER_ASSISTANT_OUTPUT
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def transition_to_speaking(
        self,
        *,
        detail: str = "response",
        phase: str = VOICE_PHASE_SPEAK,
    ) -> None:
        with self._lock:
            now = time.monotonic()
            self._snapshot.state = VOICE_STATE_SPEAKING
            self._snapshot.detail = str(detail or "response").strip()
            self._snapshot.interaction_phase = self._normalize_phase(phase)
            self._snapshot.input_owner = VOICE_INPUT_OWNER_ASSISTANT_OUTPUT
            self._snapshot.last_state_change_monotonic = now
            self._snapshot.last_response_started_monotonic = now

    def transition_to_shutdown(self, *, detail: str = "assistant_shutdown") -> None:
        with self._lock:
            self._snapshot.active_until_monotonic = 0.0
            self._snapshot.state = VOICE_STATE_SHUTDOWN
            self._snapshot.detail = str(detail or "assistant_shutdown").strip()
            self._snapshot.interaction_phase = VOICE_PHASE_SHUTDOWN
            self._snapshot.input_owner = VOICE_INPUT_OWNER_NONE
            self._snapshot.last_state_change_monotonic = time.monotonic()

    def mark_response_finished(
        self,
        *,
        detail: str = "response_complete",
        return_to_standby: bool = True,
    ) -> None:
        with self._lock:
            now = time.monotonic()
            self._snapshot.last_response_finished_monotonic = now
            self._snapshot.input_owner = VOICE_INPUT_OWNER_NONE
            if return_to_standby:
                self._snapshot.state = VOICE_STATE_STANDBY
                self._snapshot.detail = str(detail or "response_complete").strip()
                self._snapshot.last_state_change_monotonic = now

    def mark_interrupt_requested(self, *, detail: str = "interrupt_requested") -> None:
        with self._lock:
            self._snapshot.last_interrupt_requested_monotonic = time.monotonic()
            self._snapshot.detail = str(detail or "interrupt_requested").strip()

    def set_input_owner(self, input_owner: str) -> None:
        with self._lock:
            self._snapshot.input_owner = self._normalize_input_owner(input_owner)

    def input_owner(self) -> str:
        with self._lock:
            return self._snapshot.input_owner

    def interaction_phase(self) -> str:
        with self._lock:
            return self._snapshot.interaction_phase