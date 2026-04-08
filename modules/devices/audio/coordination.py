from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from modules.shared.logging.logger import append_log


@dataclass(slots=True)
class AudioCoordinatorSnapshot:
    active_output_count: int = 0
    blocked_until_monotonic: float = 0.0
    last_output_started_monotonic: float = 0.0
    last_output_finished_monotonic: float = 0.0
    last_output_source: str = ""
    last_output_preview: str = ""
    active_tokens: tuple[str, ...] = field(default_factory=tuple)


class AudioCoordinator:
    """
    Central half-duplex shield for assistant output vs. microphone input.

    Responsibilities:
    - mark when assistant output is currently active
    - keep a short post-speech hold to reduce self-hearing
    - support manual input holds for future use
    - expose cheap polling methods for main loop and audio pipeline
    """

    def __init__(
        self,
        *,
        post_speech_hold_seconds: float = 0.72,
        input_poll_interval_seconds: float = 0.05,
    ) -> None:
        self.post_speech_hold_seconds = max(0.0, float(post_speech_hold_seconds))
        self.input_poll_interval_seconds = max(0.01, float(input_poll_interval_seconds))

        self._lock = threading.RLock()
        self._active_outputs: dict[str, dict[str, Any]] = {}
        self._manual_holds: dict[str, dict[str, Any]] = {}

        self._snapshot = AudioCoordinatorSnapshot()
        self._generation = 0

    # ------------------------------------------------------------------
    # Snapshot / state
    # ------------------------------------------------------------------

    def snapshot(self) -> AudioCoordinatorSnapshot:
        with self._lock:
            return AudioCoordinatorSnapshot(
                active_output_count=len(self._active_outputs),
                blocked_until_monotonic=self._snapshot.blocked_until_monotonic,
                last_output_started_monotonic=self._snapshot.last_output_started_monotonic,
                last_output_finished_monotonic=self._snapshot.last_output_finished_monotonic,
                last_output_source=self._snapshot.last_output_source,
                last_output_preview=self._snapshot.last_output_preview,
                active_tokens=tuple(self._active_outputs.keys()),
            )

    def active_output_count(self) -> int:
        with self._lock:
            return len(self._active_outputs)

    def has_active_output(self) -> bool:
        with self._lock:
            return bool(self._active_outputs)

    # ------------------------------------------------------------------
    # Assistant output lifecycle
    # ------------------------------------------------------------------

    def begin_assistant_output(
        self,
        *,
        source: str,
        text_preview: str = "",
    ) -> str:
        token = uuid.uuid4().hex
        now = time.monotonic()
        source_text = str(source or "assistant_output").strip() or "assistant_output"
        preview = self._preview_text(text_preview)

        with self._lock:
            self._generation += 1
            self._active_outputs[token] = {
                "source": source_text,
                "preview": preview,
                "started_at": now,
                "generation": self._generation,
            }
            self._snapshot.active_output_count = len(self._active_outputs)
            self._snapshot.last_output_started_monotonic = now
            self._snapshot.last_output_source = source_text
            self._snapshot.last_output_preview = preview

            active_count = self._snapshot.active_output_count

        append_log(
            "Audio coordinator: assistant output started "
            f"source={source_text}, active_outputs={active_count}, preview={preview}"
        )
        return token

    def end_assistant_output(
        self,
        token: str | None,
        *,
        hold_seconds: float | None = None,
    ) -> None:
        if not token:
            return

        now = time.monotonic()
        effective_hold = (
            self.post_speech_hold_seconds
            if hold_seconds is None
            else max(0.0, float(hold_seconds))
        )

        with self._lock:
            output_info = self._active_outputs.pop(token, None)
            if output_info is None:
                return

            self._snapshot.active_output_count = len(self._active_outputs)
            source_text = str(output_info.get("source") or "assistant_output")

            if not self._active_outputs:
                self._snapshot.last_output_finished_monotonic = now
                self._snapshot.blocked_until_monotonic = max(
                    self._snapshot.blocked_until_monotonic,
                    now + effective_hold,
                )

            active_count = self._snapshot.active_output_count

        append_log(
            "Audio coordinator: assistant output finished "
            f"source={source_text}, active_outputs={active_count}, hold_seconds={effective_hold:.2f}"
        )

    # ------------------------------------------------------------------
    # Manual holds
    # ------------------------------------------------------------------

    def force_input_hold(
        self,
        *,
        reason: str,
        hold_seconds: float,
    ) -> str:
        token = uuid.uuid4().hex
        now = time.monotonic()
        effective_hold = max(0.0, float(hold_seconds))
        reason_text = str(reason or "manual_hold").strip() or "manual_hold"

        with self._lock:
            self._manual_holds[token] = {
                "reason": reason_text,
                "until": now + effective_hold,
                "created_at": now,
            }
            self._snapshot.blocked_until_monotonic = max(
                self._snapshot.blocked_until_monotonic,
                now + effective_hold,
            )

        append_log(
            "Audio coordinator: manual input hold registered "
            f"reason={reason_text}, hold_seconds={effective_hold:.2f}"
        )
        return token

    def release_input_hold(self, token: str | None) -> None:
        if not token:
            return

        with self._lock:
            released = self._manual_holds.pop(token, None)

        if released is not None:
            append_log(
                "Audio coordinator: manual input hold released "
                f"reason={released.get('reason')}"
            )

    def clear_expired_holds(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._clear_expired_holds_locked(now)

    # ------------------------------------------------------------------
    # Input blocking
    # ------------------------------------------------------------------

    def input_blocked(self) -> bool:
        now = time.monotonic()

        with self._lock:
            self._clear_expired_holds_locked(now)

            if self._active_outputs:
                return True

            if self._manual_holds:
                latest_manual_until = max(
                    float(hold.get("until", 0.0))
                    for hold in self._manual_holds.values()
                )
                if now < latest_manual_until:
                    return True

            return now < self._snapshot.blocked_until_monotonic

    def time_until_input_unblocked(self) -> float:
        now = time.monotonic()

        with self._lock:
            self._clear_expired_holds_locked(now)

            if self._active_outputs:
                return max(self.input_poll_interval_seconds, 0.0)

            latest_deadline = self._snapshot.blocked_until_monotonic

            if self._manual_holds:
                latest_manual_until = max(
                    float(hold.get("until", 0.0))
                    for hold in self._manual_holds.values()
                )
                latest_deadline = max(latest_deadline, latest_manual_until)

            remaining = latest_deadline - now
            return max(0.0, remaining)

    def wait_until_input_allowed(self, max_wait_seconds: float | None = None) -> bool:
        deadline = None
        if max_wait_seconds is not None:
            deadline = time.monotonic() + max(0.0, float(max_wait_seconds))

        while self.input_blocked():
            if deadline is not None and time.monotonic() >= deadline:
                return False

            sleep_for = self.time_until_input_unblocked()
            if sleep_for <= 0.0:
                sleep_for = self.input_poll_interval_seconds

            time.sleep(min(max(sleep_for, 0.01), self.input_poll_interval_seconds))

        return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._active_outputs.clear()
            self._manual_holds.clear()
            self._snapshot.active_output_count = 0
            self._snapshot.blocked_until_monotonic = 0.0
            self._snapshot.last_output_source = ""
            self._snapshot.last_output_preview = ""

        append_log("Audio coordinator reset.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_expired_holds_locked(self, now: float) -> None:
        expired_tokens = [
            token
            for token, hold in self._manual_holds.items()
            if float(hold.get("until", 0.0)) <= now
        ]
        for token in expired_tokens:
            self._manual_holds.pop(token, None)

    @staticmethod
    def _preview_text(text: str, max_chars: int = 60) -> str:
        compact = " ".join(str(text or "").split()).strip()
        if len(compact) <= max_chars:
            return compact
        return f"{compact[: max_chars - 3].rstrip()}..."


__all__ = [
    "AudioCoordinator",
    "AudioCoordinatorSnapshot",
]