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
    ) -> FocusVisionReminder | None:
        current_time = float(now if now is not None else snapshot.updated_at)
        if self.session_started_at is None:
            self.start_session(started_at=current_time)

        if not self._past_startup_grace(current_time):
            return None
        if self._warning_count >= self.config.max_warnings_per_session:
            return None

        reminder_kind = self._kind_for_snapshot(snapshot)
        if reminder_kind is None:
            return None
        if not self._stable_long_enough(snapshot, reminder_kind):
            return None
        if not self._cooldown_elapsed(reminder_kind, current_time):
            return None

        text = self._message(reminder_kind, language)
        self._last_reminder_at_by_kind[reminder_kind] = current_time
        self._warning_count += 1
        return FocusVisionReminder(
            kind=reminder_kind,
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
        if snapshot.current_state == FocusVisionState.ABSENT:
            return FocusVisionReminderKind.ABSENCE
        if snapshot.current_state == FocusVisionState.PHONE_DISTRACTION:
            return FocusVisionReminderKind.PHONE_DISTRACTION
        return None

    def _stable_long_enough(self, snapshot: FocusVisionStateSnapshot, kind: FocusVisionReminderKind) -> bool:
        if kind == FocusVisionReminderKind.ABSENCE:
            threshold = self.config.absence_warning_after_seconds
        else:
            threshold = self.config.phone_warning_after_seconds
        return snapshot.stable_seconds >= threshold

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
        if normalized == "pl":
            return "Focus mode nadal trwa. Odłóż telefon i wróć do zadania."
        return "Focus mode is still running. Put the phone down and return to your task."

    @staticmethod
    def _normalize_language(language: str) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


__all__ = ["FocusVisionReminderPolicy"]
