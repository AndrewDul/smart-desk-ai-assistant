from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ValidationCaptureSegmentProgress:
    key: str
    label: str
    current_samples: int
    required_samples: int
    missing_samples: int
    ok: bool
    failed_check_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationCaptureScenarioView:
    key: str
    title: str
    objective: str
    target_segments: list[str] = field(default_factory=list)
    min_turns: int = 0
    prompts: list[str] = field(default_factory=list)
    expected_signals: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationCaptureStageView:
    key: str
    title: str
    goal: str
    notes: list[str] = field(default_factory=list)
    scenarios: list[ValidationCaptureScenarioView] = field(default_factory=list)


@dataclass(slots=True)
class ValidationCaptureRuntimeStatusView:
    path: str
    exists: bool
    lifecycle_state: str = ""
    startup_mode: str = ""
    primary_ready: bool = False
    premium_ready: bool = False
    updated_at_iso: str = ""


@dataclass(slots=True)
class PremiumValidationCaptureSnapshot:
    benchmark_ok: bool
    benchmark_path: str
    total_samples: int
    window_samples: int
    latest_turn_id: str = ""
    benchmark_updated_at_iso: str = ""
    benchmark_file_age_seconds: float | None = None
    priority_segments: list[str] = field(default_factory=list)
    segment_progress: list[ValidationCaptureSegmentProgress] = field(default_factory=list)
    runtime_status: ValidationCaptureRuntimeStatusView | None = None
    activity_hints: list[str] = field(default_factory=list)
    stage: ValidationCaptureStageView | None = None


__all__ = [
    "PremiumValidationCaptureSnapshot",
    "ValidationCaptureRuntimeStatusView",
    "ValidationCaptureScenarioView",
    "ValidationCaptureSegmentProgress",
    "ValidationCaptureStageView",
]