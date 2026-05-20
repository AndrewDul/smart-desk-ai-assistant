"""Tests for _away_soft_due_from_scan delivery logic.

Before the fix, camera_available=False with scan_blocked_reason="" (scan ran but
all observation force-refreshes timed out) was incorrectly treated as a
"camera_unavailable" block, so the away reminder was never delivered even after
a completed scan returned no person.

After the fix, "" is included in the allowed-reasons set alongside "scan_timeout"
and "scan_exception", so a completed scan with observation timeouts still allows
away reminder delivery.
"""
from __future__ import annotations

from modules.features.focus_vision import (
    FocusScanResult,
    FocusVisionConfig,
    FocusVisionSentinelService,
    FocusVisionState,
)
from modules.features.focus_vision.models import (
    FocusVisionDecision,
    FocusVisionEvidence,
    FocusVisionStateSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service() -> FocusVisionSentinelService:
    cfg = FocusVisionConfig(
        enabled=True,
        dry_run=False,
        active_monitoring_enabled=False,
        continuous_tracking_enabled=False,
        pan_tilt_scan_enabled=False,
        startup_grace_seconds=0.0,
        away_soft_reminder_after_seconds=5.0,
    )
    return FocusVisionSentinelService(vision_backend=None, config=cfg)


def _snapshot(state: FocusVisionState = FocusVisionState.ABSENT) -> FocusVisionStateSnapshot:
    evidence = FocusVisionEvidence()
    decision = FocusVisionDecision(
        state=state,
        confidence=0.9,
        reasons=(),
        observed_at=100.0,
        evidence=evidence,
    )
    return FocusVisionStateSnapshot(
        current_state=state,
        stable_seconds=30.0,
        state_started_at=70.0,
        updated_at=100.0,
        decision=decision,
    )


def _completed_away_recheck(
    *,
    camera_available: bool,
    scan_blocked_reason: str = "",
    person_found: bool = False,
    triggered_at: float = 5.0,
    completed_at: float = 9.0,
) -> FocusScanResult:
    return FocusScanResult(
        scan_type="away_recheck",
        person_found=person_found,
        triggered_at=triggered_at,
        completed_at=completed_at,
        blocked=False,
        movement_executed=True,
        scan_blocked_reason=scan_blocked_reason,
        pan_tilt_scan_enabled=True,
        pan_tilt_backend_present=True,
        camera_available=camera_available,
    )


# ---------------------------------------------------------------------------
# Bug A regression tests — camera_available=False with empty reason
# ---------------------------------------------------------------------------

def test_away_soft_camera_unavailable_empty_reason_delivers() -> None:
    """BUG A fix: camera_available=False + scan_blocked_reason='' must allow delivery.

    This is the case where the scan physically ran (pan moved, settled) but all
    observation force-refreshes timed out.  The away reminder must fire.
    """
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is True, f"Expected delivery, got due={due!r} reason={reason!r}"
    assert reason == "away_recheck_no_person"


def test_away_soft_camera_unavailable_scan_timeout_delivers() -> None:
    """scan_blocked_reason='scan_timeout' is an existing allowed reason — must deliver."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="scan_timeout",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is True, f"Expected delivery, got due={due!r} reason={reason!r}"


def test_away_soft_camera_unavailable_scan_exception_delivers() -> None:
    """scan_blocked_reason='scan_exception' is an existing allowed reason — must deliver."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="scan_exception",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is True, f"Expected delivery, got due={due!r} reason={reason!r}"


# ---------------------------------------------------------------------------
# Non-empty blocked reasons must still block when camera unavailable
# ---------------------------------------------------------------------------

def test_away_soft_camera_unavailable_scan_disabled_blocks() -> None:
    """pan_tilt_scan_disabled means the scan never ran — do not deliver."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="pan_tilt_scan_disabled",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False
    assert reason == "camera_unavailable"


def test_away_soft_camera_unavailable_backend_missing_blocks() -> None:
    """pan_tilt_backend_missing means the scan never ran — do not deliver."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="pan_tilt_backend_missing",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False
    assert reason == "camera_unavailable"


def test_away_soft_camera_unavailable_hardware_gates_closed_blocks() -> None:
    """hardware_gates_closed means no movement executed — do not deliver."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=False,
        scan_blocked_reason="hardware_gates_closed",
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False
    assert reason == "camera_unavailable"


# ---------------------------------------------------------------------------
# Normal delivery path (camera_available=True)
# ---------------------------------------------------------------------------

def test_away_soft_camera_available_delivers() -> None:
    """camera_available=True (obs.detected was True) → normal delivery."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(camera_available=True)
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is True
    assert reason == "away_recheck_no_person"


# ---------------------------------------------------------------------------
# Gating conditions that block delivery
# ---------------------------------------------------------------------------

def test_away_soft_person_seen_true_blocks() -> None:
    """person_seen=True at delivery time means person returned — block reminder."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(camera_available=True)
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=True)
    assert due is False
    assert reason == "person_evidence_returned"


def test_away_soft_no_scan_result_blocks() -> None:
    """No completed scan result → no delivery."""
    svc = _service()
    svc._last_focus_scan_result = None
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False


def test_away_soft_wrong_scan_type_blocks() -> None:
    """scan_type != 'away_recheck' → no delivery."""
    svc = _service()
    svc._last_focus_scan_result = FocusScanResult(
        scan_type="periodic",
        person_found=False,
        triggered_at=5.0,
        completed_at=9.0,
        camera_available=True,
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False


def test_away_soft_incomplete_scan_blocks() -> None:
    """completed_at=None (scan still running) → no delivery."""
    svc = _service()
    svc._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=5.0,
        completed_at=None,
        camera_available=True,
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False


def test_away_soft_person_found_during_scan_blocks() -> None:
    """person_found=True during scan means person was seen — block delivery."""
    svc = _service()
    svc._last_focus_scan_result = _completed_away_recheck(
        camera_available=True,
        person_found=True,
    )
    due, reason = svc._away_soft_due_from_scan(_snapshot(), person_seen=False)
    assert due is False
    assert reason == "person_found"
