from __future__ import annotations

from typing import Any


class RuntimeBuilderFeaturesMixin:
    """
    Build the core feature services.
    """

    def _build_memory(self) -> Any:
        memory_class = self._import_symbol(
            "modules.features.memory.service",
            "MemoryService",
        )
        return memory_class()

    def _build_reminders(self) -> Any:
        reminders_class = self._import_symbol(
            "modules.features.reminders.service",
            "ReminderService",
        )
        return reminders_class()

    def _build_timer(
        self,
        *,
        on_timer_started=None,
        on_timer_finished=None,
        on_timer_stopped=None,
        on_timer_tick=None,
    ) -> Any:
        timer_class = self._import_symbol(
            "modules.features.timer.service",
            "TimerService",
        )
        return timer_class(
            on_started=on_timer_started,
            on_finished=on_timer_finished,
            on_stopped=on_timer_stopped,
            on_tick=on_timer_tick,
        )


__all__ = ["RuntimeBuilderFeaturesMixin"]