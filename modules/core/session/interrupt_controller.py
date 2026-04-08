from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InterruptSnapshot:
    """
    Immutable view of the current interrupt state.
    """

    requested: bool
    generation: int
    reason: str = ""
    source: str = ""
    requested_at_monotonic: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        if not self.requested or self.requested_at_monotonic <= 0.0:
            return 0.0
        return max(0.0, time.monotonic() - self.requested_at_monotonic)


class InteractionInterruptController:
    """
    Central interruption gate for speaking / streaming / active interaction.

    Design goals:
    - thread-safe
    - cheap to poll from low-latency streaming code
    - generation counter so newer interrupts can be distinguished from older ones
    - compatible with both immediate checks and wait-based loops
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._event = threading.Event()
        self._requested = False
        self._generation = 0
        self._reason = ""
        self._source = ""
        self._requested_at_monotonic = 0.0
        self._metadata: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Core state transitions
    # ------------------------------------------------------------------

    def request(
        self,
        *,
        reason: str = "",
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> InterruptSnapshot:
        """
        Raise an interrupt request and return the new snapshot.

        Every new request increments the generation counter so downstream
        components can detect whether they are still handling the latest
        cancellation/override.
        """
        with self._lock:
            self._requested = True
            self._generation += 1
            self._reason = str(reason or "").strip()
            self._source = str(source or "").strip()
            self._requested_at_monotonic = time.monotonic()
            self._metadata = dict(metadata or {})
            self._event.set()
            return self.snapshot()

    def clear(self) -> None:
        """
        Clear the current interrupt flag but keep the generation number.

        I do not reset the generation because it should represent the history
        of interrupt requests over the session lifetime.
        """
        with self._lock:
            self._requested = False
            self._reason = ""
            self._source = ""
            self._requested_at_monotonic = 0.0
            self._metadata = {}
            self._event.clear()

    def acknowledge(self) -> InterruptSnapshot:
        """
        Alias kept for semantic clarity in streaming code.

        Some call sites may conceptually "acknowledge" an interrupt before
        continuing; this simply returns the snapshot and clears the flag.
        """
        with self._lock:
            snapshot = self.snapshot()
            self.clear()
            return snapshot

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_requested(self) -> bool:
        with self._lock:
            return self._requested

    def requested_generation(self) -> int:
        with self._lock:
            return self._generation

    def reason(self) -> str:
        with self._lock:
            return self._reason

    def source(self) -> str:
        with self._lock:
            return self._source

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._metadata)

    def age_seconds(self) -> float:
        with self._lock:
            if not self._requested or self._requested_at_monotonic <= 0.0:
                return 0.0
            return max(0.0, time.monotonic() - self._requested_at_monotonic)

    def snapshot(self) -> InterruptSnapshot:
        with self._lock:
            return InterruptSnapshot(
                requested=self._requested,
                generation=self._generation,
                reason=self._reason,
                source=self._source,
                requested_at_monotonic=self._requested_at_monotonic,
                metadata=dict(self._metadata),
            )

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    def wait(self, timeout: float | None = None) -> bool:
        """
        Block until an interrupt is requested or timeout elapses.

        Returns:
            True  -> interrupt became active
            False -> timeout elapsed without an interrupt
        """
        return self._event.wait(timeout=timeout)

    def wait_for_new_generation(
        self,
        generation: int,
        *,
        timeout: float | None = None,
        poll_interval: float = 0.02,
    ) -> InterruptSnapshot | None:
        """
        Wait until a newer interrupt generation appears.

        Useful when a caller wants to know whether an *additional* interrupt
        happened after some piece of work started.
        """
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        safe_poll = max(0.005, float(poll_interval))

        while True:
            snapshot = self.snapshot()
            if snapshot.generation > generation and snapshot.requested:
                return snapshot

            if deadline is not None and time.monotonic() >= deadline:
                return None

            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            self._event.wait(timeout=safe_poll if remaining is None else min(safe_poll, remaining))

    # ------------------------------------------------------------------
    # Context manager style helper
    # ------------------------------------------------------------------

    def scoped_generation(self) -> int:
        """
        Return the current generation marker.

        Callers can store this before a long operation and later compare it
        against a fresh snapshot to detect whether a newer interrupt happened.
        """
        with self._lock:
            return self._generation


__all__ = [
    "InterruptSnapshot",
    "InteractionInterruptController",
]