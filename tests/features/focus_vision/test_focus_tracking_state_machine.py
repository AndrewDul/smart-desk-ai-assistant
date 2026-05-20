"""Tests for the Focus Mode tracking state machine.

Covers: debounce, one-scan-per-episode, AWAY_WARNED hold, episode reset,
scan cancellation on face return, periodic scan disabled while face visible,
paused_for_focus_scan not dominating, phone reminder regression, tilt clamp,
mobile base never called, centered face no servo noise.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

from modules.features.focus_vision import (
    FocusScanResult,
    FocusVisionConfig,
    FocusVisionSentinelService,
)
from modules.features.focus_vision.models import FocusVisionEvidence
from modules.runtime.contracts import VisionObservation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _face_observation(
    *,
    face_x_norm: float = 0.5,
    face_y_norm: float = 0.5,
    frame_width: int = 640,
    frame_height: int = 480,
    captured_at: float = 1.0,
) -> VisionObservation:
    left = int((face_x_norm - 0.05) * frame_width)
    right = int((face_x_norm + 0.05) * frame_width)
    top = int((face_y_norm - 0.07) * frame_height)
    bottom = int((face_y_norm + 0.07) * frame_height)
    return VisionObservation(
        detected=True,
        user_present=True,
        desk_active=False,
        computer_work_likely=False,
        on_phone_likely=False,
        studying_likely=False,
        confidence=0.9,
        captured_at=captured_at,
        labels=(),
        metadata={
            "frame_width": frame_width,
            "frame_height": frame_height,
            "perception": {
                "frame_width": frame_width,
                "frame_height": frame_height,
                "faces": [
                    {
                        "bounding_box": {"left": left, "top": top, "right": right, "bottom": bottom},
                        "confidence": 0.9,
                        "metadata": {},
                    }
                ],
                "people": [],
                "objects": [],
            },
        },
    )


def _no_face_observation(*, captured_at: float = 1.0) -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=False,
        desk_active=False,
        computer_work_likely=False,
        on_phone_likely=False,
        studying_likely=False,
        confidence=0.0,
        captured_at=captured_at,
        labels=(),
        metadata={
            "frame_width": 640,
            "frame_height": 480,
            "perception": {
                "frame_width": 640,
                "frame_height": 480,
                "faces": [],
                "people": [],
                "objects": [],
            },
        },
    )


def _phone_observation(*, captured_at: float = 1.0) -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=True,
        desk_active=False,
        computer_work_likely=False,
        on_phone_likely=True,
        studying_likely=False,
        confidence=0.9,
        captured_at=captured_at,
        labels=("object:cell phone",),
        metadata={
            "frame_width": 640,
            "frame_height": 480,
            "perception": {
                "frame_width": 640,
                "frame_height": 480,
                "faces": [{"bounding_box": {"left": 280, "top": 160, "right": 360, "bottom": 256}, "confidence": 0.9, "metadata": {}}],
                "people": [],
                "objects": [{"label": "cell phone", "confidence": 0.85, "bounding_box": {"left": 270, "top": 200, "right": 370, "bottom": 300}}],
            },
        },
    )


class _MockPanTiltBackend:
    def __init__(self) -> None:
        self.move_delta_calls: list[dict[str, float]] = []

    def status(self) -> dict[str, Any]:
        return {"tilt_angle": 0.0, "pan_angle": 0.0, "ok": True}

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        self.move_delta_calls.append({"pan": pan_delta_degrees, "tilt": tilt_delta_degrees})
        return {
            "ok": True,
            "movement_executed": True,
            "blocked_reason": "",
            "missing_safety_gates": [],
        }


def _service(
    *,
    pan_tilt_backend: Any = None,
    debounce: float = 0.5,
    **config_overrides: Any,
) -> FocusVisionSentinelService:
    defaults: dict[str, Any] = dict(
        enabled=True,
        dry_run=False,
        voice_warnings_enabled=True,
        active_monitoring_enabled=True,
        continuous_tracking_enabled=True,
        pan_tilt_scan_enabled=False,
        warning_cooldown_seconds=0.0,
        enabled_reminder_kinds=("away_soft", "phone"),
        startup_grace_seconds=0.0,
        face_lost_debounce_seconds=debounce,
        focus_scan_once_per_absence_episode=True,
        tracking_hold_zone_x=0.035,
        tracking_hold_zone_y=0.025,
        tracking_pan_gain_degrees=22.0,
        tracking_tilt_gain_degrees=34.0,
        tracking_max_pan_step_degrees=1.4,
        tracking_max_tilt_step_degrees=2.0,
        tracking_min_move_degrees=0.12,
    )
    defaults.update(config_overrides)
    cfg = FocusVisionConfig(**defaults)
    svc = FocusVisionSentinelService(
        vision_backend=None,
        config=cfg,
        telemetry=MagicMock(),
        pan_tilt_backend=pan_tilt_backend,
    )
    svc._running = True
    return svc


def _completed_away_recheck(
    *,
    triggered_at: float,
    completed_at: float,
    person_found: bool = False,
    camera_available: bool = True,
) -> FocusScanResult:
    return FocusScanResult(
        scan_type="away_recheck",
        person_found=person_found,
        triggered_at=triggered_at,
        completed_at=completed_at,
        camera_available=camera_available,
    )


# ---------------------------------------------------------------------------
# 1. Fresh face visible → tracking, no scan triggered
# ---------------------------------------------------------------------------

def test_fresh_face_visible_does_not_trigger_scan() -> None:
    """FACE_LOCKED: when face is visible, no scan must be started."""
    svc = _service()
    obs = _face_observation(captured_at=10.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    # Inject observation so tracking worker can read it
    svc._last_forced_observation = obs
    status = svc._tracking_worker_step(current_time=10.0)
    assert status.get("immediate_away_scan_started") is False
    assert status.get("hard_person_visible") is True


# ---------------------------------------------------------------------------
# 2. Face flickers missing for less than debounce → no scan
# ---------------------------------------------------------------------------

def test_face_flicker_under_debounce_does_not_trigger_scan() -> None:
    """FACE_LOST_DEBOUNCE: brief absence under debounce must not start a scan."""
    svc = _service(debounce=0.5)
    # Person last seen at t=5.0
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=5.0)
    # At t=5.2 — only 0.2s since last seen (< 0.5s debounce)
    status = svc._tracking_worker_step(current_time=5.2)
    assert status.get("immediate_away_scan_started") is False
    assert status.get("tracking_state") == "face_lost_debounce"


def test_face_flicker_tracking_state_is_debounce() -> None:
    """tracking_state='face_lost_debounce' must appear in telemetry during debounce."""
    svc = _service(debounce=0.5)
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=5.0)
    status = svc._tracking_worker_step(current_time=5.3)
    assert status.get("tracking_state") == "face_lost_debounce"


# ---------------------------------------------------------------------------
# 3. Face missing beyond debounce → exactly one scan starts
# ---------------------------------------------------------------------------

def test_face_missing_beyond_debounce_triggers_scan() -> None:
    """FACE_REACQUIRE_SCAN: after debounce expires, one scan must start."""
    svc = _service(debounce=0.5)
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=5.0)
    # t=6.0: 1.0s since last seen > 0.5s debounce
    status = svc._tracking_worker_step(current_time=6.0)
    assert status.get("immediate_away_scan_started") is True


# ---------------------------------------------------------------------------
# 4. Scan completed with no face → away reminder delivered from tracking worker
# ---------------------------------------------------------------------------

def test_scan_completed_no_face_delivers_away_reminder() -> None:
    """FACE_REACQUIRE_SCAN → AWAY_WARNED: after scan confirms absence, reminder fires."""
    delivered: list[object] = []
    svc = _service()
    svc.set_reminder_handler(delivered.append)
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=90.0)
    svc._last_focus_scan_result = _completed_away_recheck(triggered_at=95.0, completed_at=96.0)
    status = svc._tracking_worker_step(current_time=100.0)
    assert status.get("immediate_away_reminder_due") is True
    assert len(delivered) == 1 or status.get("away_reminder_delivered") is True


# ---------------------------------------------------------------------------
# 5. After away reminder delivered → no repeated scan
# ---------------------------------------------------------------------------

def test_no_repeated_scan_after_away_reminder() -> None:
    """AWAY_WARNED: once away reminder fires, no new scan must start on subsequent ticks."""
    delivered: list[object] = []
    svc = _service()
    svc.set_reminder_handler(delivered.append)
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=90.0)
    svc._last_focus_scan_result = _completed_away_recheck(triggered_at=95.0, completed_at=96.0)
    # First tick: delivers reminder
    svc._tracking_worker_step(current_time=100.0)
    assert svc._away_warned_this_episode is True
    # Subsequent ticks: no new scan
    for t in [100.1, 100.5, 101.0, 105.0]:
        status = svc._tracking_worker_step(current_time=t)
        assert status.get("immediate_away_scan_started") is False, (
            f"New scan started at t={t} after away warning"
        )
        assert status.get("tracking_state") == "away_warned_holding"


# ---------------------------------------------------------------------------
# 6. Fresh face returns after away warning → episode resets, tracking resumes
# ---------------------------------------------------------------------------

def test_face_return_after_away_warning_resets_episode() -> None:
    """Face stable ≥ debounce resets away episode and resumes FACE_LOCKED."""
    svc = _service(debounce=0.5)
    svc._away_warned_this_episode = True
    # Simulate scan result from the warned episode
    svc._last_focus_scan_result = _completed_away_recheck(triggered_at=80.0, completed_at=81.0)
    assert svc._evidence_accumulator is not None
    # Face visible continuously from t=110.0 onward
    obs = _face_observation(captured_at=110.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=110.0)
    # Simulate stable face lock by setting _face_locked_since early enough
    svc._face_locked_since = 109.4  # 0.6s ago → stably locked
    status = svc._tracking_worker_step(current_time=110.0)
    assert svc._away_warned_this_episode is False, "away episode must reset when face stably returns"
    assert status.get("hard_person_visible") is True


# ---------------------------------------------------------------------------
# 7. Scan running + fresh face appears → tracking_worker continues, no infinite pause
# ---------------------------------------------------------------------------

def test_scan_running_does_not_block_forever_when_face_appears() -> None:
    """If scan expires (timeout) and face appears, tracking resumes on the same tick."""
    backend = _MockPanTiltBackend()
    svc = _service(pan_tilt_backend=backend)
    # Set up a timed-out scan
    svc._focus_scan_running = True
    svc._focus_scan_started_at = 90.0
    svc._active_focus_scan_id = "away_recheck_90.000"
    svc._active_focus_scan_type = "away_recheck"
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=90.0)
    # At t=100.0 scan has timed out (>4s) and face is back
    obs = _face_observation(captured_at=100.0)
    svc._last_forced_observation = obs
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=100.0)
    status = svc._tracking_worker_step(current_time=100.0)
    # Scan expire_stuck should have fired; tracking should not be stuck paused forever
    assert status.get("reason") != "paused_for_focus_scan" or status.get("hard_person_visible") is False


# ---------------------------------------------------------------------------
# 8. Periodic scan disabled when face is visible (config gate)
# ---------------------------------------------------------------------------

def test_periodic_scan_disabled_by_default_in_tracking_path() -> None:
    """periodic_scan_enabled=False must mean no periodic scans while face is visible."""
    svc = _service(periodic_scan_enabled=False)
    obs = _face_observation(captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    assert svc._evidence_accumulator is not None
    for i in range(10):
        t = 1.0 + i * 0.1
        svc.vision_backend.latest_observation.return_value = _face_observation(captured_at=t)
        status = svc._tracking_worker_step(current_time=t)
        assert status.get("immediate_away_scan_started") is False


# ---------------------------------------------------------------------------
# 9. paused_for_focus_scan does not dominate normal face-visible session
# ---------------------------------------------------------------------------

def test_paused_for_focus_scan_not_dominant_when_face_visible() -> None:
    """In a face-visible session, paused_for_focus_scan must not be the dominant reason."""
    backend = _MockPanTiltBackend()
    svc = _service(pan_tilt_backend=backend)
    reasons: list[str] = []
    assert svc._evidence_accumulator is not None
    obs = _face_observation(captured_at=1.0)
    svc._last_forced_observation = obs
    # Feed face-visible ticks
    for i in range(20):
        t = 1.0 + i * 0.1
        svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=t)
        status = svc._tracking_worker_step(current_time=t)
        reasons.append(str(status.get("reason") or status.get("tracking_reason", "")))
    paused_count = reasons.count("paused_for_focus_scan")
    assert paused_count < 5, (
        f"paused_for_focus_scan appeared {paused_count}/20 times while face was visible"
    )


# ---------------------------------------------------------------------------
# 10. Centered face → no servo command
# ---------------------------------------------------------------------------

def test_centered_face_does_not_generate_servo_command() -> None:
    """Face at center → target_centered, backend.move_delta must NOT be called."""
    backend = _MockPanTiltBackend()
    svc = _service(pan_tilt_backend=backend)
    obs = _face_observation(face_x_norm=0.5, face_y_norm=0.5, captured_at=1.0)
    svc._last_forced_observation = obs
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    status = svc._tracking_worker_step(current_time=1.0)
    assert backend.move_delta_calls == [], (
        "Centered face must not send servo command"
    )
    assert status.get("reason") == "target_centered" or status.get("tracking_move_executed") is False


# ---------------------------------------------------------------------------
# 11. Face movement → smooth pan/tilt command
# ---------------------------------------------------------------------------

def test_off_center_face_sends_pan_command() -> None:
    """Face displaced from center must generate a pan command."""
    backend = _MockPanTiltBackend()
    svc = _service(pan_tilt_backend=backend)
    obs = _face_observation(face_x_norm=0.7, face_y_norm=0.5, captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    status = svc._tracking_worker_step(current_time=1.0)
    assert len(backend.move_delta_calls) > 0 or status.get("tracking_plan_has_target") is True


# ---------------------------------------------------------------------------
# 12. Tilt below center remains clamped (regression)
# ---------------------------------------------------------------------------

def test_tilt_below_center_clamped_in_tracking_worker() -> None:
    """Tilt must not go below neutral even when face is below center."""
    backend = _MockPanTiltBackend()  # reports tilt_angle=0.0
    svc = _service(pan_tilt_backend=backend)
    obs = _face_observation(face_x_norm=0.5, face_y_norm=0.8, captured_at=1.0)
    svc._last_forced_observation = obs
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    status = svc._tracking_worker_step(current_time=1.0)
    if backend.move_delta_calls:
        tilt = backend.move_delta_calls[-1]["tilt"]
        assert tilt >= 0.0, f"Downward tilt {tilt:.3f}° must not be sent in Focus Mode"


# ---------------------------------------------------------------------------
# 13. Phone + fresh face still delivers fast reminder
# ---------------------------------------------------------------------------

def test_phone_reminder_delivered_when_face_and_phone_visible() -> None:
    """Phone + face → phone reminder delivered on tracking tick, not blocked by state machine."""
    delivered: list[object] = []
    svc = _service()
    svc.set_reminder_handler(delivered.append)
    obs = _phone_observation(captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=True, now=1.0)
    status = svc._tracking_worker_step(current_time=1.0)
    assert status.get("immediate_phone_reminder_due") is True or len(delivered) > 0


# ---------------------------------------------------------------------------
# 14. Mobile base is never called
# ---------------------------------------------------------------------------

def test_mobile_base_never_called() -> None:
    """mobile_base_movement_attempted must always be False."""
    backend = _MockPanTiltBackend()
    svc = _service(pan_tilt_backend=backend)
    assert svc._evidence_accumulator is not None
    # Run a mix of face-visible and face-absent ticks
    scenarios = [
        (_face_observation(face_x_norm=0.7, face_y_norm=0.3, captured_at=1.0), True),
        (_face_observation(face_x_norm=0.5, face_y_norm=0.5, captured_at=2.0), True),
        (_no_face_observation(captured_at=3.0), False),
    ]
    for obs, face_present in scenarios:
        svc._last_forced_observation = obs
        svc._evidence_accumulator.update(person_seen=face_present, phone_seen=False, now=obs.captured_at)
        status = svc._tracking_worker_step(current_time=obs.captured_at)
        assert status.get("mobile_base_movement_attempted") is False


# ---------------------------------------------------------------------------
# 15. Visual Shell launcher test passes (smoke)
# ---------------------------------------------------------------------------

def test_focus_vision_config_defaults_are_sane() -> None:
    """Default config must have sensible values for production Focus Mode."""
    cfg = FocusVisionConfig()
    assert 0.0 <= cfg.face_lost_debounce_seconds <= 2.0, "Debounce must be short"
    assert cfg.focus_scan_once_per_absence_episode is True
    assert cfg.scan_point_settle_seconds <= 0.5
    assert cfg.tracking_min_move_degrees > 0.0
    assert cfg.tracking_hold_zone_x > 0.0
    assert cfg.tracking_hold_zone_y > 0.0
    assert 0.0 < cfg.focus_tracking_command_coalesce_seconds <= 1.0
    assert 0.0 < cfg.focus_tracking_command_change_threshold_degrees <= 5.0


# ---------------------------------------------------------------------------
# 16. Stale observation holds briefly, then reacquires
# ---------------------------------------------------------------------------

def test_stale_observation_holds_briefly_then_triggers_one_scan() -> None:
    """A stale frame holds briefly, then transitions to face reacquisition."""
    backend = _MockPanTiltBackend()
    svc = _service(
        pan_tilt_backend=backend,
        debounce=0.1,
        tracking_max_observation_age_seconds=1.5,
        face_stale_hold_max_seconds=1.2,
    )
    # captured_at=1.0, current_time=10.0 → age=9s > 1.5s → stale
    stale_obs = _face_observation(face_x_norm=0.5, face_y_norm=0.5, captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = stale_obs
    assert svc._evidence_accumulator is not None

    for tick in range(12):
        t = 10.0 + tick * 0.1
        status = svc._tracking_worker_step(current_time=t)
        assert status.get("immediate_away_scan_started") is False, (
            f"Scan triggered on tick {tick} with stale observation"
        )
        assert status.get("immediate_away_scan_triggered") is False
        assert status.get("tracking_state") == "stale_observation_hold"

    status = svc._tracking_worker_step(current_time=11.3)
    assert status.get("stale_hold_timeout_reached") is True
    assert status.get("stale_hold_transition") == "face_reacquire"
    assert status.get("immediate_away_scan_started") is True


def test_stale_observation_tracking_state_is_stale_hold() -> None:
    """tracking_state must be 'stale_observation_hold' when the frame is stale."""
    svc = _service(tracking_max_observation_age_seconds=1.5)
    # captured_at=1.0, current_time=10.0 → age=9s > 1.5s → stale
    stale_obs = _face_observation(face_x_norm=0.5, face_y_norm=0.5, captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = stale_obs
    assert svc._evidence_accumulator is not None

    status = svc._tracking_worker_step(current_time=10.0)
    assert status.get("tracking_state") == "stale_observation_hold", (
        f"Expected 'stale_observation_hold', got '{status.get('tracking_state')}'"
    )
    assert status.get("observation_stale") is True


def test_stale_observation_does_not_call_move_delta() -> None:
    """A stale observation must never produce a hardware move command."""
    backend = _MockPanTiltBackend()
    svc = _service(
        pan_tilt_backend=backend,
        tracking_max_observation_age_seconds=1.5,
    )
    # Off-center face, but captured 9 seconds ago → stale
    stale_obs = _face_observation(face_x_norm=0.9, face_y_norm=0.1, captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = stale_obs
    assert svc._evidence_accumulator is not None

    for tick in range(10):
        svc._tracking_worker_step(current_time=10.0 + tick * 0.1)

    assert len(backend.move_delta_calls) == 0, (
        f"move_delta called {len(backend.move_delta_calls)} time(s) during stale period"
    )


def test_stale_frame_does_not_reset_face_lost_since() -> None:
    """Stale frames must not clear or modify _face_lost_since set by a prior fresh no-face."""
    svc = _service(debounce=0.5, tracking_max_observation_age_seconds=1.5)
    assert svc._evidence_accumulator is not None

    # Tick 1: fresh no-face frame at t=1.0 (age=0 → not stale) — sets _face_lost_since
    no_face = _no_face_observation(captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = no_face
    svc._tracking_worker_step(current_time=1.0)
    face_lost_at = svc._face_lost_since
    assert face_lost_at is not None, "face_lost_since should be set after fresh no-face tick"

    # Tick 2: stale frame at t=10.0 (age=9s > 1.5s → stale) — must not change face_lost_since
    stale_obs = _face_observation(captured_at=1.0)
    svc.vision_backend.latest_observation.return_value = stale_obs
    svc._tracking_worker_step(current_time=10.0)
    assert svc._face_lost_since == face_lost_at, (
        f"_face_lost_since changed from {face_lost_at} to {svc._face_lost_since} during stale tick"
    )


def test_stale_frame_does_not_clear_face_locked_since() -> None:
    """Stale frames must not discard _face_locked_since established by a prior fresh face."""
    svc = _service(debounce=0.5, tracking_max_observation_age_seconds=1.5)
    assert svc._evidence_accumulator is not None

    # Tick 1: fresh face at t=1.0 (age=0 → not stale) — sets _face_locked_since
    face_obs = _face_observation(captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = face_obs
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    svc._tracking_worker_step(current_time=1.0)
    locked_at = svc._face_locked_since
    assert locked_at is not None, "_face_locked_since should be set after fresh face tick"

    # Tick 2: stale frame at t=10.0 (age=9s > 1.5s → stale) — must not touch _face_locked_since
    stale_obs = _face_observation(captured_at=1.0)
    svc.vision_backend.latest_observation.return_value = stale_obs
    svc._tracking_worker_step(current_time=10.0)
    assert svc._face_locked_since == locked_at, (
        f"_face_locked_since cleared from {locked_at} to {svc._face_locked_since} during stale tick"
    )


# ---------------------------------------------------------------------------
# 17. Command coalescing reduces hardware command flood
# ---------------------------------------------------------------------------

def test_coalescing_suppresses_repeated_same_target_commands() -> None:
    """20 ticks with the same off-center face must produce << 20 move_delta calls.

    Before the fix, max consecutive identical pan streak was 42. After the fix,
    coalesce_seconds=0.3 at 0.1s tick = at most 1 command per 3 ticks ≈ 7 max.
    """
    backend = _MockPanTiltBackend()
    svc = _service(
        pan_tilt_backend=backend,
        focus_tracking_command_coalesce_seconds=0.3,
        focus_tracking_command_change_threshold_degrees=0.4,
    )
    # Strongly off-center face — computes max-step command every tick
    obs = _face_observation(face_x_norm=0.9, face_y_norm=0.5, captured_at=1.0)
    svc.vision_backend = MagicMock()
    svc.vision_backend.latest_observation.return_value = obs
    assert svc._evidence_accumulator is not None
    svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)

    for tick in range(20):
        t = 1.0 + tick * 0.1
        svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=t)
        svc._tracking_worker_step(current_time=t)

    total_moves = len(backend.move_delta_calls)
    # With 20 ticks at 0.1s and coalesce_seconds=0.3, at most ceil(20*0.1/0.3)+1 = 8 commands
    assert total_moves <= 8, (
        f"Expected ≤8 move_delta calls (coalescing), got {total_moves}"
    )
    assert total_moves >= 1, "At least one command must be sent when face is off-center"


def test_coalescing_does_not_suppress_significantly_changed_target() -> None:
    """When the face moves significantly between ticks, the command is NOT suppressed."""
    backend = _MockPanTiltBackend()
    svc = _service(
        pan_tilt_backend=backend,
        focus_tracking_command_coalesce_seconds=0.3,
        focus_tracking_command_change_threshold_degrees=0.4,
    )
    assert svc._evidence_accumulator is not None

    # Alternate between far-left and far-right every tick (large pan delta change)
    positions = [0.1, 0.9, 0.1, 0.9, 0.1, 0.9]
    for i, x in enumerate(positions):
        t = 1.0 + i * 0.35  # 0.35s gap each time — exceeds coalesce_seconds
        obs = _face_observation(face_x_norm=x, face_y_norm=0.5, captured_at=t)
        svc.vision_backend = MagicMock()
        svc.vision_backend.latest_observation.return_value = obs
        svc._evidence_accumulator.update(person_seen=True, phone_seen=False, now=t)
        svc._tracking_worker_step(current_time=t)

    # 6 ticks at 0.35s gaps (all > 0.3s coalesce) — all should be sent
    assert len(backend.move_delta_calls) >= 4, (
        f"Expected most commands to pass through when gap > coalesce_seconds, "
        f"got {len(backend.move_delta_calls)}"
    )
