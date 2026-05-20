from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FocusScanResult:
    """Result of a single focus-mode active scan attempt."""

    scan_type: str
    person_found: bool
    triggered_at: float
    completed_at: float | None = None
    blocked: bool = False
    movement_executed: bool = False
    scan_blocked_reason: str = ""
    pan_tilt_scan_enabled: bool = False
    pan_tilt_backend_present: bool = False
    missing_safety_gates: tuple[str, ...] = field(default_factory=tuple)
    camera_available: bool = True
    scan_id: str = ""
    scan_points_attempted: int = 0
    scan_point_results: tuple[dict, ...] = field(default_factory=tuple)
    behavior_presence_ignored_for_scan: bool = True
    stale_observation_ignored: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "scan_type": self.scan_type,
            "person_found": self.person_found,
            "triggered_at": self.triggered_at,
            "completed_at": self.completed_at,
            "blocked": self.blocked,
            "movement_executed": self.movement_executed,
            "scan_blocked_reason": self.scan_blocked_reason,
            "pan_tilt_scan_enabled": self.pan_tilt_scan_enabled,
            "pan_tilt_backend_present": self.pan_tilt_backend_present,
            "missing_safety_gates": list(self.missing_safety_gates),
            "camera_available": self.camera_available,
            "scan_id": self.scan_id,
            "scan_points_attempted": self.scan_points_attempted,
            "scan_point_results": list(self.scan_point_results),
            "behavior_presence_ignored_for_scan": self.behavior_presence_ignored_for_scan,
            "stale_observation_ignored": self.stale_observation_ignored,
        }


@dataclass(slots=True)
class FocusMonitoringEvidenceAccumulator:
    """
    Wall-clock tracker for person presence and phone usage.

    Unlike stable_seconds from the state machine, these counters are NOT reset
    when no_observation gaps occur — only session boundaries or explicit loss
    of evidence for longer than the gap tolerance.
    """

    phone_gap_tolerance_seconds: float = 5.0

    _last_person_evidence_at: float | None = field(default=None, init=False)
    _phone_accumulated_seconds: float = field(default=0.0, init=False)
    _phone_first_seen_at: float | None = field(default=None, init=False)
    _last_phone_evidence_at: float | None = field(default=None, init=False)
    _last_phone_gap_seconds: float = field(default=0.0, init=False)
    _session_started_at: float | None = field(default=None, init=False)

    def reset(self, *, now: float) -> None:
        self._last_person_evidence_at = None
        self._phone_accumulated_seconds = 0.0
        self._phone_first_seen_at = None
        self._last_phone_evidence_at = None
        self._last_phone_gap_seconds = 0.0
        self._session_started_at = now

    def update(self, *, person_seen: bool, phone_seen: bool, now: float) -> None:
        if person_seen:
            self._last_person_evidence_at = now

        if phone_seen and person_seen:
            if self._phone_first_seen_at is None:
                self._phone_first_seen_at = now
            if self._last_phone_evidence_at is not None:
                gap = now - self._last_phone_evidence_at
                self._last_phone_gap_seconds = max(0.0, gap)
                if gap <= self.phone_gap_tolerance_seconds:
                    self._phone_accumulated_seconds += gap
            self._last_phone_evidence_at = now
        elif self._last_phone_evidence_at is not None:
            gap = now - self._last_phone_evidence_at
            self._last_phone_gap_seconds = max(0.0, gap)
            if gap > self.phone_gap_tolerance_seconds:
                self._phone_accumulated_seconds = 0.0
                self._phone_first_seen_at = None
                self._last_phone_evidence_at = None

    def record_person_seen(self, *, now: float) -> None:
        """Called when a background scan finds a person outside the normal tick path."""
        self._last_person_evidence_at = now

    def last_person_evidence_at(self) -> float | None:
        return self._last_person_evidence_at

    def person_absent_seconds(self, *, now: float) -> float | None:
        if self._last_person_evidence_at is None:
            return None
        return max(0.0, now - self._last_person_evidence_at)

    def phone_accumulated_seconds(self) -> float:
        return self._phone_accumulated_seconds

    def phone_first_seen_seconds_ago(self, *, now: float) -> float | None:
        if self._phone_first_seen_at is None:
            return None
        return max(0.0, now - self._phone_first_seen_at)

    def phone_gap_seconds(self) -> float:
        return self._last_phone_gap_seconds

    def status(self) -> dict[str, object]:
        return {
            "last_person_evidence_at": self._last_person_evidence_at,
            "phone_accumulated_seconds": self._phone_accumulated_seconds,
            "phone_first_seen_at": self._phone_first_seen_at,
            "last_phone_evidence_at": self._last_phone_evidence_at,
            "phone_gap_seconds": self._last_phone_gap_seconds,
            "session_started_at": self._session_started_at,
        }


@dataclass(slots=True)
class FocusMonitoringScanScheduler:
    """
    Decides when focus-mode scans are due.

    Periodic scans sweep left/right every N seconds to confirm user presence.
    Away-recheck scans fire once per absence episode when person missing >= threshold.
    """

    periodic_scan_interval_seconds: float = 35.0
    away_recheck_scan_after_seconds: float = 8.0

    _last_periodic_scan_at: float | None = field(default=None, init=False)
    _away_recheck_triggered_at: float | None = field(default=None, init=False)
    _session_started_at: float | None = field(default=None, init=False)

    def reset(self, *, now: float) -> None:
        self._last_periodic_scan_at = None
        self._away_recheck_triggered_at = None
        self._session_started_at = now

    def is_periodic_scan_due(self, *, now: float) -> bool:
        if self._session_started_at is None:
            return False
        reference = self._last_periodic_scan_at if self._last_periodic_scan_at is not None else self._session_started_at
        return (now - reference) >= self.periodic_scan_interval_seconds

    def is_away_recheck_due(self, *, now: float, person_absent_seconds: float | None) -> bool:
        if person_absent_seconds is None:
            return False
        if person_absent_seconds < self.away_recheck_scan_after_seconds:
            return False
        return self._away_recheck_triggered_at is None

    def record_periodic_scan(self, *, now: float) -> None:
        self._last_periodic_scan_at = now

    def record_away_recheck_triggered(self, *, now: float) -> None:
        self._away_recheck_triggered_at = now

    def reset_away_recheck(self) -> None:
        """Call when person is seen again so the next absence episode can trigger a fresh recheck."""
        self._away_recheck_triggered_at = None

    def away_recheck_triggered(self) -> bool:
        return self._away_recheck_triggered_at is not None

    def status(self) -> dict[str, object]:
        return {
            "last_periodic_scan_at": self._last_periodic_scan_at,
            "away_recheck_triggered_at": self._away_recheck_triggered_at,
            "session_started_at": self._session_started_at,
            "periodic_scan_interval_seconds": self.periodic_scan_interval_seconds,
            "away_recheck_scan_after_seconds": self.away_recheck_scan_after_seconds,
        }


__all__ = [
    "FocusScanResult",
    "FocusMonitoringEvidenceAccumulator",
    "FocusMonitoringScanScheduler",
]
