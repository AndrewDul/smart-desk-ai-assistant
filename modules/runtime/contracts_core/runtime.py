from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .protocols import DisplayBackend, SpeechInputBackend, SpeechOutputBackend, WakeGateBackend


@dataclass(slots=True)
class RuntimeBackendStatus:
    """Health and fallback status for one runtime component."""

    component: str
    ok: bool
    selected_backend: str
    detail: str = ""
    fallback_used: bool = False


@dataclass(slots=True)
class RuntimeServices:
    """
    Runtime container passed across the assistant stack.

    Strong typing for the core hardware-facing surfaces is preserved.
    Everything else remains generic so the architecture can evolve
    without forcing wide contract churn.
    """

    settings: dict[str, Any]
    voice_input: SpeechInputBackend
    voice_output: SpeechOutputBackend
    display: DisplayBackend
    wake_gate: WakeGateBackend | None = None
    parser: Any | None = None
    router: Any | None = None
    dialogue: Any | None = None
    memory: Any | None = None
    reminders: Any | None = None
    timer: Any | None = None
    backend_statuses: dict[str, RuntimeBackendStatus] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def backend_status(self, component: str) -> RuntimeBackendStatus | None:
        return self.backend_statuses.get(component)


__all__ = [
    "RuntimeBackendStatus",
    "RuntimeServices",
]