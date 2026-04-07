from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from modules.system.utils import append_log


@dataclass(slots=True)
class AudioCoordinatorSnapshot:
    active_output_count: int = 0
    blocked_until_monotonic: float = 0.0
    last_output_started_monotonic: float = 0.0
    last_output_finished_monotonic: float = 0.0
    last_output_source: str = ""
    last_output_preview: str = ""
    active_tokens: tuple[str, ...] = field(default_factory=tuple)


class AssistantAudioCoordinator:
    """
    Cross-cutting audio coordination for premium voice UX.

    Responsibilities:
    - declare when assistant playback is active
    - keep a short post-speech shield to reduce self-hearing
    - expose a cheap `input_blocked()` signal for wake/STT frontends

    Important design choice:
    this service does not know anything about intents, follow-ups, or UI.
    It only coordinates audio lifecycle.
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
        self._active_outputs: dict[str, dict[str, str | float]] = {}
        self._snapshot = AudioCoordinatorSnapshot()

    def snapshot(self) -> AudioCoordinatorSnapshot:
        with self._lock:
            return AudioCoordinatorSnapshot(
                active_output_count=self._snapshot.active_output_count,
                blocked_until_monotonic=self._snapshot.blocked_until_monotonic,
                last_output_started_monotonic=self._snapshot.last_output_started_monotonic,
                last_output_finished_monotonic=self._snapshot.last_output_finished_monotonic,
                last_output_source=self._snapshot.last_output_source,
                last_output_preview=self._snapshot.last_output_preview,
                active_tokens=tuple(self._active_outputs.keys()),
            )

    def begin_assistant_output(
        self,
        *,
        source: str,
        text_preview: str = "",
    ) -> str:
        token = uuid.uuid4().hex
        now = time.monotonic()
        preview = self._preview_text(text_preview)

        with self._lock:
            self._active_outputs[token] = {
                "source": str(source or "assistant_output"),
                "preview": preview,
                "started_at": now,
            }
            self._snapshot.active_output_count = len(self._active_outputs)
            self._snapshot.last_output_started_monotonic = now
            self._snapshot.last_output_source = str(source or "assistant_output")
            self._snapshot.last_output_preview = preview

        append_log(
            "Audio coordinator: assistant output started "
            f"source={source}, active_outputs={self._snapshot.active_output_count}, preview={preview}"
        )
        return token

    def end_assistant_output(self, token: str | None, *, hold_seconds: float | None = None) -> None:
        if not token:
            return

        now = time.monotonic()
        effective_hold = self.post_speech_hold_seconds if hold_seconds is None else max(0.0, float(hold_seconds))

        with self._lock:
            output_info = self._active_outputs.pop(token, None)
            if output_info is None:
                return

            self._snapshot.active_output_count = len(self._active_outputs)
            if not self._active_outputs:
                self._snapshot.last_output_finished_monotonic = now
                self._snapshot.blocked_until_monotonic = max(
                    self._snapshot.blocked_until_monotonic,
                    now + effective_hold,
                )

        append_log(
            "Audio coordinator: assistant output finished "
            f"source={output_info.get('source')}, active_outputs={self._snapshot.active_output_count}, "
            f"hold_seconds={effective_hold:.2f}"
        )

    def input_blocked(self) -> bool:
        with self._lock:
            if self._active_outputs:
                return True
            return time.monotonic() < self._snapshot.blocked_until_monotonic

    def time_until_input_unblocked(self) -> float:
        with self._lock:
            if self._active_outputs:
                return max(self.input_poll_interval_seconds, 0.0)
            remaining = self._snapshot.blocked_until_monotonic - time.monotonic()
            return max(0.0, remaining)

    def wait_until_input_allowed(self, max_wait_seconds: float | None = None) -> bool:
        deadline = None if max_wait_seconds is None else (time.monotonic() + max(0.0, float(max_wait_seconds)))

        while self.input_blocked():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(self.input_poll_interval_seconds)

        return True

    @staticmethod
    def _preview_text(text: str, max_chars: int = 80) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."