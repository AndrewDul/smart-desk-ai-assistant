from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ReleaseChecklistItem:
    key: str
    ok: bool
    details: str
    remediation: str = ""
    source: str = ""


@dataclass(slots=True)
class PremiumReleaseGateResult:
    ok: bool
    verdict: str
    benchmark_path: str
    benchmark_window_sample_count: int
    runtime_status_path: str
    lifecycle_state: str = ""
    startup_mode: str = ""
    primary_ready: bool = False
    premium_ready: bool = False
    failed_check_keys: list[str] = field(default_factory=list)
    checklist: list[ReleaseChecklistItem] = field(default_factory=list)

    def failed_items(self) -> list[ReleaseChecklistItem]:
        return [item for item in self.checklist if not item.ok]