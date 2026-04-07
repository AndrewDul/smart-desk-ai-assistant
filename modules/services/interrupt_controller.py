from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class InterruptSnapshot:
    requested: bool
    generation: int
    reason: str = ""
    source: str = ""
    requested_at_monotonic: float = 0.0
    metadata: dict | None = field(default_factory=dict)


class InteractionInterruptController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requested = False
        self._generation = 0
        self._reason = ""
        self._source = ""
        self._requested_at_monotonic = 0.0
        self._metadata: dict = {}

    def request(
        self,
        *,
        reason: str,
        source: str,
        metadata: dict | None = None,
    ) -> InterruptSnapshot:
        with self._lock:
            self._requested = True
            self._generation += 1
            self._reason = str(reason or "").strip()
            self._source = str(source or "").strip()
            self._requested_at_monotonic = time.monotonic()
            self._metadata = dict(metadata or {})

            return InterruptSnapshot(
                requested=True,
                generation=self._generation,
                reason=self._reason,
                source=self._source,
                requested_at_monotonic=self._requested_at_monotonic,
                metadata=dict(self._metadata),
            )

    def clear(self) -> None:
        with self._lock:
            self._requested = False
            self._reason = ""
            self._source = ""
            self._requested_at_monotonic = 0.0
            self._metadata = {}

    def is_requested(self) -> bool:
        with self._lock:
            return self._requested

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