from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class StartupGateDecision:
    runtime_mode: str
    startup_allowed: bool
    primary_ready: bool
    premium_ready: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    abort_startup: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class BootLifecycleDecision:
    method_name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)