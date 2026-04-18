from __future__ import annotations

from .base import BaseSkillExecutor
from .models import ExecutorOutcome


class TimerSkillExecutor(BaseSkillExecutor):
    def start(self, *, mode: str, minutes: float) -> ExecutorOutcome:
        start_method = self.first_callable(self.assistant.timer, "start", "start_timer")
        if start_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        result = start_method(float(minutes), mode)
        if self.result_ok(result):
            return ExecutorOutcome(
                ok=True,
                status="accepted",
                data={"mode": mode, "minutes": float(minutes)},
                metadata={"source": "timer_service.start"},
            )

        return ExecutorOutcome(
            ok=False,
            status="start_failed",
            message=self.result_message(result),
            data={"mode": mode, "minutes": float(minutes)},
            metadata={"source": "timer_service.start"},
        )

    def stop(self) -> ExecutorOutcome:
        stop_method = self.first_callable(self.assistant.timer, "stop", "cancel", "stop_timer")
        if stop_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        result = stop_method()
        if self.result_ok(result):
            return ExecutorOutcome(
                ok=True,
                status="accepted",
                metadata={"source": "timer_service.stop"},
            )

        return ExecutorOutcome(
            ok=False,
            status="stop_failed",
            message=self.result_message(result),
            metadata={"source": "timer_service.stop"},
        )


__all__ = ["TimerSkillExecutor"]