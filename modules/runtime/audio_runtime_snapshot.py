from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AudioRuntimeSnapshot:
    state: str
    detail: str
    interaction_phase: str
    input_owner: str
    active_window_open: bool
    active_window_remaining_seconds: float
    active_window_generation: int
    state_age_seconds: float
    last_capture_handoff: dict[str, Any]
    last_resume_policy: dict[str, Any]
    last_command_window_policy: dict[str, Any]
    lines: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "detail": self.detail,
            "interaction_phase": self.interaction_phase,
            "input_owner": self.input_owner,
            "active_window_open": self.active_window_open,
            "active_window_remaining_seconds": self.active_window_remaining_seconds,
            "active_window_generation": self.active_window_generation,
            "state_age_seconds": self.state_age_seconds,
            "last_capture_handoff": dict(self.last_capture_handoff),
            "last_resume_policy": dict(self.last_resume_policy),
            "last_command_window_policy": dict(self.last_command_window_policy),
            "lines": list(self.lines),
        }


class AudioRuntimeSnapshotService:
    """
    Build a compact audio/session runtime snapshot for observability.

    Responsibilities:
    - expose current voice-session state
    - expose current active-window ownership and timing
    - expose last audio policy and handoff decisions
    - provide compact lines suitable for debug status or overlays
    """

    def __init__(self, *, voice_session: Any) -> None:
        self.voice_session = voice_session

    def snapshot(self, *, assistant: Any) -> dict[str, Any]:
        session_snapshot = self._voice_session_snapshot()

        state = str(getattr(session_snapshot, "state", "") or "unknown").strip().lower()
        detail = str(getattr(session_snapshot, "detail", "") or "").strip()
        interaction_phase = str(
            getattr(session_snapshot, "interaction_phase", "") or "unknown"
        ).strip().lower()
        input_owner = str(
            getattr(session_snapshot, "input_owner", "") or "unknown"
        ).strip().lower()
        active_window_open = bool(
            getattr(session_snapshot, "active_window_open", False)
        )
        active_window_remaining_seconds = self._safe_float(
            getattr(session_snapshot, "active_window_remaining_seconds", 0.0)
        )
        active_window_generation = self._safe_int(
            getattr(session_snapshot, "active_window_generation", 0)
        )
        state_age_seconds = self._safe_float(
            getattr(session_snapshot, "state_age_seconds", 0.0)
        )

        last_capture_handoff = dict(getattr(assistant, "_last_capture_handoff", {}) or {})
        last_resume_policy = dict(getattr(assistant, "_last_resume_policy_snapshot", {}) or {})
        last_command_window_policy = dict(
            getattr(assistant, "_last_command_window_policy_snapshot", {}) or {}
        )

        lines = (
            f"phase:{self._token(interaction_phase, 14)} owner:{self._token(input_owner, 14)}",
            f"resume:{self._token(last_resume_policy.get('action', 'n/a'), 10)} "
            f"cmd:{self._token(last_command_window_policy.get('action', 'n/a'), 10)}",
            f"handoff:{self._token(last_capture_handoff.get('applied_owner', 'n/a'), 14)}",
            f"win:{active_window_remaining_seconds:.2f}s state:{self._token(state, 12)}",
        )

        payload = AudioRuntimeSnapshot(
            state=state or "unknown",
            detail=detail,
            interaction_phase=interaction_phase or "unknown",
            input_owner=input_owner or "unknown",
            active_window_open=active_window_open,
            active_window_remaining_seconds=active_window_remaining_seconds,
            active_window_generation=active_window_generation,
            state_age_seconds=state_age_seconds,
            last_capture_handoff=last_capture_handoff,
            last_resume_policy=last_resume_policy,
            last_command_window_policy=last_command_window_policy,
            lines=lines,
        )
        return payload.to_dict()

    def _voice_session_snapshot(self) -> Any:
        snapshot_method = getattr(self.voice_session, "snapshot", None)
        if callable(snapshot_method):
            try:
                return snapshot_method()
            except Exception:
                return object()
        return object()

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _token(value: Any, max_chars: int) -> str:
        text = " ".join(str(value or "n/a").split()).strip().lower() or "n/a"
        if len(text) <= max_chars:
            return text
        return text[:max_chars]