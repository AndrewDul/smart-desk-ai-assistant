from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BenchmarkThresholdCheck:
    key: str
    ok: bool
    actual: float | int | str | None
    expected: float | int | str | None
    details: str
    comparator: str = ""


@dataclass(slots=True)
class BenchmarkValidationSegment:
    key: str
    label: str
    sample_count: int
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[BenchmarkThresholdCheck] = field(default_factory=list)

    def failed_checks(self) -> list[BenchmarkThresholdCheck]:
        return [check for check in self.checks if not check.ok]


@dataclass(slots=True)
class TurnBenchmarkValidationResult:
    ok: bool
    path: str
    sample_count: int
    window_sample_count: int
    latest_turn_id: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[BenchmarkThresholdCheck] = field(default_factory=list)
    segments: list[BenchmarkValidationSegment] = field(default_factory=list)

    def failed_checks(self) -> list[BenchmarkThresholdCheck]:
        return [check for check in self.checks if not check.ok]