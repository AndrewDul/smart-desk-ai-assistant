from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class VoiceSessionSnapshot:
    state: str
    active_until_monotonic: float = 0.0
    last_state_change_monotonic: float = field(default_factory=time.monotonic)
    detail: str = ""
    last_wake_detected_monotonic: float = 0.0
    last_command_accepted_monotonic: float = 0.0
    active_window_generation: int = 0

    @property
    def active_window_open(self) -> bool:
        return self.active_window_remaining_seconds > 0.0

    @property
    def active_window_remaining_seconds(self) -> float:
        remaining = self.active_until_monotonic - time.monotonic()
        return max(0.0, remaining)

    @property
    def state_age_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.last_state_change_monotonic)


__all__ = ["VoiceSessionSnapshot"]