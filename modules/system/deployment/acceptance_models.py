from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BootAcceptanceCheck:
    key: str
    ok: bool
    details: str
    remediation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SystemdBootAcceptanceResult:
    ok: bool
    strict_premium: bool
    system_dir: str
    runtime_status_path: str
    checked_unit_names: list[str] = field(default_factory=list)
    checks: list[BootAcceptanceCheck] = field(default_factory=list)
    unit_states: dict[str, dict[str, str]] = field(default_factory=dict)
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    journal_tails: dict[str, str] = field(default_factory=dict)

    def failed_checks(self) -> list[BootAcceptanceCheck]:
        return [check for check in self.checks if not check.ok]