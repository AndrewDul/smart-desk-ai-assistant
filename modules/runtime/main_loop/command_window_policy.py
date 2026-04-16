from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from modules.shared.logging.logger import append_log

from .constants import (
    COMMAND_EMPTY_RETRY_LIMIT,
    COMMAND_IGNORE_RETRY_LIMIT,
    FOLLOW_UP_EMPTY_RETRY_LIMIT,
    FOLLOW_UP_IGNORE_RETRY_LIMIT,
    GRACE_EMPTY_RETRY_LIMIT,
    GRACE_IGNORE_RETRY_LIMIT,
    INITIAL_COMMAND_WINDOW_SECONDS,
    PHASE_COMMAND,
    PHASE_FOLLOW_UP,
    PHASE_GRACE,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


@dataclass(slots=True)
class CommandWindowDecision:
    action: str
    reason: str
    phase: str
    attempt_number: int
    retry_limit: int
    remaining_seconds: float
    retry_floor_seconds: float
    detail: str = ""
    window_seconds: float = 0.0


class CommandWindowPolicyService:
    """
    Decide how command windows should behave around active listening.

    Responsibilities:
    - resolve the initial command window duration after wake
    - decide whether empty or ignored active captures should retry or fall back
    - expose structured timing decisions for logging and tests
    """

    def initial_window_decision(self, assistant: CoreAssistant) -> CommandWindowDecision:
        seconds = self._initial_command_window_seconds(assistant)
        decision = CommandWindowDecision(
            action="open_initial",
            reason="wake_accepted",
            phase=PHASE_COMMAND,
            attempt_number=0,
            retry_limit=0,
            remaining_seconds=seconds,
            retry_floor_seconds=self._retry_floor_seconds(assistant),
            detail="awaiting_command_after_wake",
            window_seconds=seconds,
        )
        self._store_last_decision(assistant, decision)
        return decision

    def decide_after_empty_capture(
        self,
        assistant: CoreAssistant,
        *,
        phase: str,
        attempt_number: int,
        remaining_seconds: float,
    ) -> CommandWindowDecision:
        retry_limit, detail = self._empty_retry_profile(phase)
        return self._build_retry_decision(
            assistant,
            phase=phase,
            attempt_number=attempt_number,
            remaining_seconds=remaining_seconds,
            retry_limit=retry_limit,
            detail=detail,
            failure_reason=f"{phase}_window_expired",
            decision_kind="empty_capture",
        )

    def decide_after_ignored_transcript(
        self,
        assistant: CoreAssistant,
        *,
        phase: str,
        attempt_number: int,
        remaining_seconds: float,
    ) -> CommandWindowDecision:
        retry_limit, detail = self._ignored_retry_profile(phase)
        return self._build_retry_decision(
            assistant,
            phase=phase,
            attempt_number=attempt_number,
            remaining_seconds=remaining_seconds,
            retry_limit=retry_limit,
            detail=detail,
            failure_reason=f"{phase}_ignored_transcript",
            decision_kind="ignored_transcript",
        )

    def _build_retry_decision(
        self,
        assistant: CoreAssistant,
        *,
        phase: str,
        attempt_number: int,
        remaining_seconds: float,
        retry_limit: int,
        detail: str,
        failure_reason: str,
        decision_kind: str,
    ) -> CommandWindowDecision:
        retry_floor = self._retry_floor_seconds(assistant)
        normalized_remaining = max(0.0, float(remaining_seconds or 0.0))
        should_retry = normalized_remaining > retry_floor and int(attempt_number) <= int(retry_limit)

        decision = CommandWindowDecision(
            action="retry" if should_retry else "standby",
            reason=decision_kind if should_retry else failure_reason,
            phase=phase,
            attempt_number=int(attempt_number),
            retry_limit=int(retry_limit),
            remaining_seconds=normalized_remaining,
            retry_floor_seconds=retry_floor,
            detail=detail if should_retry else "",
        )
        self._store_last_decision(assistant, decision)
        return decision

    def _initial_command_window_seconds(self, assistant: CoreAssistant) -> float:
        voice_input_cfg = assistant.settings.get("voice_input", {})
        configured = voice_input_cfg.get("initial_command_window_seconds")
        if configured is not None:
            try:
                return max(2.0, float(configured))
            except (TypeError, ValueError):
                pass

        active_window_seconds = max(
            1.0,
            float(getattr(assistant.voice_session, "active_listen_window_seconds", 8.0)),
        )
        return max(6.0, min(active_window_seconds, INITIAL_COMMAND_WINDOW_SECONDS))

    def _retry_floor_seconds(self, assistant: CoreAssistant) -> float:
        voice_input_cfg = assistant.settings.get("voice_input", {})
        configured = voice_input_cfg.get("active_window_retry_min_remaining_seconds")
        if configured is not None:
            try:
                return max(0.1, float(configured))
            except (TypeError, ValueError):
                pass
        return 0.35

    def _empty_retry_profile(self, phase: str) -> tuple[int, str]:
        if phase == PHASE_FOLLOW_UP:
            return FOLLOW_UP_EMPTY_RETRY_LIMIT, "awaiting_followup_after_silence"
        if phase == PHASE_GRACE:
            return GRACE_EMPTY_RETRY_LIMIT, "grace_after_silence"
        return COMMAND_EMPTY_RETRY_LIMIT, "awaiting_command_after_silence"

    def _ignored_retry_profile(self, phase: str) -> tuple[int, str]:
        if phase == PHASE_FOLLOW_UP:
            return FOLLOW_UP_IGNORE_RETRY_LIMIT, f"{phase}_ignored_transcript"
        if phase == PHASE_GRACE:
            return GRACE_IGNORE_RETRY_LIMIT, f"{phase}_ignored_transcript"
        return COMMAND_IGNORE_RETRY_LIMIT, f"{phase}_ignored_transcript"

    def _store_last_decision(
        self,
        assistant: CoreAssistant,
        decision: CommandWindowDecision,
    ) -> None:
        assistant._last_command_window_policy_snapshot = {
            "action": decision.action,
            "reason": decision.reason,
            "phase": decision.phase,
            "attempt_number": decision.attempt_number,
            "retry_limit": decision.retry_limit,
            "remaining_seconds": decision.remaining_seconds,
            "retry_floor_seconds": decision.retry_floor_seconds,
            "detail": decision.detail,
            "window_seconds": decision.window_seconds,
        }
        append_log(
            "Command window policy decided: "
            f"action={decision.action}, "
            f"reason={decision.reason}, "
            f"phase={decision.phase}, "
            f"attempt={decision.attempt_number}/{decision.retry_limit}, "
            f"remaining={decision.remaining_seconds:.2f}, "
            f"retry_floor={decision.retry_floor_seconds:.2f}, "
            f"window_seconds={decision.window_seconds:.2f}"
        )


__all__ = ["CommandWindowDecision", "CommandWindowPolicyService"]