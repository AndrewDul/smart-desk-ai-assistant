from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import FocusVisionConfig
from .decision_engine import FocusVisionDecisionEngine
from .models import FocusVisionReminder, FocusVisionStateSnapshot
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
    _delivered_reminder_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.reminder_policy is None:
            self.reminder_policy = FocusVisionReminderPolicy(config=self.config)
        if self.telemetry is None:
            self.telemetry = FocusVisionTelemetryWriter(self.config.telemetry_path)

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
            assert self.reminder_policy is not None
            self.reminder_policy.start_session(started_at=time.monotonic())
            self._thread = threading.Thread(
                target=self._run_loop,
                name="nexa-focus-vision-sentinel",
                daemon=True,
            )
            self._running = True
            self._thread.start()
            return True

    def stop(self) -> None:
        thread: threading.Thread | None
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self.config.observation_interval_seconds * 2.0))
        with self._lock:
            self._running = False
            self._thread = None
            assert self.reminder_policy is not None
            self.reminder_policy.stop_session()

    def tick(self, *, now: float | None = None) -> FocusVisionTickResult:
        current_time = float(now if now is not None else time.monotonic())
        try:
            observation = self._latest_observation_for_decision(current_time=current_time)
            decision = self.decision_engine.decide(observation, observed_at=current_time)
            snapshot = self.state_machine.update(decision)
            assert self.reminder_policy is not None
            reminder = self.reminder_policy.evaluate(snapshot, language=self._language, now=current_time)
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
            self._write_telemetry(result, current_time=current_time)
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
                "max_observation_age_seconds": self.config.max_observation_age_seconds,
                "last_observation_age_seconds": self._last_observation_age_seconds,
                "last_observation_stale": self._last_observation_stale,
                "delivered_reminder_count": self._delivered_reminder_count,
                "reminder_handler_attached": self.reminder_handler is not None,
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
                self._stop_event.wait(self.config.observation_interval_seconds)
        finally:
            with self._lock:
                self._running = False

    def _latest_observation_for_decision(self, *, current_time: float):
        observation = self._latest_observation()
        observation_age = self._observation_age_seconds(observation, current_time=current_time)
        stale = self._is_observation_stale(observation_age)
        self._last_observation_age_seconds = observation_age
        self._last_observation_stale = stale
        if stale:
            return None
        return observation

    def _latest_observation(self):
        method = getattr(self.vision_backend, "latest_observation", None)
        if not callable(method):
            return None
        return method(force_refresh=self.config.latest_observation_force_refresh)

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

    def _write_telemetry(self, result: FocusVisionTickResult, *, current_time: float) -> None:
        if self.telemetry is None:
            return
        self.telemetry.append(
            {
                "event": "focus_vision_tick",
                "created_at": current_time,
                "language": self._language,
                "dry_run": self.config.dry_run,
                "last_error": self._last_error,
                "latest_observation_force_refresh": self.config.latest_observation_force_refresh,
                "observation_age_seconds": self._last_observation_age_seconds,
                "observation_stale": self._last_observation_stale,
                **result.to_dict(),
            }
        )

    @staticmethod
    def _normalize_language(language: str) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


__all__ = ["FocusVisionSentinelService", "FocusVisionTickResult"]
