from __future__ import annotations

import time
from dataclasses import dataclass

from .constants import PHASE_COMMAND


@dataclass(slots=True)
class MainLoopRuntimeState:
    standby_banner_shown: bool = False
    compatibility_wake_mode_logged: bool = False
    wake_miss_count: int = 0
    last_wake_stt_fallback_monotonic: float = 0.0
    wake_rearm_ready_monotonic: float = 0.0
    prefetched_command_text: str | None = None
    active_phase: str = PHASE_COMMAND
    active_empty_count: int = 0
    active_ignored_count: int = 0
    last_transcript_normalized: str | None = None
    last_transcript_time: float | None = None

    def reset_active_counters(self) -> None:
        self.active_empty_count = 0
        self.active_ignored_count = 0

    def set_active_phase(self, phase: str) -> None:
        self.active_phase = str(phase or PHASE_COMMAND)
        self.reset_active_counters()

    def hide_standby_banner(self) -> None:
        self.standby_banner_shown = False

    def show_standby_banner(self) -> None:
        self.standby_banner_shown = True

    def clear_prefetched_command(self) -> None:
        self.prefetched_command_text = None

    def consume_prefetched_command(self) -> str | None:
        value = self.prefetched_command_text
        self.prefetched_command_text = None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def store_prefetched_command(self, text: str | None) -> None:
        cleaned = str(text or "").strip()
        self.prefetched_command_text = cleaned or None

    def clear_wake_rearm(self) -> None:
        self.wake_rearm_ready_monotonic = 0.0

    def arm_wake_rearm(self, seconds: float) -> None:
        self.wake_rearm_ready_monotonic = time.monotonic() + max(0.0, float(seconds))

    def wake_rearm_remaining_seconds(self) -> float:
        if self.wake_rearm_ready_monotonic <= 0.0:
            return 0.0
        return max(0.0, self.wake_rearm_ready_monotonic - time.monotonic())

    def reset_wake_detection(self) -> None:
        self.wake_miss_count = 0
        self.compatibility_wake_mode_logged = False
        self.clear_wake_rearm()

    def record_wake_miss(self) -> None:
        self.wake_miss_count += 1

    def mark_stt_wake_fallback_attempt(self) -> None:
        self.last_wake_stt_fallback_monotonic = time.monotonic()

    def record_empty_capture(self) -> int:
        self.active_empty_count += 1
        return self.active_empty_count

    def record_ignored_capture(self) -> int:
        self.active_ignored_count += 1
        return self.active_ignored_count

    def remember_accepted_transcript(self, normalized_text: str) -> None:
        cleaned = str(normalized_text or "").strip()
        self.last_transcript_normalized = cleaned or None
        self.last_transcript_time = time.monotonic() if cleaned else None


__all__ = ["MainLoopRuntimeState"]