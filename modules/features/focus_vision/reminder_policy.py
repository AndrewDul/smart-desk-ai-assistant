from __future__ import annotations

from dataclasses import dataclass, field

from .config import FocusVisionConfig
from .models import (
    FocusVisionReminder,
    FocusVisionReminderKind,
    FocusVisionState,
    FocusVisionStateSnapshot,
)


@dataclass(slots=True)
class FocusVisionReminderPolicy:
    """Decide whether a stabilized focus state should produce a reminder."""

    config: FocusVisionConfig = field(default_factory=FocusVisionConfig)
    session_started_at: float | None = None
    _last_reminder_at_by_kind: dict[FocusVisionReminderKind, float] = field(default_factory=dict)
    _warning_count: int = 0

    def start_session(self, *, started_at: float) -> None:
        self.session_started_at = float(started_at)
        self._last_reminder_at_by_kind.clear()
        self._warning_count = 0

    def stop_session(self) -> None:
        self.session_started_at = None
        self._last_reminder_at_by_kind.clear()
        self._warning_count = 0

    def evaluate(
        self,
        snapshot: FocusVisionStateSnapshot,
        *,
        language: str,
        now: float | None = None,
        person_absent_seconds: float | None = None,
        phone_accumulated_seconds: float | None = None,
        immediate_phone_reminder_due: bool = False,
        immediate_away_reminder_due: bool = False,
    ) -> FocusVisionReminder | None:
        current_time = float(now if now is not None else snapshot.updated_at)
        if self.session_started_at is None:
            self.start_session(started_at=current_time)

        if self._warning_count >= self.config.max_warnings_per_session:
            return None

        phone_kind = FocusVisionReminderKind.PHONE_DISTRACTION
        if (
            immediate_phone_reminder_due
            and self._reminder_kind_enabled(phone_kind)
            and self._cooldown_elapsed(phone_kind, current_time)
        ):
            return self._make_reminder(phone_kind, language, current_time, snapshot)

        away_kind = FocusVisionReminderKind.AWAY_SOFT
        if (
            immediate_away_reminder_due
            and self._reminder_kind_enabled(away_kind)
            and self._cooldown_elapsed(away_kind, current_time)
        ):
            return self._make_reminder(away_kind, language, current_time, snapshot)

        if not self._past_startup_grace(current_time):
            return None

        reminder_kind = self._kind_for_snapshot(snapshot)
        if reminder_kind is None:
            return None
        if not self._reminder_kind_enabled(reminder_kind):
            return None
        if not self._stable_long_enough(
            snapshot,
            reminder_kind,
            person_absent_seconds=person_absent_seconds,
            phone_accumulated_seconds=phone_accumulated_seconds,
        ):
            return None
        if not self._cooldown_elapsed(reminder_kind, current_time):
            return None

        return self._make_reminder(reminder_kind, language, current_time, snapshot)

    def _make_reminder(
        self,
        kind: FocusVisionReminderKind,
        language: str,
        current_time: float,
        snapshot: FocusVisionStateSnapshot,
    ) -> FocusVisionReminder:
        text = self._message(kind, language)
        self._last_reminder_at_by_kind[kind] = current_time
        self._warning_count += 1
        return FocusVisionReminder(
            kind=kind,
            language=self._normalize_language(language),
            text=text,
            created_at=current_time,
            snapshot=snapshot,
            dry_run=self.config.dry_run or not self.config.voice_warnings_enabled,
        )

    def status(self) -> dict[str, object]:
        return {
            "session_started_at": self.session_started_at,
            "warning_count": self._warning_count,
            "enabled_reminder_kinds": list(self.config.enabled_reminder_kinds),
            "last_reminder_at_by_kind": {
                kind.value: value for kind, value in self._last_reminder_at_by_kind.items()
            },
        }

    def _past_startup_grace(self, now: float) -> bool:
        if self.session_started_at is None:
            return False
        return (now - self.session_started_at) >= self.config.startup_grace_seconds

    @staticmethod
    def _kind_for_snapshot(snapshot: FocusVisionStateSnapshot) -> FocusVisionReminderKind | None:
        if snapshot.current_state == FocusVisionState.AWAY_CONFIRMED:
            return FocusVisionReminderKind.ABSENCE
        if snapshot.current_state == FocusVisionState.PHONE_DISTRACTION:
            return FocusVisionReminderKind.PHONE_DISTRACTION
        if snapshot.current_state == FocusVisionState.AWAY_PENDING_SCAN:
            return FocusVisionReminderKind.AWAY_SOFT
        return None

    def _reminder_kind_enabled(self, kind: FocusVisionReminderKind) -> bool:
        enabled = {_normalize_reminder_kind(value) for value in self.config.enabled_reminder_kinds}
        return kind.value in enabled

    def _stable_long_enough(
        self,
        snapshot: FocusVisionStateSnapshot,
        kind: FocusVisionReminderKind,
        *,
        person_absent_seconds: float | None = None,
        phone_accumulated_seconds: float | None = None,
    ) -> bool:
        if kind == FocusVisionReminderKind.ABSENCE:
            return snapshot.stable_seconds >= self.config.absence_warning_after_seconds

        if kind == FocusVisionReminderKind.AWAY_SOFT:
            if person_absent_seconds is not None:
                return person_absent_seconds >= self.config.away_soft_reminder_after_seconds
            return snapshot.stable_seconds >= self.config.away_soft_reminder_after_seconds

        return True

    @staticmethod
    def _phone_usage_active_seconds(snapshot: FocusVisionStateSnapshot) -> float:
        evidence = getattr(getattr(snapshot, "decision", None), "evidence", None)
        value = getattr(evidence, "phone_usage_active_seconds", 0.0)
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _cooldown_elapsed(self, kind: FocusVisionReminderKind, now: float) -> bool:
        last = self._last_reminder_at_by_kind.get(kind)
        if last is None:
            return True
        return (now - last) >= self.config.warning_cooldown_seconds

    def _message(self, kind: FocusVisionReminderKind, language: str) -> str:
        normalized = self._normalize_language(language)
        if kind == FocusVisionReminderKind.ABSENCE:
            if normalized == "pl":
                return "To jest twój czas pracy. Wróć do biurka i kontynuuj focus mode."
            return "This is your work time. Come back to your desk and continue focus mode."
        if kind == FocusVisionReminderKind.AWAY_SOFT:
            if normalized == "pl":
                return "Focus mode nadal trwa. Wróć proszę do biurka, kiedy możesz."
            return "Focus mode is still running. Please come back to the desk when you can."
        if normalized == "pl":
            return "Focus mode nadal trwa. Odłóż telefon i wróć do zadania."
        return "Focus mode is still running. Put the phone down and return to your task."

    @staticmethod
    def _normalize_language(language: str) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"



def _normalize_reminder_kind(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "absent": "absence",
        "away": "absence",
        "desk_absence": "absence",
        "phone": "phone_distraction",
        "phone_usage": "phone_distraction",
    }
    return aliases.get(normalized, normalized)


__all__ = ["FocusVisionReminderPolicy"]
