from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ValidationCommand:
    label: str
    command: str
    requires_sudo: bool = False


@dataclass(slots=True)
class ValidationScenario:
    key: str
    title: str
    objective: str
    target_segments: list[str] = field(default_factory=list)
    min_turns: int = 0
    prompts: list[str] = field(default_factory=list)
    expected_signals: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationFlowStage:
    key: str
    title: str
    goal: str
    commands: list[ValidationCommand] = field(default_factory=list)
    scenarios: list[ValidationScenario] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PremiumValidationFlow:
    benchmark_ok: bool
    benchmark_path: str
    benchmark_window_sample_count: int
    latest_turn_id: str = ""
    priority_segments: list[str] = field(default_factory=list)
    failed_check_keys: list[str] = field(default_factory=list)
    stages: list[ValidationFlowStage] = field(default_factory=list)