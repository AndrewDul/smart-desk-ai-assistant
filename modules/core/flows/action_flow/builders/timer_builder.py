from __future__ import annotations

from .base import BaseActionResponseBuilder
from .models import ActionResponseSpec


class TimerSkillResponseBuilder(BaseActionResponseBuilder):
    def build_start_failure(
        self,
        *,
        language: str,
        action: str,
        outcome_message: str,
        resolved_source: str,
        phase: str,
        minutes: float,
        mode: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        spoken = outcome_message or self.localized(
            language,
            "Nie mogę teraz uruchomić timera.",
            "I cannot start the timer right now.",
        )
        return ActionResponseSpec(
            action=action,
            spoken_text=spoken,
            display_title="TIMER",
            display_lines=self.display_lines(spoken),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "phase": phase,
                "minutes": float(minutes),
                "mode": mode,
            },
        )

    def build_stop_failure(
        self,
        *,
        language: str,
        action: str,
        outcome_message: str,
        resolved_source: str,
        phase: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        spoken = outcome_message or self.localized(
            language,
            "Nie ma teraz aktywnego timera.",
            "There is no active timer right now.",
        )
        return ActionResponseSpec(
            action=action,
            spoken_text=spoken,
            display_title="TIMER",
            display_lines=self.display_lines(spoken),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "phase": phase,
            },
        )


__all__ = ["TimerSkillResponseBuilder"]