from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HealthSeverity(str, Enum):
    """Severity assigned to one runtime health item."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class HealthCheckItem:
    """One startup/runtime diagnostic result."""

    name: str
    ok: bool
    details: str
    severity: HealthSeverity = HealthSeverity.INFO
    critical: bool = True

    @property
    def is_warning(self) -> bool:
        return self.severity == HealthSeverity.WARNING

    @property
    def is_error(self) -> bool:
        return self.severity == HealthSeverity.ERROR


@dataclass(slots=True)
class HealthCheckReport:
    """Aggregate startup/runtime diagnostic result."""

    ok: bool
    items: list[HealthCheckItem] = field(default_factory=list)

    @property
    def startup_allowed(self) -> bool:
        return not any((not item.ok) and item.critical for item in self.items)

    @property
    def warnings(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.is_warning]

    @property
    def errors(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.is_error]

    @property
    def passed(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.ok]

    @property
    def failed(self) -> list[HealthCheckItem]:
        return [item for item in self.items if not item.ok]

    def summary_lines(self) -> list[str]:
        if not self.items:
            return ["no checks"]

        passed_count = len(self.passed)
        total_count = len(self.items)

        if self.failed:
            first_failed = self.failed[0]
            return [
                f"{passed_count} / {total_count} ready",
                f"issue: {first_failed.name}",
            ]

        if self.warnings:
            return [
                "startup checks ok",
                f"{passed_count} / {total_count} ready, warnings={len(self.warnings)}",
            ]

        return [
            "startup checks ok",
            f"{passed_count} / {total_count} ready",
        ]


__all__ = [
    "HealthCheckItem",
    "HealthCheckReport",
    "HealthSeverity",
]