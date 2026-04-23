from __future__ import annotations

import threading
import time
from typing import Any, Mapping

from modules.shared.logging.logger import get_logger

from .models import AiBrokerMode, AiBrokerOwner, AiBrokerSnapshot, AiLaneProfile

LOGGER = get_logger(__name__)

_DEFAULT_RECOVERY_WINDOW_SECONDS = 1.5

_DEFAULT_PROFILES: dict[AiBrokerMode, AiLaneProfile] = {
    AiBrokerMode.IDLE_BASELINE: AiLaneProfile(
        heavy_lane_cadence_hz=2.0,
        keep_fast_lane_alive=True,
        llm_priority="normal",
        notes=("cheap_fast_lane_alive", "balanced_idle_policy"),
    ),
    AiBrokerMode.CONVERSATION_ANSWER: AiLaneProfile(
        heavy_lane_cadence_hz=0.5,
        keep_fast_lane_alive=True,
        llm_priority="high",
        notes=("protect_reply_speed", "heavy_vision_steps_back"),
    ),
    AiBrokerMode.VISION_ACTION: AiLaneProfile(
        heavy_lane_cadence_hz=6.0,
        keep_fast_lane_alive=True,
        llm_priority="low",
        notes=("vision_priority", "short_ack_before_heavy_work"),
    ),
    AiBrokerMode.FOCUS_SENTINEL: AiLaneProfile(
        heavy_lane_cadence_hz=1.0,
        keep_fast_lane_alive=True,
        llm_priority="low",
        notes=("monitoring_mode", "quiet_long_running_policy"),
    ),
    AiBrokerMode.RECOVERY_WINDOW: AiLaneProfile(
        heavy_lane_cadence_hz=1.0,
        keep_fast_lane_alive=True,
        llm_priority="normal",
        notes=("smooth_transition", "avoid_mode_thrashing"),
    ),
}

_MODE_OWNERS: dict[AiBrokerMode, AiBrokerOwner] = {
    AiBrokerMode.IDLE_BASELINE: AiBrokerOwner.BALANCED,
    AiBrokerMode.CONVERSATION_ANSWER: AiBrokerOwner.ANSWER_PATH,
    AiBrokerMode.VISION_ACTION: AiBrokerOwner.VISION_PATH,
    AiBrokerMode.FOCUS_SENTINEL: AiBrokerOwner.MONITOR_PATH,
    AiBrokerMode.RECOVERY_WINDOW: AiBrokerOwner.BALANCED,
}


class AiBrokerService:
    """
    Central policy owner for NeXa heavy AI lane coordination.

    Stage D Part 1 scope:
    - hold the runtime ownership state model
    - expose mode transitions
    - apply heavy-lane cadence changes through a public vision backend surface
    - provide a recovery window state that can later be wired into runtime hooks

    This class intentionally does not yet decide mode automatically.
    Runtime integration comes in the next part.
    """

    def __init__(
        self,
        *,
        vision_backend: Any | None = None,
        settings: Mapping[str, Any] | None = None,
        clock=None,
    ) -> None:
        self._vision_backend = vision_backend
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()

        broker_cfg = dict((settings or {}).get("ai_broker", {}) or {})
        self._recovery_window_seconds = max(
            0.0,
            float(broker_cfg.get("recovery_window_seconds", _DEFAULT_RECOVERY_WINDOW_SECONDS)),
        )
        self._profiles = self._build_profiles(broker_cfg)

        self._recovery_return_mode = AiBrokerMode.IDLE_BASELINE
        self._snapshot = AiBrokerSnapshot(
            mode=AiBrokerMode.IDLE_BASELINE,
            owner=AiBrokerOwner.BALANCED,
            profile=self._profiles[AiBrokerMode.IDLE_BASELINE],
            recovery_window_active=False,
            recovery_until_monotonic=None,
            last_reason="broker_initialized",
            last_error=None,
            vision_control_available=self._supports_vision_control(),
            metadata={
                "vision_profile_applied": False,
                "supported_modes": [mode.value for mode in AiBrokerMode],
            },
        )

    def enter_idle_baseline(self, *, reason: str = "") -> dict[str, Any]:
        return self._transition(
            mode=AiBrokerMode.IDLE_BASELINE,
            reason=reason or "idle_baseline_requested",
        )

    def enter_conversation_answer_mode(self, *, reason: str = "") -> dict[str, Any]:
        return self._transition(
            mode=AiBrokerMode.CONVERSATION_ANSWER,
            reason=reason or "conversation_answer_requested",
        )

    def enter_vision_action_mode(self, *, reason: str = "") -> dict[str, Any]:
        return self._transition(
            mode=AiBrokerMode.VISION_ACTION,
            reason=reason or "vision_action_requested",
        )

    def enter_focus_sentinel_mode(self, *, reason: str = "") -> dict[str, Any]:
        return self._transition(
            mode=AiBrokerMode.FOCUS_SENTINEL,
            reason=reason or "focus_sentinel_requested",
        )

    def enter_recovery_window(
        self,
        *,
        reason: str = "",
        return_to_mode: AiBrokerMode = AiBrokerMode.IDLE_BASELINE,
        seconds: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._recovery_return_mode = return_to_mode
        return self._transition(
            mode=AiBrokerMode.RECOVERY_WINDOW,
            reason=reason or "recovery_window_requested",
            recovery_seconds=seconds,
        )

    def tick(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
            if not snapshot.recovery_window_active:
                return snapshot.to_dict()

            deadline = snapshot.recovery_until_monotonic
            if deadline is None or self._clock() < deadline:
                return snapshot.to_dict()

            return_mode = self._recovery_return_mode

        return self._transition(
            mode=return_mode,
            reason="recovery_window_elapsed",
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot.to_dict()

    def status(self) -> dict[str, Any]:
        data = self.snapshot()
        data["profiles"] = {
            mode.value: profile.to_dict()
            for mode, profile in self._profiles.items()
        }
        data["recovery_window_seconds"] = float(self._recovery_window_seconds)
        return data

    def close(self) -> None:
        return None

    def _transition(
        self,
        *,
        mode: AiBrokerMode,
        reason: str,
        recovery_seconds: float | None = None,
    ) -> dict[str, Any]:
        profile = self._profiles[mode]
        owner = _MODE_OWNERS[mode]
        vision_applied, last_error = self._apply_vision_profile(profile)

        recovery_window_active = mode == AiBrokerMode.RECOVERY_WINDOW
        recovery_until = None
        if recovery_window_active:
            duration = self._recovery_window_seconds if recovery_seconds is None else float(recovery_seconds)
            duration = max(0.0, duration)
            recovery_until = self._clock() + duration

        snapshot = AiBrokerSnapshot(
            mode=mode,
            owner=owner,
            profile=profile,
            recovery_window_active=recovery_window_active,
            recovery_until_monotonic=recovery_until,
            last_reason=reason,
            last_error=last_error,
            vision_control_available=self._supports_vision_control(),
            metadata={
                "vision_profile_applied": bool(vision_applied),
                "supported_modes": [candidate.value for candidate in AiBrokerMode],
            },
        )

        with self._lock:
            self._snapshot = snapshot

        LOGGER.info(
            "AiBrokerService: mode=%s owner=%s heavy_lane=%.2fHz applied=%s reason=%s",
            mode.value,
            owner.value,
            profile.heavy_lane_cadence_hz,
            vision_applied,
            reason,
        )
        return snapshot.to_dict()

    def _apply_vision_profile(self, profile: AiLaneProfile) -> tuple[bool, str | None]:
        backend = self._vision_backend
        if backend is None:
            return False, None

        try:
            set_cadence = getattr(backend, "set_object_detection_cadence_hz", None)
            if callable(set_cadence):
                applied = bool(set_cadence(profile.heavy_lane_cadence_hz))
                return applied, None

            if profile.heavy_lane_cadence_hz <= 0.0:
                pause = getattr(backend, "pause_object_detection", None)
                if callable(pause):
                    applied = bool(pause())
                    return applied, None
                return False, None

            resume = getattr(backend, "resume_object_detection", None)
            if callable(resume):
                applied = bool(resume(profile.heavy_lane_cadence_hz))
                return applied, None

            return False, None
        except Exception as error:
            return False, f"{error.__class__.__name__}: {error}"

    def _supports_vision_control(self) -> bool:
        backend = self._vision_backend
        if backend is None:
            return False

        return any(
            callable(getattr(backend, method_name, None))
            for method_name in (
                "set_object_detection_cadence_hz",
                "pause_object_detection",
                "resume_object_detection",
            )
        )

    def _build_profiles(
        self,
        broker_cfg: Mapping[str, Any],
    ) -> dict[AiBrokerMode, AiLaneProfile]:
        profile_cfg = dict(broker_cfg.get("profiles", {}) or {})
        profiles: dict[AiBrokerMode, AiLaneProfile] = {}

        for mode, default_profile in _DEFAULT_PROFILES.items():
            override = dict(profile_cfg.get(mode.value, {}) or {})
            profiles[mode] = AiLaneProfile(
                heavy_lane_cadence_hz=max(
                    0.0,
                    float(
                        override.get(
                            "heavy_lane_cadence_hz",
                            default_profile.heavy_lane_cadence_hz,
                        )
                    ),
                ),
                keep_fast_lane_alive=bool(
                    override.get(
                        "keep_fast_lane_alive",
                        default_profile.keep_fast_lane_alive,
                    )
                ),
                llm_priority=str(
                    override.get("llm_priority", default_profile.llm_priority)
                ),
                notes=tuple(
                    str(item)
                    for item in override.get("notes", default_profile.notes)
                ),
            )

        return profiles