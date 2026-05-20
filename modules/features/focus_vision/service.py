from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Callable

from modules.devices.vision.look_at_me.tracking_planner import TrackingPlanner
from modules.devices.vision.tracking.target_selector import TrackingTargetSelector

from .active_monitoring import (
    FocusMonitoringEvidenceAccumulator,
    FocusMonitoringScanScheduler,
    FocusScanResult,
)
from .config import FocusVisionConfig
from .decision_engine import FocusVisionDecisionEngine
from .models import (
    FocusVisionDecision,
    FocusVisionEvidence,
    FocusVisionReminder,
    FocusVisionState,
    FocusVisionStateSnapshot,
)
from .reminder_policy import FocusVisionReminderPolicy
from .state_machine import FocusVisionStateMachine
from .telemetry import FocusVisionTelemetryWriter


@dataclass(slots=True)
class FocusVisionTickResult:
    snapshot: FocusVisionStateSnapshot | None
    reminder: FocusVisionReminder | None
    reminder_delivered: bool = False
    reminder_delivery_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": None if self.snapshot is None else self.snapshot.to_dict(),
            "reminder": None if self.reminder is None else self.reminder.to_dict(),
            "reminder_delivered": self.reminder_delivered,
            "reminder_delivery_error": self.reminder_delivery_error,
        }


@dataclass(slots=True)
class FocusVisionSentinelService:
    """Background-safe focus vision monitor for Focus Mode."""

    vision_backend: Any
    config: FocusVisionConfig = field(default_factory=FocusVisionConfig)
    decision_engine: FocusVisionDecisionEngine = field(default_factory=FocusVisionDecisionEngine)
    state_machine: FocusVisionStateMachine = field(default_factory=FocusVisionStateMachine)
    reminder_policy: FocusVisionReminderPolicy | None = None
    telemetry: FocusVisionTelemetryWriter | None = None
    reminder_handler: Callable[[FocusVisionReminder], None] | None = None
    pan_tilt_backend: Any = None
    vision_tracking_service: Any = None

    _thread: threading.Thread | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _running: bool = field(default=False, init=False)
    _language: str = field(default="en", init=False)
    _last_result: FocusVisionTickResult | None = field(default=None, init=False)
    _last_error: str | None = field(default=None, init=False)
    _last_delivery_error: str | None = field(default=None, init=False)
    _last_observation_age_seconds: float | None = field(default=None, init=False)
    _last_observation_stale: bool = field(default=False, init=False)
    _last_observation_source: str = field(default="none", init=False)
    _last_forced_observation: Any = field(default=None, init=False)
    _force_refresh_in_progress: bool = field(default=False, init=False)
    _last_force_refresh_started_at: float | None = field(default=None, init=False)
    _last_force_refresh_finished_at: float | None = field(default=None, init=False)
    _last_force_refresh_reason: str | None = field(default=None, init=False)
    _last_force_refresh_error: str | None = field(default=None, init=False)
    _last_force_refresh_returned_observation: bool = field(default=False, init=False)
    _delivered_reminder_count: int = field(default=0, init=False)
    _micro_scan_state: str = field(default="idle", init=False)
    _micro_scan_requested_at: float | None = field(default=None, init=False)
    _micro_scan_completed_at: float | None = field(default=None, init=False)
    _micro_scan_result: str = field(default="none", init=False)
    _micro_scan_blocked_reason: str = field(default="", init=False)
    _evidence_accumulator: FocusMonitoringEvidenceAccumulator | None = field(default=None, init=False)
    _scan_scheduler: FocusMonitoringScanScheduler | None = field(default=None, init=False)
    _focus_scan_running: bool = field(default=False, init=False)
    _focus_scan_started_at: float | None = field(default=None, init=False)
    _active_focus_scan_id: str = field(default="", init=False)
    _active_focus_scan_type: str = field(default="", init=False)
    _last_focus_scan_result: FocusScanResult | None = field(default=None, init=False)
    _last_tracking_status: dict[str, Any] = field(default_factory=dict, init=False)
    _tracking_thread: threading.Thread | None = field(default=None, init=False)
    _tracking_selector: TrackingTargetSelector = field(default_factory=TrackingTargetSelector, init=False)
    _tracking_planner: TrackingPlanner | None = field(default=None, init=False)
    _policy_lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _face_lost_since: float | None = field(default=None, init=False)
    _face_locked_since: float | None = field(default=None, init=False)
    _stale_hold_since: float | None = field(default=None, init=False)
    _away_warned_this_episode: bool = field(default=False, init=False)
    _last_tracking_command_at: float | None = field(default=None, init=False)
    _last_tracking_pan_delta: float = field(default=0.0, init=False)
    _last_tracking_tilt_delta: float = field(default=0.0, init=False)
    _active_focus_scan_cancel_requested: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.reminder_policy is None:
            self.reminder_policy = FocusVisionReminderPolicy(config=self.config)
        if self.telemetry is None:
            self.telemetry = FocusVisionTelemetryWriter(self.config.telemetry_path)
        self._evidence_accumulator = FocusMonitoringEvidenceAccumulator(
            phone_gap_tolerance_seconds=self.config.phone_gap_tolerance_seconds,
        )
        self._scan_scheduler = FocusMonitoringScanScheduler(
            periodic_scan_interval_seconds=self.config.periodic_scan_interval_seconds,
            away_recheck_scan_after_seconds=self.config.away_recheck_scan_after_seconds,
        )
        self._tracking_planner = TrackingPlanner(
            pan_gain_degrees=self.config.tracking_pan_gain_degrees,
            tilt_gain_degrees=self.config.tracking_tilt_gain_degrees,
            hold_zone_x=self.config.tracking_hold_zone_x,
            hold_zone_y=self.config.tracking_hold_zone_y,
            max_step_degrees=max(
                self.config.tracking_max_pan_step_degrees,
                self.config.tracking_max_tilt_step_degrees,
            ),
            invert_tilt=self.config.tracking_invert_tilt,
        )

    def set_reminder_handler(
        self,
        handler: Callable[[FocusVisionReminder], None] | None,
    ) -> None:
        with self._lock:
            self.reminder_handler = handler
            self._last_delivery_error = None

    def start(self, *, language: str = "en") -> bool:
        with self._lock:
            if not self.config.enabled:
                return False
            if self._running:
                self._language = self._normalize_language(language)
                return True
            self._language = self._normalize_language(language)
            self._stop_event.clear()
            self.state_machine.reset()
            self._last_forced_observation = None
            self._last_observation_source = "none"
            self._last_force_refresh_error = None
            self._last_force_refresh_reason = None
            self._last_force_refresh_returned_observation = False
            self._micro_scan_state = "idle"
            self._micro_scan_requested_at = None
            self._micro_scan_completed_at = None
            self._micro_scan_result = "none"
            self._micro_scan_blocked_reason = ""
            self._focus_scan_running = False
            self._focus_scan_started_at = None
            self._active_focus_scan_id = ""
            self._active_focus_scan_type = ""
            self._last_focus_scan_result = None
            self._last_tracking_status = {}
            self._face_lost_since = None
            self._face_locked_since = None
            self._stale_hold_since = None
            self._away_warned_this_episode = False
            self._last_tracking_command_at = None
            self._last_tracking_pan_delta = 0.0
            self._last_tracking_tilt_delta = 0.0
            self._active_focus_scan_cancel_requested = False
            _now = time.monotonic()
            assert self._evidence_accumulator is not None
            assert self._scan_scheduler is not None
            self._evidence_accumulator.reset(now=_now)
            self._scan_scheduler.reset(now=_now)
            assert self.reminder_policy is not None
            self.reminder_policy.start_session(started_at=time.monotonic())
            self._thread = threading.Thread(
                target=self._run_loop,
                name="nexa-focus-vision-sentinel",
                daemon=True,
            )
            self._tracking_thread = None
            self._running = True
            self._thread.start()
            if self.config.continuous_tracking_enabled:
                self._tracking_thread = threading.Thread(
                    target=self._run_tracking_loop,
                    name="nexa-focus-tracking-worker",
                    daemon=True,
                )
                self._tracking_thread.start()
            return True

    def stop(self) -> None:
        thread: threading.Thread | None
        tracking_thread: threading.Thread | None
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            tracking_thread = self._tracking_thread
        if tracking_thread is not None and tracking_thread.is_alive():
            tracking_thread.join(timeout=max(1.0, self.config.tracking_interval_seconds * 10.0))
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self.config.observation_interval_seconds * 2.0))
        with self._lock:
            self._running = False
            self._thread = None
            self._tracking_thread = None
            assert self.reminder_policy is not None
            self.reminder_policy.stop_session()

    def tick(self, *, now: float | None = None) -> FocusVisionTickResult:
        current_time = float(now if now is not None else time.monotonic())
        try:
            observation = self._latest_observation_for_decision(current_time=current_time)
            decision = self.decision_engine.decide(observation, observed_at=current_time)
            ev = decision.evidence
            person_seen = self._has_person_evidence(ev)
            person_hard_visible = self._has_hard_visual_person(ev)
            phone_person_evidence = self._has_phone_person_evidence(ev)
            immediate_phone_reminder_due = phone_person_evidence
            tracking_status = self._track_visible_person(
                evidence=ev,
                hard_person_visible=person_hard_visible,
            )
            assert self._evidence_accumulator is not None
            assert self._scan_scheduler is not None
            self._evidence_accumulator.update(
                person_seen=person_hard_visible,
                phone_seen=phone_person_evidence,
                now=current_time,
            )
            if person_hard_visible:
                self._scan_scheduler.reset_away_recheck()
            immediate_away_scan_triggered = False
            if not self.config.continuous_tracking_enabled:
                immediate_away_scan_triggered = self._trigger_immediate_away_scan_if_due(
                    now=current_time,
                    hard_person_visible=person_hard_visible,
                )
            _person_absent_sec = self._evidence_accumulator.person_absent_seconds(now=current_time)
            _phone_acc_sec = self._evidence_accumulator.phone_accumulated_seconds()
            snapshot = self.state_machine.update(decision)
            snapshot = self._apply_derived_presence_states(snapshot, current_time)
            immediate_away_reminder_due = False
            away_soft_due_reason = ""
            if not self.config.continuous_tracking_enabled:
                immediate_away_reminder_due, away_soft_due_reason = self._away_soft_due_from_scan(
                    snapshot,
                    person_seen=person_hard_visible,
                )
            if immediate_away_reminder_due:
                snapshot = _replace_snapshot_state(snapshot, FocusVisionState.AWAY_PENDING_SCAN)
            assert self.reminder_policy is not None
            with self._policy_lock:
                reminder = self.reminder_policy.evaluate(
                    snapshot,
                    language=self._language,
                    now=current_time,
                    person_absent_seconds=_person_absent_sec,
                    # Kept in telemetry/status for diagnostics; reminders use immediate hard evidence.
                    phone_accumulated_seconds=_phone_acc_sec if _phone_acc_sec > 0.0 else None,
                    immediate_phone_reminder_due=immediate_phone_reminder_due,
                    immediate_away_reminder_due=immediate_away_reminder_due,
                )
            if reminder is not None and immediate_away_reminder_due and person_hard_visible:
                reminder = None
            delivered = False
            delivery_error = None
            if reminder is not None:
                delivered, delivery_error = self._deliver_reminder(reminder)
            result = FocusVisionTickResult(
                snapshot=snapshot,
                reminder=reminder,
                reminder_delivered=delivered,
                reminder_delivery_error=delivery_error,
            )
            self._last_result = result
            self._last_error = None
            self._write_telemetry(
                result,
                current_time=current_time,
                phone_person_evidence=phone_person_evidence,
                immediate_phone_reminder_due=immediate_phone_reminder_due,
                immediate_away_scan_triggered=immediate_away_scan_triggered,
                immediate_away_reminder_due=immediate_away_reminder_due,
                hard_person_visible=person_hard_visible,
                tracking_status=tracking_status,
                away_soft_due_from_scan=immediate_away_reminder_due,
                away_soft_due_reason=away_soft_due_reason,
            )
            return result
        except Exception as error:
            self._last_error = f"{error.__class__.__name__}: {error}"
            result = FocusVisionTickResult(snapshot=None, reminder=None)
            self._last_result = result
            self._write_telemetry(result, current_time=current_time)
            return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            policy_status = self.reminder_policy.status() if self.reminder_policy is not None else {}
            return {
                "enabled": self.config.enabled,
                "running": self._running,
                "language": self._language,
                "dry_run": self.config.dry_run,
                "last_error": self._last_error,
                "last_delivery_error": self._last_delivery_error,
                "latest_observation_force_refresh": self.config.latest_observation_force_refresh,
                "cache_miss_force_refresh_enabled": self.config.cache_miss_force_refresh_enabled,
                "cache_miss_force_refresh_cooldown_seconds": self.config.cache_miss_force_refresh_cooldown_seconds,
                "max_observation_age_seconds": self.config.max_observation_age_seconds,
                "last_observation_age_seconds": self._last_observation_age_seconds,
                "last_observation_stale": self._last_observation_stale,
                "last_observation_source": self._last_observation_source,
                "force_refresh_in_progress": self._force_refresh_in_progress,
                "last_force_refresh_started_at": self._last_force_refresh_started_at,
                "last_force_refresh_finished_at": self._last_force_refresh_finished_at,
                "last_force_refresh_reason": self._last_force_refresh_reason,
                "last_force_refresh_error": self._last_force_refresh_error,
                "last_force_refresh_returned_observation": self._last_force_refresh_returned_observation,
                "delivered_reminder_count": self._delivered_reminder_count,
                "reminder_handler_attached": self.reminder_handler is not None,
                "micro_scan_state": self._micro_scan_state,
                "micro_scan_result": self._micro_scan_result,
                "micro_scan_blocked_reason": self._micro_scan_blocked_reason,
                "micro_scan_requested_at": self._micro_scan_requested_at,
                "micro_scan_completed_at": self._micro_scan_completed_at,
                "pan_tilt_backend_attached": self.pan_tilt_backend is not None,
                "scan_available": (
                    self.config.pan_tilt_scan_enabled and self.pan_tilt_backend is not None
                ),
                "focus_scan_running": self._focus_scan_running,
                "focus_scan_started_at": self._focus_scan_started_at,
                "active_focus_scan_id": self._active_focus_scan_id,
                "active_focus_scan_type": self._active_focus_scan_type,
                "last_focus_scan": None if self._last_focus_scan_result is None else self._last_focus_scan_result.to_dict(),
                "focus_tracking": dict(self._last_tracking_status),
                "focus_tracking_worker_running": self._tracking_thread is not None and self._tracking_thread.is_alive(),
                "vision_tracking_service_attached": self.vision_tracking_service is not None,
                "evidence_accumulator": self._evidence_accumulator.status() if self._evidence_accumulator is not None else {},
                "scan_scheduler": self._scan_scheduler.status() if self._scan_scheduler is not None else {},
                "last_result": None if self._last_result is None else self._last_result.to_dict(),
                "policy": policy_status,
            }

    def _deliver_reminder(self, reminder: FocusVisionReminder) -> tuple[bool, str | None]:
        if reminder.dry_run:
            return False, None

        handler = self.reminder_handler
        if handler is None:
            self._last_delivery_error = "no_reminder_handler"
            return False, self._last_delivery_error

        try:
            handler(reminder)
        except Exception as error:
            self._last_delivery_error = f"{error.__class__.__name__}: {error}"
            return False, self._last_delivery_error

        self._last_delivery_error = None
        self._delivered_reminder_count += 1
        return True, None

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.tick()
                _loop_now = time.monotonic()
                self._check_and_trigger_scans(_loop_now)
                self._stop_event.wait(self.config.observation_interval_seconds)
        finally:
            with self._lock:
                self._running = False

    def _run_tracking_loop(self) -> None:
        while not self._stop_event.is_set():
            started_at = time.monotonic()
            try:
                status = self._tracking_worker_step(current_time=started_at)
                status.setdefault("telemetry_write_seconds", 0.0)
                self._write_tracking_telemetry(status, current_time=started_at)
            except Exception as error:
                status = self._tracking_status(
                    focus_tracking_active=False,
                    tracking_target_type="none",
                    tracking_move_executed=False,
                    reason=f"tracking_worker_error:{error.__class__.__name__}",
                )
                status.setdefault("telemetry_write_seconds", 0.0)
                self._last_tracking_status = status
                self._write_tracking_telemetry(status, current_time=started_at)
            elapsed = time.monotonic() - started_at
            sleep_for = max(0.01, self.config.tracking_interval_seconds - elapsed)
            self._stop_event.wait(sleep_for)

    def _tracking_worker_step(self, *, current_time: float) -> dict[str, Any]:
        step_started = time.perf_counter()
        latency: dict[str, float] = {}
        with self._lock:
            scan_running = self._focus_scan_running or self._micro_scan_state == "scanning"
            running = self._running and not self._stop_event.is_set()
        if not running:
            return self._record_tracking_status(
                self._tracking_status(
                    focus_tracking_active=False,
                    tracking_target_type="none",
                    tracking_move_executed=False,
                    reason="focus_mode_not_running",
                )
            )
        if not self.config.continuous_tracking_enabled:
            return self._record_tracking_status(
                self._tracking_status(
                    focus_tracking_active=False,
                    tracking_target_type="none",
                    tracking_move_executed=False,
                    reason="continuous_tracking_disabled",
                )
            )
        if scan_running:
            observation_probe, source_probe, observation_probe_latency = self._latest_cached_observation_for_tracking_timed()
            latency["latest_observation_seconds"] = observation_probe_latency
            probe_age = self._observation_age_seconds(observation_probe, current_time=current_time)
            probe_stale = self._is_tracking_observation_stale(probe_age)
            evidence_started = time.perf_counter()
            probe_evidence = (
                FocusVisionEvidence(metadata={"reason": "missing_observation"})
                if observation_probe is None
                else self.decision_engine.reader.read(observation_probe)
            )
            latency["evidence_read_seconds"] = round(time.perf_counter() - evidence_started, 6)
            if observation_probe is not None and not probe_stale and self._has_fresh_face(probe_evidence):
                self._cancel_active_focus_scan(
                    now=current_time,
                    reason="face_reacquired_during_scan",
                )
                status = self._track_visible_person_from_observation(
                    observation=observation_probe,
                    evidence=probe_evidence,
                    current_time=current_time,
                    latency=latency,
                )
                status.update(
                    {
                        "hard_person_visible": True,
                        "face_count": probe_evidence.face_count,
                        "yolo_person_count": probe_evidence.yolo_person_count,
                        "people_count": probe_evidence.people_count,
                        "person_without_face": probe_evidence.person_without_face,
                        "object_labels": [label for label in probe_evidence.labels if label.startswith("object:")],
                        "observation_age_seconds": probe_age,
                        "observation_source": source_probe,
                        "observation_stale": probe_stale,
                        "camera_frame_fresh": True,
                        "camera_unavailable": False,
                        "tracking_state": "scan_cancelled_face_reacquired",
                        "scan_cancelled": True,
                        "scan_cancel_reason": "face_reacquired_during_scan",
                        "tracking_worker_step_seconds": round(time.perf_counter() - step_started, 6),
                        **latency,
                    }
                )
                return self._record_tracking_status(status)
            with self._lock:
                self._expire_stuck_focus_scan_locked(current_time)
                scan_running = self._focus_scan_running or self._micro_scan_state == "scanning"
            if not scan_running:
                return self._tracking_worker_step(current_time=current_time)
            return self._record_tracking_status(
                self._tracking_status(
                    focus_tracking_active=False,
                    tracking_target_type="none",
                    tracking_move_executed=False,
                    reason="paused_for_focus_scan",
                )
            )

        observation, source, latest_observation_seconds = self._latest_cached_observation_for_tracking_timed()
        latency["latest_observation_seconds"] = latest_observation_seconds
        age_seconds = self._observation_age_seconds(observation, current_time=current_time)
        stale = self._is_tracking_observation_stale(age_seconds)
        if observation is None:
            self._last_observation_source = source
            self._last_observation_age_seconds = None
            self._last_observation_stale = False
            evidence = FocusVisionEvidence(metadata={"reason": "missing_observation"})
        else:
            self._last_observation_source = source
            self._last_observation_age_seconds = age_seconds
            self._last_observation_stale = stale
            evidence_started = time.perf_counter()
            evidence = self.decision_engine.reader.read(observation)
            latency["evidence_read_seconds"] = round(time.perf_counter() - evidence_started, 6)

        hard_face_visible = (not stale) and self._has_fresh_face(evidence)
        hard_person_visible = (not stale) and self._has_hard_visual_person(evidence)
        phone_person_evidence = (not stale) and self._has_phone_person_evidence(evidence)
        assert self._evidence_accumulator is not None
        assert self._scan_scheduler is not None
        self._evidence_accumulator.update(
            person_seen=hard_face_visible,
            phone_seen=phone_person_evidence,
            now=current_time,
        )

        # --- Focus Mode state machine ------------------------------------------
        # FACE_LOCKED: fresh face visible.
        # STALE_HOLD: observation too old; hold position, no episode state changes.
        # FACE_LOST_DEBOUNCE: fresh no-face; short hold before scanning.
        # FACE_REACQUIRE_SCAN: face missing past debounce; run one bounded scan.
        # AWAY_WARNED: scan confirmed absence, reminder delivered; hold until face returns.
        # -----------------------------------------------------------------------

        tracking_state = "face_locked"  # populated below for telemetry

        delivered_phone = False
        phone_error: str | None = None
        immediate_scan_started = False
        immediate_away_due = False
        delivered_away = False
        away_error: str | None = None
        away_reason = ""

        if hard_face_visible:
            # ---- FACE_LOCKED -------------------------------------------------
            self._face_lost_since = None
            self._stale_hold_since = None
            if self._face_locked_since is None:
                self._face_locked_since = current_time
            _face_locked_seconds = current_time - self._face_locked_since
            _stably_locked = _face_locked_seconds >= self.config.face_lost_debounce_seconds
            if _stably_locked:
                # Face genuinely returned → reset the absence episode.
                if self._away_warned_this_episode:
                    self._away_warned_this_episode = False
                self._scan_scheduler.reset_away_recheck()
                with self._lock:
                    if self._last_focus_scan_result is not None:
                        self._last_focus_scan_result = None
            tracking_state = "face_locked"

            if phone_person_evidence:
                delivered_phone, phone_error = self._deliver_immediate_reminder_from_evidence(
                    evidence=evidence,
                    current_time=current_time,
                    state=FocusVisionState.PHONE_DISTRACTION,
                    immediate_phone_reminder_due=True,
                    immediate_away_reminder_due=False,
                )

        elif stale:
            # ---- STALE_HOLD: observation aged out ----------------------------
            # Stale frames are NOT evidence of face absence.
            # Hold briefly, then enter the normal face-reacquire scan path.
            if self._stale_hold_since is None:
                self._stale_hold_since = current_time
            stale_hold_seconds = current_time - self._stale_hold_since
            if stale_hold_seconds < self.config.face_stale_hold_max_seconds:
                tracking_state = "stale_observation_hold"
            else:
                tracking_state = "face_reacquire"
                if self._face_lost_since is None:
                    self._face_lost_since = current_time
                decision = self.decision_engine.decide(None, observed_at=current_time)
                snapshot = FocusVisionStateSnapshot(
                    current_state=FocusVisionState.NO_OBSERVATION,
                    stable_seconds=0.0,
                    state_started_at=current_time,
                    updated_at=current_time,
                    decision=decision,
                )
                immediate_away_due, away_reason = self._away_soft_due_from_scan(
                    snapshot,
                    person_seen=False,
                )
                if immediate_away_due:
                    delivered_away, away_error = self._deliver_immediate_reminder_from_evidence(
                        evidence=evidence,
                        current_time=current_time,
                        state=FocusVisionState.AWAY_PENDING_SCAN,
                        immediate_phone_reminder_due=False,
                        immediate_away_reminder_due=True,
                    )
                    self._away_warned_this_episode = True
                    tracking_state = "away_warned"
                else:
                    immediate_scan_started = self._trigger_immediate_away_scan_if_due(
                        now=current_time,
                        hard_person_visible=False,
                    )

        else:
            # ---- FACE_ABSENT (fresh no-face frame) ---------------------------
            self._face_locked_since = None
            self._stale_hold_since = None
            if self._away_warned_this_episode:
                # ---- AWAY_WARNED: hold, do not scan again --------------------
                tracking_state = "away_warned_holding"
            else:
                # Count consecutive fresh no-face ticks.
                if self._face_lost_since is None:
                    self._face_lost_since = current_time
                _face_lost_seconds = current_time - self._face_lost_since
                _acc_absent_seconds = self._evidence_accumulator.person_absent_seconds(now=current_time)
                _effective_absent_seconds = max(
                    _face_lost_seconds,
                    _acc_absent_seconds if _acc_absent_seconds is not None else 0.0,
                )
                # Skip debounce if a scan was already triggered/completed for this episode.
                _scan_already_ran = (
                    self._last_focus_scan_result is not None
                    and self._last_focus_scan_result.scan_type == "away_recheck"
                )

                if _effective_absent_seconds < self.config.face_lost_debounce_seconds and not _scan_already_ran:
                    # ---- FACE_LOST_DEBOUNCE: hold position ------------------
                    tracking_state = "face_lost_debounce"
                else:
                    # ---- FACE_REACQUIRE_SCAN or away check ------------------
                    tracking_state = "face_reacquire"
                    decision = self.decision_engine.decide(observation, observed_at=current_time)
                    snapshot_state = (
                        FocusVisionState.NO_OBSERVATION
                        if observation is None
                        else FocusVisionState.ABSENT
                    )
                    snapshot = FocusVisionStateSnapshot(
                        current_state=snapshot_state,
                        stable_seconds=0.0,
                        state_started_at=current_time,
                        updated_at=current_time,
                        decision=decision,
                    )
                    immediate_away_due, away_reason = self._away_soft_due_from_scan(
                        snapshot,
                        person_seen=False,
                    )
                    if immediate_away_due:
                        delivered_away, away_error = self._deliver_immediate_reminder_from_evidence(
                            evidence=evidence,
                            current_time=current_time,
                            state=FocusVisionState.AWAY_PENDING_SCAN,
                            immediate_phone_reminder_due=False,
                            immediate_away_reminder_due=True,
                        )
                        # Scan confirmed absence — enter AWAY_WARNED regardless of delivery success.
                        self._away_warned_this_episode = True
                        tracking_state = "away_warned"
                    else:
                        immediate_scan_started = self._trigger_immediate_away_scan_if_due(
                            now=current_time,
                            hard_person_visible=False,
                        )

        if stale:
            stale_reason = (
                "stale_observation_hold"
                if tracking_state == "stale_observation_hold"
                else "stale_hold_timeout_face_reacquire"
            )
            status = self._tracking_status(
                focus_tracking_active=False,
                tracking_target_type=self._tracking_target_type_from_evidence(evidence),
                tracking_move_executed=False,
                reason=stale_reason,
                observation_age_seconds=age_seconds,
                observation_source=source,
                observation_stale=True,
            )
        elif hard_face_visible:
            status = self._track_visible_person_from_observation(
                observation=observation,
                evidence=evidence,
                current_time=current_time,
                latency=latency,
            )
        else:
            reason_for_status = tracking_state if tracking_state != "face_reacquire" else "no_hard_person_visible"
            status = self._tracking_status(
                focus_tracking_active=False,
                tracking_target_type="none",
                tracking_move_executed=False,
                reason=reason_for_status,
                observation_age_seconds=age_seconds,
                observation_source=source,
            )

        status.update(
            {
                "phone_reminder_delivered": delivered_phone,
                "phone_reminder_delivery_error": phone_error,
                "immediate_phone_reminder_due": phone_person_evidence,
                "immediate_away_scan_triggered": immediate_scan_started,
                "immediate_away_scan_started": immediate_scan_started,
                "immediate_away_reminder_due": immediate_away_due,
                "immediate_away_reminder_reason": away_reason,
                "away_reminder_delivered": delivered_away,
                "away_reminder_delivery_error": away_error,
                "hard_person_visible": hard_person_visible,
                "hard_face_visible": hard_face_visible,
                "phone_object_detected": evidence.phone_object_detected,
                "phone_candidate_detected": evidence.phone_candidate_detected,
                "phone_candidate_confidence": evidence.phone_candidate_confidence,
                "phone_detection_source": evidence.phone_detection_source,
                "face_count": evidence.face_count,
                "yolo_person_count": evidence.yolo_person_count,
                "people_count": evidence.people_count,
                "person_without_face": evidence.person_without_face,
                "object_labels": [label for label in evidence.labels if label.startswith("object:")],
                "observation_age_seconds": age_seconds,
                "observation_source": source,
                "observation_stale": stale,
                "camera_frame_fresh": observation is not None and not stale,
                "camera_unavailable": observation is None,
                "tracking_state": tracking_state,
                "away_warned_this_episode": self._away_warned_this_episode,
                "face_lost_seconds": (
                    round(current_time - self._face_lost_since, 3)
                    if self._face_lost_since is not None and not hard_face_visible
                    else 0.0
                ),
                "stale_hold_seconds": (
                    round(current_time - self._stale_hold_since, 3)
                    if self._stale_hold_since is not None and stale
                    else 0.0
                ),
                "stale_hold_timeout_reached": bool(
                    stale
                    and self._stale_hold_since is not None
                    and (current_time - self._stale_hold_since) >= self.config.face_stale_hold_max_seconds
                ),
                "stale_hold_transition": "face_reacquire" if tracking_state == "face_reacquire" and stale else "",
                "tracking_worker_step_seconds": round(time.perf_counter() - step_started, 6),
                **latency,
            }
        )
        return self._record_tracking_status(status)

    def _latest_cached_observation_for_tracking(self) -> tuple[Any, str]:
        observation, source, _elapsed = self._latest_cached_observation_for_tracking_timed()
        return observation, source

    def _latest_cached_observation_for_tracking_timed(self) -> tuple[Any, str, float]:
        started = time.perf_counter()
        method = getattr(self.vision_backend, "latest_observation", None)
        if not callable(method):
            return None, "missing_backend_method", round(time.perf_counter() - started, 6)
        try:
            return method(force_refresh=False), "backend_cached", round(time.perf_counter() - started, 6)
        except Exception as error:
            self._last_error = f"{error.__class__.__name__}: {error}"
            return None, "backend_cached_error", round(time.perf_counter() - started, 6)

    def _is_tracking_observation_stale(self, observation_age_seconds: float | None) -> bool:
        if observation_age_seconds is None:
            return False
        if self.config.tracking_max_observation_age_seconds <= 0.0:
            return False
        return observation_age_seconds > self.config.tracking_max_observation_age_seconds

    def _deliver_immediate_reminder_from_evidence(
        self,
        *,
        evidence: FocusVisionEvidence,
        current_time: float,
        state: FocusVisionState,
        immediate_phone_reminder_due: bool,
        immediate_away_reminder_due: bool,
    ) -> tuple[bool, str | None]:
        decision = FocusVisionDecision(
            state=state,
            confidence=1.0,
            reasons=("immediate_focus_worker",),
            observed_at=current_time,
            evidence=evidence,
        )
        snapshot = FocusVisionStateSnapshot(
            current_state=state,
            stable_seconds=0.0,
            state_started_at=current_time,
            updated_at=current_time,
            decision=decision,
        )
        assert self.reminder_policy is not None
        with self._policy_lock:
            reminder = self.reminder_policy.evaluate(
                snapshot,
                language=self._language,
                now=current_time,
                person_absent_seconds=0.0,
                phone_accumulated_seconds=None,
                immediate_phone_reminder_due=immediate_phone_reminder_due,
                immediate_away_reminder_due=immediate_away_reminder_due,
            )
        if reminder is None:
            return False, None
        return self._deliver_reminder(reminder)

    def _latest_observation_for_decision(self, *, current_time: float):
        observation = self._latest_observation()
        if observation is None:
            refreshed = self._latest_observation_force_refresh_with_timeout(
                timeout_seconds=self.config.observation_refresh_timeout_seconds,
            )
            if refreshed is not None:
                self._last_observation_source = "backend_forced_reactive"
                self._last_observation_age_seconds = self._observation_age_seconds(
                    refreshed,
                    current_time=current_time,
                )
                self._last_observation_stale = self._is_reactive_observation_stale(
                    self._last_observation_age_seconds,
                )
                if not self._last_observation_stale:
                    return refreshed
            self._last_observation_age_seconds = None
            self._last_observation_stale = False
            self._schedule_force_refresh(current_time=current_time, reason="missing_observation")
            return None

        observation_age = self._observation_age_seconds(observation, current_time=current_time)
        stale = self._is_observation_stale(observation_age)
        reactive_stale = self._is_reactive_observation_stale(observation_age)
        self._last_observation_age_seconds = observation_age
        self._last_observation_stale = stale or reactive_stale
        if reactive_stale:
            refreshed = self._latest_observation_force_refresh_with_timeout(
                timeout_seconds=self.config.observation_refresh_timeout_seconds,
            )
            if refreshed is not None:
                refreshed_age = self._observation_age_seconds(refreshed, current_time=current_time)
                self._last_observation_age_seconds = refreshed_age
                self._last_observation_stale = self._is_reactive_observation_stale(refreshed_age)
                if not self._last_observation_stale:
                    self._last_observation_source = "backend_forced_reactive"
                    return refreshed
            self._schedule_force_refresh(current_time=current_time, reason="stale_reactive_observation")
            return None
        if stale:
            self._schedule_force_refresh(current_time=current_time, reason="stale_observation")
            return None
        return observation

    def _latest_observation(self):
        method = getattr(self.vision_backend, "latest_observation", None)
        if not callable(method):
            self._last_observation_source = "missing_backend_method"
            return None

        observation = method(force_refresh=self.config.latest_observation_force_refresh)
        if observation is not None:
            self._last_observation_source = "backend_forced" if self.config.latest_observation_force_refresh else "backend_cached"
            return observation

        with self._lock:
            forced_observation = self._last_forced_observation
        if forced_observation is not None:
            self._last_observation_source = "service_forced_cache"
            return forced_observation

        self._last_observation_source = "none"
        return None

    def _schedule_force_refresh(self, *, current_time: float, reason: str) -> bool:
        if not self.config.cache_miss_force_refresh_enabled:
            return False

        with self._lock:
            if self._force_refresh_in_progress:
                return False
            if self._last_force_refresh_started_at is not None:
                elapsed = max(0.0, current_time - self._last_force_refresh_started_at)
                if elapsed < self.config.cache_miss_force_refresh_cooldown_seconds:
                    return False

            self._force_refresh_in_progress = True
            self._last_force_refresh_started_at = current_time
            self._last_force_refresh_reason = reason
            self._last_force_refresh_error = None
            self._last_force_refresh_returned_observation = False

        thread = threading.Thread(
            target=self._run_force_refresh,
            name="nexa-focus-vision-force-refresh",
            daemon=True,
            args=(reason,),
        )
        thread.start()
        return True

    def _run_force_refresh(self, reason: str) -> None:
        finished_at = time.monotonic()
        returned_observation = False
        error_text: str | None = None
        observation = None
        try:
            method = getattr(self.vision_backend, "latest_observation", None)
            if not callable(method):
                error_text = "missing_backend_method"
            else:
                observation = method(force_refresh=True)
                returned_observation = observation is not None
        except Exception as error:
            error_text = f"{error.__class__.__name__}: {error}"
        finally:
            finished_at = time.monotonic()
            with self._lock:
                if observation is not None:
                    self._last_forced_observation = observation
                self._force_refresh_in_progress = False
                self._last_force_refresh_finished_at = finished_at
                self._last_force_refresh_reason = reason
                self._last_force_refresh_error = error_text
                self._last_force_refresh_returned_observation = returned_observation

    @staticmethod
    def _observation_age_seconds(observation, *, current_time: float) -> float | None:
        if observation is None:
            return None
        try:
            captured_at = float(getattr(observation, "captured_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            return None
        if captured_at <= 0.0:
            return None
        return round(max(0.0, current_time - captured_at), 3)

    def _is_observation_stale(self, observation_age_seconds: float | None) -> bool:
        if observation_age_seconds is None:
            return False
        if self.config.max_observation_age_seconds <= 0.0:
            return False
        return observation_age_seconds > self.config.max_observation_age_seconds

    def _is_reactive_observation_stale(self, observation_age_seconds: float | None) -> bool:
        if observation_age_seconds is None:
            return False
        if self.config.reactive_max_observation_age_seconds <= 0.0:
            return False
        return observation_age_seconds > self.config.reactive_max_observation_age_seconds

    def _latest_observation_force_refresh_with_timeout(self, *, timeout_seconds: float):
        method = getattr(self.vision_backend, "latest_observation", None)
        if not callable(method):
            self._last_force_refresh_error = "missing_backend_method"
            self._last_force_refresh_returned_observation = False
            return None
        result = self._call_with_timeout(
            lambda: method(force_refresh=True),
            timeout_seconds=timeout_seconds,
        )
        if result.get("timeout"):
            self._last_force_refresh_error = "force_refresh_timeout"
            self._last_force_refresh_returned_observation = False
            return None
        if result.get("error") is not None:
            self._last_force_refresh_error = str(result["error"])
            self._last_force_refresh_returned_observation = False
            return None
        observation = result.get("value")
        self._last_force_refresh_returned_observation = observation is not None
        return observation

    @staticmethod
    def _call_with_timeout(callback: Callable[[], Any], *, timeout_seconds: float) -> dict[str, Any]:
        result: dict[str, Any] = {"value": None, "error": None, "timeout": False}

        def _call() -> None:
            try:
                result["value"] = callback()
            except Exception as error:
                result["error"] = f"{error.__class__.__name__}: {error}"

        thread = threading.Thread(
            target=_call,
            name="nexa-focus-vision-timeout-call",
            daemon=True,
        )
        thread.start()
        thread.join(timeout=max(0.05, float(timeout_seconds)))
        if thread.is_alive():
            result["timeout"] = True
        return result

    def _write_telemetry(
        self,
        result: FocusVisionTickResult,
        *,
        current_time: float,
        phone_person_evidence: bool | None = None,
        immediate_phone_reminder_due: bool = False,
        immediate_away_scan_triggered: bool = False,
        immediate_away_reminder_due: bool = False,
        hard_person_visible: bool | None = None,
        tracking_status: dict[str, Any] | None = None,
        away_soft_due_from_scan: bool = False,
        away_soft_due_reason: str = "",
    ) -> None:
        if self.telemetry is None:
            return
        snap = result.snapshot
        current_state = snap.current_state if snap is not None else None
        stable_s = snap.stable_seconds if snap is not None else 0.0
        evidence = getattr(getattr(snap, "decision", None), "evidence", FocusVisionEvidence())
        acc = self._evidence_accumulator
        _person_absent_sec = acc.person_absent_seconds(now=current_time) if acc is not None else None
        _phone_acc_sec = acc.phone_accumulated_seconds() if acc is not None else 0.0
        _phone_first_seen_sec = (
            acc.phone_first_seen_seconds_ago(now=current_time) if acc is not None else None
        )
        _phone_gap_sec = acc.phone_gap_seconds() if acc is not None else 0.0
        raw_phone_object_detected = bool(
            set(getattr(evidence, "labels", ()) or ())
            & {"object:cell phone", "object:mobile phone", "object:phone"}
        )
        if phone_person_evidence is None:
            phone_person_evidence = self._has_phone_person_evidence(evidence)
        if hard_person_visible is None:
            hard_person_visible = self._has_hard_visual_person(evidence)
        tracking_status = dict(tracking_status or self._last_tracking_status or {})
        last_person_s_ago = round(_person_absent_sec, 1) if _person_absent_sec is not None else None
        away_soft_allowed = (
            current_state == FocusVisionState.AWAY_PENDING_SCAN
            and (
                (_person_absent_sec is not None and _person_absent_sec >= self.config.away_soft_reminder_after_seconds)
                or stable_s >= self.config.away_soft_reminder_after_seconds
            )
        )
        last_scan = self._last_focus_scan_result
        away_recheck_scan_completed = bool(
            last_scan is not None
            and last_scan.scan_type == "away_recheck"
            and last_scan.completed_at is not None
        )
        away_recheck_person_found = (
            bool(last_scan.person_found) if away_recheck_scan_completed else None
        )
        active_scan_id = last_scan.scan_id if last_scan is not None else self._active_focus_scan_id
        active_scan_type = last_scan.scan_type if last_scan is not None else self._active_focus_scan_type
        active_scan_points = list(last_scan.scan_point_results) if last_scan is not None else []
        self.telemetry.append(
            {
                "event": "focus_vision_tick",
                "created_at": current_time,
                "current_state": current_state.value if current_state is not None else None,
                "face_count": evidence.face_count,
                "yolo_person_count": evidence.yolo_person_count,
                "people_count": evidence.people_count,
                "person_without_face": evidence.person_without_face,
                "hard_person_visible": bool(hard_person_visible),
                "phone_object_detected": evidence.phone_object_detected,
                "phone_candidate_detected": evidence.phone_candidate_detected,
                "phone_candidate_confidence": evidence.phone_candidate_confidence,
                "phone_detection_source": evidence.phone_detection_source,
                "immediate_phone_reminder_due": bool(immediate_phone_reminder_due),
                "immediate_away_scan_triggered": bool(immediate_away_scan_triggered),
                "immediate_away_scan_started": bool(immediate_away_scan_triggered),
                "immediate_away_scan_completed": bool(
                    last_scan is not None
                    and last_scan.scan_type == "away_recheck"
                    and last_scan.completed_at is not None
                ),
                "immediate_away_scan_failed": bool(
                    last_scan is not None
                    and last_scan.scan_type == "away_recheck"
                    and last_scan.completed_at is not None
                    and last_scan.blocked
                    and not last_scan.camera_available
                ),
                "immediate_away_reminder_due": bool(immediate_away_reminder_due),
                "immediate_away_reminder_reason": away_soft_due_reason,
                "reminder_kind": result.reminder.kind.value if result.reminder is not None else None,
                "reminder_delivered": result.reminder_delivered,
                "observation_source": self._last_observation_source,
                "observation_age_seconds": self._last_observation_age_seconds,
                "observation_stale": self._last_observation_stale,
                "camera_frame_fresh": not bool(self._last_observation_stale),
                "camera_unavailable": current_state == FocusVisionState.NO_OBSERVATION,
                "focus_tracking_active": bool(tracking_status.get("focus_tracking_active", False)),
                "tracking_target_type": str(tracking_status.get("tracking_target_type", "none") or "none"),
                "tracking_move_executed": bool(tracking_status.get("tracking_move_executed", False)),
                "tracking_move_degrees": dict(tracking_status.get("tracking_move_degrees", {}) or {}),
                "tracking_reason": str(tracking_status.get("tracking_reason", tracking_status.get("reason", "")) or ""),
                "vision_tracking_service_available": bool(tracking_status.get("vision_tracking_service_available", self.vision_tracking_service is not None)),
                "pan_tilt_backend_available": bool(tracking_status.get("pan_tilt_backend_available", self.pan_tilt_backend is not None)),
                "continuous_tracking_enabled": bool(tracking_status.get("continuous_tracking_enabled", self.config.continuous_tracking_enabled)),
                "tracking_plan_has_target": bool(tracking_status.get("tracking_plan_has_target", False)),
                "tracking_backend_command_executed": bool(tracking_status.get("tracking_backend_command_executed", False)),
                "pan_tilt_move_blocked_reason": str(tracking_status.get("pan_tilt_move_blocked_reason", "") or ""),
                "missing_safety_gates": list(tracking_status.get("missing_safety_gates", []) or []),
                "tracking_smooth_limited": bool(tracking_status.get("tracking_smooth_limited", False)),
                "phone_reminder_delivered": bool(
                    result.reminder_delivered
                    and result.reminder is not None
                    and result.reminder.kind.value == "phone_distraction"
                ),
                "away_reminder_delivered": bool(
                    result.reminder_delivered
                    and result.reminder is not None
                    and result.reminder.kind.value == "away_soft"
                ),
                "force_refresh": {
                    "in_progress": self._force_refresh_in_progress,
                    "last_reason": self._last_force_refresh_reason,
                    "last_error": self._last_force_refresh_error,
                    "returned_observation": self._last_force_refresh_returned_observation,
                },
                "scan_id": active_scan_id,
                "scan_type": active_scan_type,
                "scan_points": active_scan_points,
                "scan_duration_seconds": (
                    round(max(0.0, float(last_scan.completed_at) - float(last_scan.triggered_at)), 3)
                    if last_scan is not None and last_scan.completed_at is not None
                    else None
                ),
                "visual_shell_started": None,
                "visual_shell_launch_command": [],
                "visual_shell_transport_ready": None,
                "behavior_presence_ignored_for_scan": True,
                "stale_observation_ignored": bool(
                    self._last_observation_stale
                    or (last_scan is not None and last_scan.stale_observation_ignored)
                ),
                "mobile_base_movement_attempted": False,
                "language": self._language,
                "dry_run": self.config.dry_run,
                "last_error": self._last_error,
                "latest_observation_force_refresh": self.config.latest_observation_force_refresh,
                "cache_miss_force_refresh_enabled": self.config.cache_miss_force_refresh_enabled,
                "force_refresh_in_progress": self._force_refresh_in_progress,
                "last_force_refresh_reason": self._last_force_refresh_reason,
                "last_force_refresh_error": self._last_force_refresh_error,
                "last_force_refresh_returned_observation": self._last_force_refresh_returned_observation,
                "observation_source": self._last_observation_source,
                "observation_age_seconds": self._last_observation_age_seconds,
                "observation_stale": self._last_observation_stale,
                "diagnostics": {
                    "phone_distraction_stable_seconds": stable_s if current_state == FocusVisionState.PHONE_DISTRACTION else 0.0,
                    "phone_distraction_reminder_after_seconds": self.config.phone_warning_after_seconds,
                    "phone_accumulated_seconds": _phone_acc_sec,
                    "raw_phone_object_detected": raw_phone_object_detected,
                    "phone_person_evidence": bool(phone_person_evidence),
                    "phone_first_seen_seconds_ago": (
                        round(_phone_first_seen_sec, 1)
                        if _phone_first_seen_sec is not None
                        else None
                    ),
                    "phone_evidence_elapsed_seconds": round(_phone_acc_sec, 1),
                    "phone_gap_seconds": round(_phone_gap_sec, 1),
                    "phone_reminder_due": bool(
                        result.reminder is not None
                        and result.reminder.kind.value == "phone_distraction"
                    ),
                    "immediate_phone_reminder_due": bool(immediate_phone_reminder_due),
                    "phone_reminder_after_seconds": self.config.phone_warning_after_seconds,
                    "away_absence_seconds": stable_s if current_state in (FocusVisionState.ABSENT, FocusVisionState.AWAY_PENDING_SCAN) else 0.0,
                    "away_soft_reminder_after_seconds": self.config.away_soft_reminder_after_seconds,
                    "away_soft_reminder_allowed": away_soft_allowed,
                    "away_recheck_scan_completed": away_recheck_scan_completed,
                    "away_recheck_person_found": away_recheck_person_found,
                    "away_soft_due_from_scan": bool(away_soft_due_from_scan),
                    "immediate_away_scan_triggered": bool(immediate_away_scan_triggered),
                    "immediate_away_scan_completed": bool(
                        last_scan is not None
                        and last_scan.scan_type == "away_recheck"
                        and last_scan.completed_at is not None
                    ),
                    "immediate_away_scan_failed": bool(
                        last_scan is not None
                        and last_scan.scan_type == "away_recheck"
                        and last_scan.completed_at is not None
                        and last_scan.blocked
                        and not last_scan.camera_available
                    ),
                    "immediate_away_reminder_due": bool(immediate_away_reminder_due),
                    "immediate_away_reminder_reason": away_soft_due_reason,
                    "away_soft_due_reason": away_soft_due_reason,
                    "person_absent_seconds": last_person_s_ago,
                    "last_person_evidence_seconds_ago": last_person_s_ago,
                    "reminder_kind": result.reminder.kind.value if result.reminder is not None else None,
                    "focus_scan_running": self._focus_scan_running,
                    "last_focus_scan": None if self._last_focus_scan_result is None else self._last_focus_scan_result.to_dict(),
                    "focus_tracking": tracking_status,
                },
                **result.to_dict(),
            }
        )

    def _write_tracking_telemetry(self, status: dict[str, Any], *, current_time: float) -> None:
        if self.telemetry is None:
            return
        last_scan = self._last_focus_scan_result
        active_scan_id = last_scan.scan_id if last_scan is not None else self._active_focus_scan_id
        active_scan_type = last_scan.scan_type if last_scan is not None else self._active_focus_scan_type
        active_scan_points = list(last_scan.scan_point_results) if last_scan is not None else []
        self.telemetry.append(
            {
                "event": "focus_vision_tracking_tick",
                "created_at": current_time,
                "current_state": None,
                "face_count": int(status.get("face_count", 0) or 0),
                "yolo_person_count": int(status.get("yolo_person_count", 0) or 0),
                "people_count": int(status.get("people_count", 0) or 0),
                "person_without_face": bool(status.get("person_without_face", False)),
                "hard_person_visible": bool(status.get("hard_person_visible", False)),
                "phone_object_detected": bool(status.get("phone_object_detected", False)),
                "phone_candidate_detected": bool(status.get("phone_candidate_detected", False)),
                "phone_candidate_confidence": float(status.get("phone_candidate_confidence", 0.0) or 0.0),
                "phone_detection_source": str(status.get("phone_detection_source", "") or ""),
                "focus_tracking_active": bool(status.get("focus_tracking_active", False)),
                "tracking_target_type": str(status.get("tracking_target_type", "none") or "none"),
                "tracking_move_executed": bool(status.get("tracking_move_executed", False)),
                "tracking_move_degrees": dict(status.get("tracking_move_degrees", {}) or {}),
                "tracking_reason": str(status.get("tracking_reason", status.get("reason", "")) or ""),
                "tracking_smooth_limited": bool(status.get("tracking_smooth_limited", False)),
                "vision_tracking_service_available": bool(status.get("vision_tracking_service_available", self.vision_tracking_service is not None)),
                "pan_tilt_backend_available": bool(status.get("pan_tilt_backend_available", self.pan_tilt_backend is not None)),
                "continuous_tracking_enabled": bool(status.get("continuous_tracking_enabled", self.config.continuous_tracking_enabled)),
                "tracking_plan_has_target": bool(status.get("tracking_plan_has_target", False)),
                "tracking_backend_command_executed": bool(status.get("tracking_backend_command_executed", False)),
                "pan_tilt_move_blocked_reason": str(status.get("pan_tilt_move_blocked_reason", "") or ""),
                "missing_safety_gates": list(status.get("missing_safety_gates", []) or []),
                "tracking_backend_response": dict(status.get("tracking_backend_response", {}) or {}),
                "tracking_target": dict(status.get("tracking_target", {}) or {}),
                "latest_observation_seconds": status.get("latest_observation_seconds"),
                "evidence_read_seconds": status.get("evidence_read_seconds"),
                "target_selection_seconds": status.get("target_selection_seconds"),
                "planning_seconds": status.get("planning_seconds"),
                "pan_tilt_move_delta_seconds": status.get("pan_tilt_move_delta_seconds"),
                "telemetry_write_seconds": status.get("telemetry_write_seconds"),
                "tracking_worker_step_seconds": status.get("tracking_worker_step_seconds"),
                "scan_cancelled": bool(status.get("scan_cancelled", False)),
                "scan_cancel_reason": str(status.get("scan_cancel_reason", "") or ""),
                "raw_tilt_delta_degrees": status.get("raw_tilt_delta_degrees"),
                "final_tilt_delta_degrees": status.get("final_tilt_delta_degrees"),
                "current_tilt_degrees": status.get("current_tilt_degrees"),
                "focus_tilt_center_degrees": status.get("focus_tilt_center_degrees"),
                "tilt_clamped_to_center": bool(status.get("tilt_clamped_to_center", False)),
                "tilt_clamp_reason": str(status.get("tilt_clamp_reason", "") or ""),
                "stale_hold_seconds": status.get("stale_hold_seconds"),
                "stale_hold_timeout_reached": bool(status.get("stale_hold_timeout_reached", False)),
                "stale_hold_transition": str(status.get("stale_hold_transition", "") or ""),
                "immediate_phone_reminder_due": bool(status.get("immediate_phone_reminder_due", False)),
                "phone_reminder_delivered": bool(status.get("phone_reminder_delivered", False)),
                "immediate_away_scan_triggered": bool(status.get("immediate_away_scan_triggered", False)),
                "immediate_away_scan_started": bool(status.get("immediate_away_scan_started", False)),
                "immediate_away_scan_completed": bool(
                    last_scan is not None
                    and last_scan.scan_type == "away_recheck"
                    and last_scan.completed_at is not None
                ),
                "immediate_away_scan_failed": bool(
                    last_scan is not None
                    and last_scan.scan_type == "away_recheck"
                    and last_scan.completed_at is not None
                    and last_scan.blocked
                    and not last_scan.camera_available
                ),
                "immediate_away_reminder_due": bool(status.get("immediate_away_reminder_due", False)),
                "immediate_away_reminder_reason": str(status.get("immediate_away_reminder_reason", "") or ""),
                "away_reminder_delivered": bool(status.get("away_reminder_delivered", False)),
                "reminder_delivered": bool(status.get("phone_reminder_delivered", False) or status.get("away_reminder_delivered", False)),
                "observation_age_seconds": status.get("observation_age_seconds"),
                "observation_source": str(status.get("observation_source", self._last_observation_source) or ""),
                "observation_stale": bool(status.get("observation_stale", False)),
                "camera_frame_fresh": bool(status.get("camera_frame_fresh", False)),
                "camera_unavailable": bool(status.get("camera_unavailable", False)),
                "force_refresh": {
                    "in_progress": self._force_refresh_in_progress,
                    "last_reason": self._last_force_refresh_reason,
                    "last_error": self._last_force_refresh_error,
                    "returned_observation": self._last_force_refresh_returned_observation,
                },
                "scan_id": active_scan_id,
                "scan_type": active_scan_type,
                "scan_points": active_scan_points,
                "mobile_base_movement_attempted": False,
                "behavior_presence_ignored_for_scan": True,
                "stale_observation_ignored": bool(status.get("observation_stale", False)),
                "diagnostics": {"focus_tracking": dict(status)},
            }
        )

    @staticmethod
    def _has_person_evidence(evidence: FocusVisionEvidence) -> bool:
        return bool(
            evidence.face_count > 0
            or evidence.people_count > 0
            or evidence.yolo_person_count > 0
            or evidence.person_without_face
        )

    @staticmethod
    def _has_hard_visual_person(evidence: FocusVisionEvidence) -> bool:
        """Fresh visual person evidence only, excluding behavior/session presence."""
        labels = set(evidence.labels)
        return bool(
            evidence.face_count > 0
            or evidence.yolo_person_count > 0
            or "object:person" in labels
            or evidence.person_without_face
        )

    @staticmethod
    def _has_fresh_face(evidence: FocusVisionEvidence) -> bool:
        return evidence.face_count > 0

    @staticmethod
    def _has_hard_phone_evidence(evidence: FocusVisionEvidence) -> bool:
        labels = set(evidence.labels)
        return bool(
            evidence.phone_object_detected
            or (evidence.phone_candidate_detected and evidence.phone_candidate_confidence >= 0.5)
            or labels.intersection({"object:cell phone", "object:mobile phone", "object:phone"})
        )

    def _has_phone_person_evidence(self, evidence: FocusVisionEvidence) -> bool:
        return bool(self._has_hard_phone_evidence(evidence) and self._has_hard_visual_person(evidence))

    def _track_visible_person_from_observation(
        self,
        *,
        observation: Any,
        evidence: FocusVisionEvidence,
        current_time: float,
        latency: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        latency = latency if latency is not None else {}
        target_type = self._tracking_target_type_from_evidence(evidence)

        target_started = time.perf_counter()
        raw_target = self._tracking_selector.select(observation)
        latency["target_selection_seconds"] = round(time.perf_counter() - target_started, 6)
        if raw_target is None or raw_target.target_type != "face" or self._tracking_planner is None:
            return self._tracking_status(
                focus_tracking_active=False,
                tracking_target_type="none",
                tracking_move_executed=False,
                reason="face_visible_no_tracking_box" if target_type == "face" else "no_face_tracking_target",
                tracking_plan_has_target=False,
                observation_age_seconds=self._last_observation_age_seconds,
                observation_source=self._last_observation_source,
            )

        target_type = raw_target.target_type
        planning_started = time.perf_counter()
        command = self._tracking_planner.plan(
            face_x_norm=raw_target.center_x_norm,
            face_y_norm=raw_target.center_y_norm,
        )
        latency["planning_seconds"] = round(time.perf_counter() - planning_started, 6)
        pan_delta = command.pan_delta_degrees
        raw_tilt_delta = command.tilt_delta_degrees
        tilt_delta = raw_tilt_delta

        if self.pan_tilt_backend is None:
            return self._tracking_status(
                focus_tracking_active=True,
                tracking_target_type=target_type,
                tracking_move_executed=False,
                reason="pan_tilt_backend_unavailable",
                tracking_plan_has_target=True,
                observation_age_seconds=self._last_observation_age_seconds,
                observation_source=self._last_observation_source,
            )

        pan_delta = self._limit_tracking_delta(pan_delta, axis="pan")
        tilt_delta = self._limit_tracking_delta(tilt_delta, axis="tilt")

        # Clamp tilt: never go below center (tilt_angle = 0°) in Focus Mode.
        # Default to current_tilt=0 so any downward move is clamped when status is unavailable.
        tilt_clamped_to_center = False
        tilt_clamp_reason = ""
        _current_tilt = 0.0
        _pt_status_method = getattr(self.pan_tilt_backend, "status", None)
        if callable(_pt_status_method):
            try:
                _pt_status = _pt_status_method()
                _current_tilt = float(_pt_status.get("tilt_angle", 0.0) or 0.0)
            except Exception:
                pass  # _current_tilt stays 0.0: clamp all downward tilt
        if tilt_delta < 0.0:
            tilt_delta = 0.0
            tilt_clamped_to_center = True
            tilt_clamp_reason = "focus_mode_no_downward_tilt"

        if abs(pan_delta) < self.config.tracking_min_move_degrees:
            pan_delta = 0.0
        if abs(tilt_delta) < self.config.tracking_min_move_degrees:
            tilt_delta = 0.0
        movement_requested = abs(pan_delta) > 0.0 or abs(tilt_delta) > 0.0

        # Command coalescing: suppress repeated near-identical commands sent in rapid succession.
        _coalesced = False
        if movement_requested and self._last_tracking_command_at is not None:
            _since_last = current_time - self._last_tracking_command_at
            if (
                _since_last < self.config.focus_tracking_command_coalesce_seconds
                and abs(pan_delta - self._last_tracking_pan_delta)
                    < self.config.focus_tracking_command_change_threshold_degrees
                and abs(tilt_delta - self._last_tracking_tilt_delta)
                    < self.config.focus_tracking_command_change_threshold_degrees
            ):
                _coalesced = True

        move_response: dict[str, Any] = {}
        move_executed = False
        blocked_reason = ""
        missing_gates: list[str] = []
        if _coalesced:
            blocked_reason = "command_coalesced"
        elif movement_requested:
            move_delta = getattr(self.pan_tilt_backend, "move_delta", None)
            if not callable(move_delta):
                blocked_reason = "backend_move_delta_unavailable"
            else:
                try:
                    move_started = time.perf_counter()
                    response = move_delta(
                        pan_delta_degrees=pan_delta,
                        tilt_delta_degrees=tilt_delta,
                    )
                    latency["pan_tilt_move_delta_seconds"] = round(time.perf_counter() - move_started, 6)
                    move_response = dict(response) if isinstance(response, dict) else {"response": response}
                    move_executed = bool(move_response.get("movement_executed", False))
                    if not move_executed:
                        blocked_reason = str(move_response.get("blocked_reason") or "backend_rejected_move")
                        gates = move_response.get("missing_safety_gates", [])
                        if isinstance(gates, (list, tuple)):
                            missing_gates = [str(gate) for gate in gates]
                except Exception as error:
                    latency["pan_tilt_move_delta_seconds"] = round(time.perf_counter() - move_started, 6) if "move_started" in locals() else 0.0
                    blocked_reason = f"backend_move_delta_error:{error.__class__.__name__}"
                    move_response = {"error": f"{error.__class__.__name__}: {error}"}
        else:
            blocked_reason = "target_centered"

        if move_executed:
            self._last_tracking_command_at = current_time
            self._last_tracking_pan_delta = pan_delta
            self._last_tracking_tilt_delta = tilt_delta

        reason = "tracking_move_executed" if move_executed else blocked_reason
        return self._tracking_status(
            focus_tracking_active=True,
            tracking_target_type=target_type,
            tracking_move_executed=move_executed,
            reason=reason,
            tracking_plan_has_target=True,
            tracking_move_degrees={
                "pan_delta_degrees": round(pan_delta, 4),
                "tilt_delta_degrees": round(tilt_delta, 4),
            },
            tracking_backend_command_executed=move_executed,
            pan_tilt_move_blocked_reason=blocked_reason if not move_executed else "",
            missing_safety_gates=missing_gates,
            tracking_plan_reason=command.reason,
            tracking_adapter_status="",
            tracking_backend_response=move_response,
            observation_age_seconds=self._last_observation_age_seconds,
            observation_source=self._last_observation_source,
            tracking_smooth_limited=(
                abs(pan_delta) >= self.config.tracking_max_pan_step_degrees
                or abs(tilt_delta) >= self.config.tracking_max_tilt_step_degrees
            ),
            extra={
                "raw_tracking_target_found": True,
                "tracking_plan_called": False,
                "created_at": current_time,
                "tilt_clamped_to_center": tilt_clamped_to_center,
                "tilt_clamp_reason": tilt_clamp_reason,
                "raw_tilt_delta_degrees": round(raw_tilt_delta, 4),
                "final_tilt_delta_degrees": round(tilt_delta, 4),
                "current_tilt_degrees": round(_current_tilt, 4),
                "focus_tilt_center_degrees": 0.0,
                "command_coalesced": _coalesced,
                "tracking_target": {
                    "target_type": raw_target.target_type,
                    "center_x_norm": round(raw_target.center_x_norm, 4),
                    "center_y_norm": round(raw_target.center_y_norm, 4),
                    "confidence": round(raw_target.confidence, 4),
                    "box": dict(raw_target.box),
                },
                "face_box_available": raw_target.target_type == "face",
                "person_box_available": raw_target.target_type == "person",
                **latency,
            },
        )

    def _tracking_status(
        self,
        *,
        focus_tracking_active: bool,
        tracking_target_type: str,
        tracking_move_executed: bool,
        reason: str,
        tracking_move_degrees: dict[str, float] | None = None,
        tracking_smooth_limited: bool = False,
        tracking_plan_has_target: bool = False,
        tracking_backend_command_executed: bool = False,
        pan_tilt_move_blocked_reason: str = "",
        missing_safety_gates: list[str] | tuple[str, ...] | None = None,
        tracking_plan_reason: str = "",
        tracking_adapter_status: str = "",
        tracking_backend_response: dict[str, Any] | None = None,
        observation_age_seconds: float | None = None,
        observation_source: str | None = None,
        observation_stale: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = {
            "focus_tracking_active": bool(focus_tracking_active),
            "tracking_target_type": tracking_target_type if tracking_target_type in {"face", "person"} else "none",
            "tracking_move_executed": bool(tracking_move_executed),
            "tracking_move_degrees": tracking_move_degrees or {"pan_delta_degrees": 0.0, "tilt_delta_degrees": 0.0},
            "tracking_smooth_limited": bool(tracking_smooth_limited),
            "tracking_reason": reason,
            "reason": reason,
            "vision_tracking_service_available": self.vision_tracking_service is not None,
            "pan_tilt_backend_available": self.pan_tilt_backend is not None,
            "continuous_tracking_enabled": self.config.continuous_tracking_enabled,
            "tracking_plan_has_target": bool(tracking_plan_has_target),
            "tracking_backend_command_executed": bool(tracking_backend_command_executed),
            "pan_tilt_move_blocked_reason": pan_tilt_move_blocked_reason,
            "missing_safety_gates": list(missing_safety_gates or []),
            "tracking_plan_reason": tracking_plan_reason,
            "tracking_adapter_status": tracking_adapter_status,
            "tracking_backend_response": tracking_backend_response or {},
            "observation_age_seconds": observation_age_seconds,
            "observation_source": observation_source or self._last_observation_source,
            "observation_stale": self._last_observation_stale if observation_stale is None else observation_stale,
            "mobile_base_movement_attempted": False,
        }
        if extra:
            status.update(extra)
        return status

    def _record_tracking_status(self, status: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._last_tracking_status = dict(status)
        return status

    def _limit_tracking_delta(self, value: float, *, axis: str = "pan") -> float:
        if axis == "tilt":
            limit = max(0.1, float(self.config.tracking_max_tilt_step_degrees))
        else:
            limit = max(0.1, float(self.config.tracking_max_pan_step_degrees))
        if value > limit:
            return limit
        if value < -limit:
            return -limit
        return value

    def _track_visible_person(
        self,
        *,
        evidence: FocusVisionEvidence,
        hard_person_visible: bool,
    ) -> dict[str, Any]:
        if not self.config.continuous_tracking_enabled:
            status = {
                "focus_tracking_active": False,
                "tracking_target_type": "none",
                "tracking_move_executed": False,
                "tracking_move_degrees": {},
                "tracking_smooth_limited": False,
                "reason": "continuous_tracking_disabled",
                "mobile_base_movement_attempted": False,
            }
            self._last_tracking_status = status
            return status

        if not hard_person_visible:
            status = {
                "focus_tracking_active": False,
                "tracking_target_type": "none",
                "tracking_move_executed": False,
                "tracking_move_degrees": {},
                "tracking_smooth_limited": False,
                "reason": "no_hard_person_visible",
                "mobile_base_movement_attempted": False,
            }
            self._last_tracking_status = status
            return status

        tracking = self.vision_tracking_service
        if tracking is None:
            status = {
                "focus_tracking_active": False,
                "tracking_target_type": self._tracking_target_type_from_evidence(evidence),
                "tracking_move_executed": False,
                "tracking_move_degrees": {},
                "tracking_smooth_limited": False,
                "reason": "vision_tracking_service_unavailable",
                "mobile_base_movement_attempted": False,
            }
            self._last_tracking_status = status
            return status

        try:
            plan = tracking.plan_once(force_refresh=False)
        except Exception as error:
            status = {
                "focus_tracking_active": False,
                "tracking_target_type": self._tracking_target_type_from_evidence(evidence),
                "tracking_move_executed": False,
                "tracking_move_degrees": {},
                "tracking_smooth_limited": False,
                "reason": f"tracking_plan_failed:{error.__class__.__name__}",
                "mobile_base_movement_attempted": False,
            }
            self._last_tracking_status = status
            return status

        plan_payload = _to_mapping(plan)
        adapter_result = None
        adapter_method = getattr(tracking, "latest_pan_tilt_adapter_result", None)
        if callable(adapter_method):
            adapter_result = adapter_method()
        adapter_payload = _to_mapping(adapter_result)
        target_payload = _to_mapping(plan_payload.get("target"))
        target_type = str(target_payload.get("target_type") or self._tracking_target_type_from_evidence(evidence))
        pan_delta = _safe_float(plan_payload.get("pan_delta_degrees", 0.0))
        tilt_delta = _safe_float(plan_payload.get("tilt_delta_degrees", 0.0))
        adapter_executed = bool(adapter_payload.get("backend_command_executed", False))
        move_executed = adapter_executed
        move_response: dict[str, Any] = {}

        # If the shared tracking adapter is configured as dry-run, Focus Mode can
        # still use the same tracking plan and send it through the pan-tilt
        # backend's own safety gates. This never touches mobile-base movement.
        if (
            not adapter_executed
            and bool(plan_payload.get("has_target", False))
            and (abs(pan_delta) > 0.0 or abs(tilt_delta) > 0.0)
            and self.pan_tilt_backend is not None
        ):
            move_delta = getattr(self.pan_tilt_backend, "move_delta", None)
            if callable(move_delta):
                try:
                    response = move_delta(
                        pan_delta_degrees=pan_delta,
                        tilt_delta_degrees=tilt_delta,
                    )
                    move_response = dict(response) if isinstance(response, dict) else {"response": response}
                    move_executed = bool(move_response.get("movement_executed", False))
                except Exception as error:
                    move_response = {"error": f"{error.__class__.__name__}: {error}"}

        status = {
            "focus_tracking_active": bool(plan_payload.get("has_target", False)),
            "tracking_target_type": target_type if target_type in {"face", "person"} else "none",
            "tracking_move_executed": bool(move_executed),
            "tracking_move_degrees": {
                "pan_delta_degrees": round(pan_delta, 4),
                "tilt_delta_degrees": round(tilt_delta, 4),
            },
            "tracking_smooth_limited": bool(
                adapter_payload.get("status") == "backend_command_coalesced"
                or abs(pan_delta) >= self.config.scan_pan_degrees
                or abs(tilt_delta) >= self.config.scan_pan_degrees
            ),
            "tracking_plan_reason": str(plan_payload.get("reason", "")),
            "tracking_adapter_status": str(adapter_payload.get("status", "")),
            "tracking_backend_response": move_response,
            "mobile_base_movement_attempted": False,
        }
        self._last_tracking_status = status
        return status

    @staticmethod
    def _tracking_target_type_from_evidence(evidence: FocusVisionEvidence) -> str:
        if evidence.face_count > 0:
            return "face"
        return "none"

    def _trigger_immediate_away_scan_if_due(self, *, now: float, hard_person_visible: bool) -> bool:
        if not self.config.active_monitoring_enabled:
            return False
        if hard_person_visible:
            return False
        acc = self._evidence_accumulator
        sched = self._scan_scheduler
        if acc is None or sched is None:
            return False
        with self._lock:
            self._expire_stuck_focus_scan_locked(now)
            if self._focus_scan_running or self._micro_scan_state == "scanning":
                return False
            if (
                self._last_focus_scan_result is not None
                and self._last_focus_scan_result.scan_type == "away_recheck"
                and self._last_focus_scan_result.completed_at is not None
            ):
                last_person_at = acc.last_person_evidence_at()
                if last_person_at is None or self._last_focus_scan_result.triggered_at > last_person_at:
                    return False
            if (
                self._last_focus_scan_result is not None
                and self._last_focus_scan_result.scan_type == "away_recheck"
                and self._last_focus_scan_result.completed_at is not None
                and self._last_focus_scan_result.scan_blocked_reason == "scan_timeout"
            ):
                return False
            # Clear stale scan evidence from an earlier absence episode.
            self._last_focus_scan_result = None
        sched.record_away_recheck_triggered(now=now)
        self._trigger_focus_scan("away_recheck", now)
        return True

    def _away_soft_due_from_scan(
        self,
        snapshot: FocusVisionStateSnapshot,
        *,
        person_seen: bool,
    ) -> tuple[bool, str]:
        if person_seen:
            return False, "person_evidence_returned"
        scan = self._last_focus_scan_result
        if scan is None:
            return False, ""
        if scan.scan_type != "away_recheck" or scan.completed_at is None:
            return False, ""
        if not scan.camera_available and scan.scan_blocked_reason not in {"scan_timeout", "scan_exception", ""}:
            return False, "camera_unavailable"
        if scan.person_found:
            return False, "person_found"
        # Reject scan result from before person was last seen — it belongs to an old episode.
        acc = self._evidence_accumulator
        if acc is not None:
            last_person_at = acc.last_person_evidence_at()
            if last_person_at is not None and scan.triggered_at <= last_person_at:
                return False, "scan_predates_absence"
        if snapshot.current_state not in (
            FocusVisionState.ABSENT,
            FocusVisionState.AWAY_PENDING_SCAN,
            FocusVisionState.NO_OBSERVATION,
            FocusVisionState.AWAY_CONFIRMED,
        ):
            return False, "state_not_absent"
        return True, "away_recheck_no_person"

    def _apply_derived_presence_states(
        self, snapshot: FocusVisionStateSnapshot, now: float
    ) -> FocusVisionStateSnapshot:
        if snapshot.current_state != FocusVisionState.ABSENT:
            with self._lock:
                if self._micro_scan_state not in ("idle",):
                    self._micro_scan_state = "idle"
                    self._micro_scan_requested_at = None
                    self._micro_scan_blocked_reason = ""
            return snapshot

        if snapshot.stable_seconds < self.config.absence_pending_scan_after_seconds:
            return snapshot

        with self._lock:
            scan_state = self._micro_scan_state

        if scan_state == "idle":
            if self.config.pan_tilt_scan_enabled and self.pan_tilt_backend is not None:
                self._trigger_micro_scan(now)
            else:
                reason = (
                    "pan_tilt_scan_disabled"
                    if not self.config.pan_tilt_scan_enabled
                    else "pan_tilt_backend_missing"
                )
                with self._lock:
                    self._micro_scan_state = "blocked"
                    self._micro_scan_result = "blocked"
                    self._micro_scan_blocked_reason = reason
            return _replace_snapshot_state(snapshot, FocusVisionState.AWAY_PENDING_SCAN)

        if scan_state == "scanning":
            return _replace_snapshot_state(snapshot, FocusVisionState.AWAY_PENDING_SCAN)

        if scan_state == "not_found":
            return _replace_snapshot_state(snapshot, FocusVisionState.AWAY_CONFIRMED)

        if scan_state == "blocked":
            return _replace_snapshot_state(snapshot, FocusVisionState.AWAY_PENDING_SCAN)

        if scan_state == "found":
            with self._lock:
                self._micro_scan_state = "idle"
                self._micro_scan_result = "found"
                self._micro_scan_blocked_reason = ""
            return snapshot

        return snapshot

    def _trigger_micro_scan(self, now: float) -> None:
        with self._lock:
            self._micro_scan_state = "scanning"
            self._micro_scan_requested_at = now
        thread = threading.Thread(
            target=self._run_micro_scan,
            name="nexa-focus-micro-scan",
            daemon=True,
        )
        thread.start()

    def _run_micro_scan(self) -> None:
        result = "blocked"
        try:
            pan_tilt = self.pan_tilt_backend
            if pan_tilt is None:
                result = "blocked"
                return

            any_movement_executed = False

            def _try_move(pan_delta: float) -> None:
                nonlocal any_movement_executed
                move = getattr(pan_tilt, "move_delta", None)
                if callable(move):
                    try:
                        move_result = move(pan_delta_degrees=pan_delta, tilt_delta_degrees=0.0)
                        if isinstance(move_result, dict) and bool(move_result.get("movement_executed")):
                            any_movement_executed = True
                    except Exception:
                        pass

            def _try_center() -> None:
                center = getattr(pan_tilt, "center", None)
                if callable(center):
                    try:
                        center()
                    except Exception:
                        pass

            def _check_person() -> bool:
                found, _cam, _info = self._check_person_for_scan_result()
                return found

            found = False

            if self._stop_event.is_set():
                result = "blocked"
                return
            _try_move(-12.0)
            time.sleep(1.5)
            if _check_person():
                found = True

            if self._stop_event.is_set():
                _try_center()
                result = "blocked"
                return
            _try_center()
            time.sleep(0.5)
            if _check_person():
                found = True

            if self._stop_event.is_set():
                result = "blocked"
                return
            _try_move(12.0)
            time.sleep(1.5)
            if _check_person():
                found = True

            _try_center()

            if not any_movement_executed:
                result = "blocked"
            else:
                result = "found" if found else "not_found"
                if found:
                    _scan_now = time.monotonic()
                    if self._evidence_accumulator is not None:
                        self._evidence_accumulator.record_person_seen(now=_scan_now)
                    if self._scan_scheduler is not None:
                        self._scan_scheduler.reset_away_recheck()

        except Exception:
            result = "blocked"
        finally:
            with self._lock:
                self._micro_scan_state = result
                self._micro_scan_completed_at = time.monotonic()
                self._micro_scan_result = result

    def _check_and_trigger_scans(self, now: float) -> None:
        if not self.config.active_monitoring_enabled:
            return
        if self.config.continuous_tracking_enabled:
            with self._lock:
                self._expire_stuck_focus_scan_locked(now)
            return
        with self._lock:
            self._expire_stuck_focus_scan_locked(now)
            if self._focus_scan_running or self._micro_scan_state == "scanning":
                return

        assert self._evidence_accumulator is not None
        assert self._scan_scheduler is not None
        absent_seconds = self._evidence_accumulator.person_absent_seconds(now=now)

        if self._scan_scheduler.is_away_recheck_due(now=now, person_absent_seconds=absent_seconds):
            self._scan_scheduler.record_away_recheck_triggered(now=now)
            with self._lock:
                # Clear stale result so old person_found=True does not block the new episode.
                if self._last_focus_scan_result is not None and self._last_focus_scan_result.person_found:
                    self._last_focus_scan_result = None
            self._trigger_focus_scan("away_recheck", now)
            return

        if self.config.periodic_scan_enabled and self._scan_scheduler.is_periodic_scan_due(now=now):
            person_clearly_visible = (
                absent_seconds is None
                or absent_seconds < self.config.away_recheck_scan_after_seconds
            )
            self._scan_scheduler.record_periodic_scan(now=now)
            if not person_clearly_visible:
                self._trigger_focus_scan("periodic", now)

    def _trigger_focus_scan(self, scan_type: str, triggered_at: float) -> None:
        scan_id = f"{scan_type}_{triggered_at:.3f}"
        with self._lock:
            self._focus_scan_running = True
            self._focus_scan_started_at = triggered_at
            self._active_focus_scan_type = scan_type
            self._active_focus_scan_id = scan_id
            self._active_focus_scan_cancel_requested = False
        thread = threading.Thread(
            target=self._run_focus_scan_background,
            args=(scan_type, triggered_at),
            name=f"nexa-focus-scan-{scan_type}",
            daemon=True,
        )
        thread.start()

    def _expire_stuck_focus_scan_locked(self, now: float) -> None:
        if not self._focus_scan_running:
            return
        started_at = self._focus_scan_started_at
        if started_at is None:
            started_at = now
            self._focus_scan_started_at = started_at
        timeout_seconds = max(
            1.0,
            self.config.away_scan_max_duration_seconds,
        )
        if now - started_at <= timeout_seconds:
            return
        scan_type = self._active_focus_scan_type or "away_recheck"
        scan_id = self._active_focus_scan_id or f"{scan_type}_{started_at:.3f}"
        self._last_focus_scan_result = FocusScanResult(
            scan_type=scan_type,
            person_found=False,
            triggered_at=started_at,
            completed_at=now,
            blocked=True,
            movement_executed=False,
            scan_blocked_reason="scan_timeout",
            pan_tilt_scan_enabled=self.config.pan_tilt_scan_enabled,
            pan_tilt_backend_present=self.pan_tilt_backend is not None,
            camera_available=False,
            scan_id=scan_id,
            scan_points_attempted=0,
            scan_point_results=(),
            behavior_presence_ignored_for_scan=True,
            stale_observation_ignored=True,
        )
        self._focus_scan_running = False
        self._focus_scan_started_at = None
        self._active_focus_scan_id = ""
        self._active_focus_scan_type = ""
        self._active_focus_scan_cancel_requested = False

    def _cancel_active_focus_scan(self, *, now: float, reason: str) -> None:
        with self._lock:
            if not self._focus_scan_running:
                return
            scan_type = self._active_focus_scan_type or "away_recheck"
            started_at = self._focus_scan_started_at or now
            scan_id = self._active_focus_scan_id or f"{scan_type}_{started_at:.3f}"
            self._active_focus_scan_cancel_requested = True
            self._last_focus_scan_result = None
            self._focus_scan_running = False
            self._focus_scan_started_at = None
            self._active_focus_scan_id = ""
            self._active_focus_scan_type = ""

    def _run_focus_scan_background(self, scan_type: str, triggered_at: float) -> None:
        pan_tilt = self.pan_tilt_backend
        pt_scan_enabled = self.config.pan_tilt_scan_enabled
        pt_present = pan_tilt is not None
        person_found = False
        blocked = True
        scan_blocked_reason = "scan_exception"
        any_movement_executed = False
        collected_missing_gates: list[str] = []
        scan_point_results: list[dict] = []
        stale_observation_ignored = False
        camera_available = False
        scan_id = f"{scan_type}_{triggered_at:.3f}"

        def _add_point(label: str, found: bool, cam: bool, info: dict) -> None:
            nonlocal stale_observation_ignored
            stale_observation_ignored = stale_observation_ignored or bool(
                info.get("stale_observation_ignored", False)
            )
            scan_point_results.append({"point": label, "hard_person_found": found, "camera_available": cam, **info})

        try:
            if self._focus_scan_cancelled():
                return
            found_pre, cam_pre, info_pre = self._check_person_for_scan_result()
            camera_available = cam_pre
            _add_point("pre_move", found_pre, cam_pre, info_pre)
            if found_pre:
                person_found = True

            if not pt_scan_enabled:
                scan_blocked_reason = "pan_tilt_scan_disabled"
            elif not pt_present:
                scan_blocked_reason = "pan_tilt_backend_missing"
            else:
                blocked = False
                scan_blocked_reason = ""
                _pan_move = getattr(pan_tilt, "move_delta", None)
                _pan_center = getattr(pan_tilt, "center", None)

                def _move(delta: float) -> bool:
                    if callable(_pan_move):
                        result = self._call_with_timeout(
                            lambda: _pan_move(pan_delta_degrees=delta, tilt_delta_degrees=0.0),
                            timeout_seconds=self.config.observation_refresh_timeout_seconds,
                        )
                        if result.get("timeout"):
                            collected_missing_gates.append("pan_tilt_command_timeout")
                            return False
                        payload = result.get("value")
                        if isinstance(payload, dict):
                            if not payload.get("movement_executed", False):
                                gates = payload.get("missing_safety_gates", [])
                                if gates:
                                    collected_missing_gates.extend(gates)
                            return bool(payload.get("movement_executed", False))
                    return False

                def _center() -> None:
                    if callable(_pan_center):
                        self._call_with_timeout(
                            _pan_center,
                            timeout_seconds=self.config.observation_refresh_timeout_seconds,
                        )

                settle_seconds = self._scan_point_settle_seconds(scan_type)

                if self._focus_scan_cancelled():
                    return
                moved = _move(-self.config.scan_pan_degrees)
                any_movement_executed = any_movement_executed or moved
                time.sleep(settle_seconds)
                if self._focus_scan_cancelled():
                    return
                found_now, camera_now, info_now = self._check_person_for_scan_result()
                camera_available = camera_available or camera_now
                _add_point("left", found_now, camera_now, info_now)
                if found_now:
                    person_found = True

                if self._focus_scan_cancelled():
                    return
                _center()
                time.sleep(settle_seconds / 2.0)
                if self._focus_scan_cancelled():
                    return
                found_now, camera_now, info_now = self._check_person_for_scan_result()
                camera_available = camera_available or camera_now
                _add_point("center", found_now, camera_now, info_now)
                if found_now:
                    person_found = True

                if self._focus_scan_cancelled():
                    return
                moved = _move(self.config.scan_pan_degrees)
                any_movement_executed = any_movement_executed or moved
                time.sleep(settle_seconds)
                if self._focus_scan_cancelled():
                    return
                found_now, camera_now, info_now = self._check_person_for_scan_result()
                camera_available = camera_available or camera_now
                _add_point("right", found_now, camera_now, info_now)
                if found_now:
                    person_found = True

                _center()

                if not any_movement_executed:
                    scan_blocked_reason = "hardware_gates_closed"
                    blocked = True

            completed_at = time.monotonic()
            if person_found:
                assert self._evidence_accumulator is not None
                assert self._scan_scheduler is not None
                self._evidence_accumulator.record_person_seen(now=completed_at)
                self._scan_scheduler.reset_away_recheck()

            with self._lock:
                if self._active_focus_scan_cancel_requested:
                    return
                self._last_focus_scan_result = FocusScanResult(
                    scan_type=scan_type,
                    person_found=person_found,
                    triggered_at=triggered_at,
                    completed_at=completed_at,
                    blocked=blocked,
                    movement_executed=any_movement_executed,
                    scan_blocked_reason=scan_blocked_reason,
                    pan_tilt_scan_enabled=pt_scan_enabled,
                    pan_tilt_backend_present=pt_present,
                    missing_safety_gates=tuple(dict.fromkeys(collected_missing_gates)),
                    camera_available=camera_available,
                    scan_id=scan_id,
                    scan_points_attempted=len(scan_point_results),
                    scan_point_results=tuple(scan_point_results),
                    behavior_presence_ignored_for_scan=True,
                    stale_observation_ignored=stale_observation_ignored,
                )
        except Exception:
            with self._lock:
                if self._active_focus_scan_cancel_requested:
                    return
                self._last_focus_scan_result = FocusScanResult(
                    scan_type=scan_type,
                    person_found=False,
                    triggered_at=triggered_at,
                    completed_at=time.monotonic(),
                    blocked=True,
                    movement_executed=False,
                    scan_blocked_reason="scan_exception",
                    pan_tilt_scan_enabled=pt_scan_enabled,
                    pan_tilt_backend_present=pt_present,
                    missing_safety_gates=(),
                    camera_available=False,
                    scan_id=scan_id,
                    scan_points_attempted=len(scan_point_results),
                    scan_point_results=tuple(scan_point_results),
                    behavior_presence_ignored_for_scan=True,
                    stale_observation_ignored=stale_observation_ignored,
                )
        finally:
            with self._lock:
                if not self._active_focus_scan_cancel_requested:
                    self._focus_scan_running = False
                    self._focus_scan_started_at = None
                    self._active_focus_scan_id = ""
                    self._active_focus_scan_type = ""
                self._active_focus_scan_cancel_requested = False

    def _focus_scan_cancelled(self) -> bool:
        with self._lock:
            return bool(self._active_focus_scan_cancel_requested or self._stop_event.is_set())

    def _check_person_for_scan(self) -> bool:
        found, _camera_available, _point = self._check_person_for_scan_result()
        return found

    def _scan_point_settle_seconds(self, scan_type: str) -> float:
        if scan_type == "away_recheck":
            return min(self.config.scan_point_settle_seconds, 0.25)
        return self.config.scan_point_settle_seconds

    def _check_person_for_scan_result(self) -> tuple[bool, bool, dict]:
        """Returns (hard_person_found, camera_available, scan_point_info).

        Uses ONLY hard visual evidence: face_count (Haar) and YOLO person labels.
        Behavior/session presence and tracker-based people_count are explicitly excluded.
        Returns hard_person_found=False for observations older than 5 seconds.
        """
        method = getattr(self.vision_backend, "latest_observation", None)
        if not callable(method):
            return False, False, {"error": "no_backend_method", "camera_unavailable": True}
        obs = self._latest_observation_force_refresh_with_timeout(
            timeout_seconds=min(
                self.config.observation_refresh_timeout_seconds,
                self.config.scan_observation_refresh_timeout_seconds,
            ),
        )
        if obs is None:
            return False, False, {
                "error": self._last_force_refresh_error or "no_observation",
                "camera_unavailable": True,
                "observation_age_seconds": None,
                "stale_observation_ignored": False,
                "behavior_presence_ignored_for_scan": True,
                "object_labels": [],
            }

        now = time.monotonic()
        obs_labels = frozenset(str(lbl) for lbl in getattr(obs, "labels", []) or [])
        metadata = dict(getattr(obs, "metadata", {}) or {})
        perception = dict(metadata.get("perception") or {})

        captured_at = float(getattr(obs, "captured_at", 0.0) or 0.0)
        age_seconds = round(now - captured_at, 2) if captured_at > 0.0 else None
        stale = age_seconds is not None and age_seconds > 5.0

        try:
            face_count = max(0, int(perception.get("face_count", 0) or 0))
        except (TypeError, ValueError):
            face_count = 0
        try:
            people_count = max(0, int(perception.get("people_count", 0) or 0))
        except (TypeError, ValueError):
            people_count = 0
        yolo_person = "object:person" in obs_labels
        yolo_person_count = 1 if yolo_person else 0
        person_without_face = face_count == 0 and yolo_person_count > 0

        # Focus Mode reacquisition is face-only. Person/body labels are diagnostic
        # evidence only and must not cancel scan or suppress the face-lost path.
        hard_found = (not stale) and face_count > 0
        camera_available = bool(getattr(obs, "detected", False))

        object_labels = sorted(lbl for lbl in obs_labels if lbl.startswith("object:"))
        point_info: dict = {
            "face_count": face_count,
            "people_count": people_count,
            "yolo_person_count": yolo_person_count,
            "person_without_face": person_without_face,
            "hard_person_found": hard_found,
            "observation_age_seconds": age_seconds,
            "stale_observation_ignored": stale,
            "behavior_presence_ignored_for_scan": True,
            "object_labels": object_labels,
        }
        return hard_found, camera_available, point_info

    @staticmethod
    def _normalize_language(language: str) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


def _replace_snapshot_state(
    snapshot: FocusVisionStateSnapshot, new_state: FocusVisionState
) -> FocusVisionStateSnapshot:
    return FocusVisionStateSnapshot(
        current_state=new_state,
        stable_seconds=snapshot.stable_seconds,
        state_started_at=snapshot.state_started_at,
        updated_at=snapshot.updated_at,
        decision=snapshot.decision,
    )


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return dict(asdict(value))
    return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


__all__ = ["FocusVisionSentinelService", "FocusVisionTickResult"]
