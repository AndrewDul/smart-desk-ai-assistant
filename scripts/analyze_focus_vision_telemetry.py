#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_TELEMETRY_PATH = Path("var/data/focus_vision_sentinel.jsonl")


@dataclass(slots=True)
class FocusVisionTelemetryRecord:
    line_number: int
    payload: dict[str, Any]

    @property
    def created_at(self) -> float | None:
        return _as_optional_float(self.payload.get("created_at"))

    @property
    def dry_run(self) -> bool | None:
        value = self.payload.get("dry_run")
        return value if isinstance(value, bool) else None

    @property
    def state(self) -> str:
        snapshot = _nested_dict(self.payload, "snapshot")
        state = str(snapshot.get("current_state") or "").strip()
        return state or "unknown"

    @property
    def stable_seconds(self) -> float:
        snapshot = _nested_dict(self.payload, "snapshot")
        return _as_float(snapshot.get("stable_seconds"), default=0.0)

    @property
    def decision_reasons(self) -> tuple[str, ...]:
        snapshot = _nested_dict(self.payload, "snapshot")
        decision = _nested_dict(snapshot, "decision")
        reasons = decision.get("reasons", [])
        if not isinstance(reasons, list):
            return ()
        return tuple(str(reason) for reason in reasons if str(reason).strip())

    @property
    def evidence(self) -> dict[str, Any]:
        snapshot = _nested_dict(self.payload, "snapshot")
        decision = _nested_dict(snapshot, "decision")
        return _nested_dict(decision, "evidence")

    @property
    def reminder_kind(self) -> str | None:
        reminder = self.payload.get("reminder")
        if not isinstance(reminder, dict):
            return None
        kind = str(reminder.get("kind") or "").strip()
        return kind or None

    @property
    def reminder_delivered(self) -> bool:
        return bool(self.payload.get("reminder_delivered") is True)

    @property
    def reminder_delivery_error(self) -> str | None:
        value = self.payload.get("reminder_delivery_error")
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def last_error(self) -> str | None:
        value = self.payload.get("last_error")
        if value is None:
            return None
        text = str(value).strip()
        return text or None


@dataclass(slots=True)
class FocusVisionTelemetryAnalysis:
    path: str
    exists: bool
    valid_records: int
    invalid_lines: int
    first_created_at: float | None
    last_created_at: float | None
    duration_seconds: float
    max_gap_seconds: float
    state_counts: dict[str, int]
    max_stable_seconds_by_state: dict[str, float]
    reminder_candidate_counts: dict[str, int]
    reminder_delivered_count: int
    reminder_delivery_error_count: int
    runtime_error_count: int
    dry_run_values: dict[str, int]
    reason_counts: dict[str, int]
    evidence_true_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "exists": self.exists,
            "valid_records": self.valid_records,
            "invalid_lines": self.invalid_lines,
            "first_created_at": self.first_created_at,
            "last_created_at": self.last_created_at,
            "duration_seconds": self.duration_seconds,
            "max_gap_seconds": self.max_gap_seconds,
            "state_counts": self.state_counts,
            "max_stable_seconds_by_state": self.max_stable_seconds_by_state,
            "reminder_candidate_counts": self.reminder_candidate_counts,
            "reminder_delivered_count": self.reminder_delivered_count,
            "reminder_delivery_error_count": self.reminder_delivery_error_count,
            "runtime_error_count": self.runtime_error_count,
            "dry_run_values": self.dry_run_values,
            "reason_counts": self.reason_counts,
            "evidence_true_counts": self.evidence_true_counts,
            "warnings": self.warnings,
            "failures": self.failures,
            "next_actions": _next_actions(self),
        }


def _as_optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, *, default: float) -> float:
    result = _as_optional_float(value)
    return default if result is None else result


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def _load_records(path: Path) -> tuple[list[FocusVisionTelemetryRecord], int]:
    records: list[FocusVisionTelemetryRecord] = []
    invalid_lines = 0
    if not path.exists():
        return records, invalid_lines

    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(payload, dict):
            invalid_lines += 1
            continue
        records.append(FocusVisionTelemetryRecord(line_number=line_number, payload=payload))
    return records, invalid_lines


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _max_gap(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        return 0.0
    return max(max(0.0, later - earlier) for earlier, later in zip(timestamps, timestamps[1:]))


def _dry_run_label(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def _collect_evidence_true_counts(records: Iterable[FocusVisionTelemetryRecord]) -> dict[str, int]:
    fields = (
        "detected",
        "presence_active",
        "desk_activity_active",
        "computer_work_active",
        "phone_usage_active",
        "study_activity_active",
    )
    counts: Counter[str] = Counter()
    for record in records:
        evidence = record.evidence
        for field_name in fields:
            if evidence.get(field_name) is True:
                counts[field_name] += 1
    return _counter_dict(counts)


def analyze_focus_vision_telemetry(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    require_records: bool = False,
    require_states: tuple[str, ...] = (),
    expected_dry_run: bool | None = True,
    max_expected_gap_seconds: float = 3.0,
) -> FocusVisionTelemetryAnalysis:
    records, invalid_lines = _load_records(path)
    timestamps = [timestamp for record in records if (timestamp := record.created_at) is not None]
    state_counts = Counter(record.state for record in records)
    reminder_counts = Counter(record.reminder_kind for record in records if record.reminder_kind is not None)
    reason_counts = Counter(reason for record in records for reason in record.decision_reasons)
    dry_run_values = Counter(_dry_run_label(record.dry_run) for record in records)
    max_stable: dict[str, float] = defaultdict(float)

    for record in records:
        max_stable[record.state] = max(max_stable[record.state], record.stable_seconds)

    first_created_at = min(timestamps) if timestamps else None
    last_created_at = max(timestamps) if timestamps else None
    duration = 0.0 if first_created_at is None or last_created_at is None else max(0.0, last_created_at - first_created_at)
    max_gap = _max_gap(sorted(timestamps))

    analysis = FocusVisionTelemetryAnalysis(
        path=str(path),
        exists=path.exists(),
        valid_records=len(records),
        invalid_lines=invalid_lines,
        first_created_at=first_created_at,
        last_created_at=last_created_at,
        duration_seconds=duration,
        max_gap_seconds=max_gap,
        state_counts=_counter_dict(state_counts),
        max_stable_seconds_by_state={key: round(value, 3) for key, value in sorted(max_stable.items())},
        reminder_candidate_counts=_counter_dict(reminder_counts),
        reminder_delivered_count=sum(1 for record in records if record.reminder_delivered),
        reminder_delivery_error_count=sum(1 for record in records if record.reminder_delivery_error),
        runtime_error_count=sum(1 for record in records if record.last_error),
        dry_run_values=_counter_dict(dry_run_values),
        reason_counts=_counter_dict(reason_counts),
        evidence_true_counts=_collect_evidence_true_counts(records),
    )

    if require_records and not records:
        analysis.failures.append("No valid Focus Vision telemetry records were found.")
    if invalid_lines:
        analysis.warnings.append(f"Ignored {invalid_lines} invalid JSONL line(s).")
    if analysis.runtime_error_count:
        analysis.warnings.append("Some Focus Vision ticks reported runtime errors. Inspect last_error in the JSONL log.")
    if analysis.reminder_delivery_error_count:
        analysis.warnings.append("Some reminder delivery attempts failed. Keep voice warnings disabled until this is resolved.")
    if expected_dry_run is not None:
        unexpected = "false" if expected_dry_run else "true"
        if dry_run_values.get(unexpected, 0) > 0:
            analysis.failures.append(f"Unexpected dry_run={unexpected} records were found.")
    if max_expected_gap_seconds > 0 and max_gap > max_expected_gap_seconds:
        analysis.warnings.append(
            f"Largest telemetry gap is {max_gap:.2f}s; expected at most {max_expected_gap_seconds:.2f}s."
        )
    for state in require_states:
        if state not in state_counts:
            analysis.failures.append(f"Required Focus Vision state was not observed: {state}")

    return analysis


def _next_actions(analysis: FocusVisionTelemetryAnalysis) -> list[str]:
    if analysis.valid_records <= 0:
        return [
            "Start Focus Mode with Sprint 4 dry-run enabled and keep runtime open for at least 30 seconds.",
            "If the file is still empty, check whether focus_vision.enabled=true and whether the vision backend is available.",
        ]

    actions: list[str] = []
    states = analysis.state_counts
    evidence = analysis.evidence_true_counts
    if states.get("no_observation", 0) == analysis.valid_records:
        actions.append("All records are no_observation; inspect camera/perception backend availability before tuning thresholds.")
    if evidence.get("presence_active", 0) == 0:
        actions.append("No active presence evidence was observed; run a seated-at-desk scenario and check face/person detection.")
    if "absent" not in states:
        actions.append("Run an absence scenario by leaving the desk for at least 30 seconds.")
    if "phone_distraction" not in states:
        actions.append("Run a phone scenario by holding the phone in the normal usage position for 10-15 seconds.")
    if not actions:
        actions.append("Telemetry covers the core states; use these counts to tune thresholds before enabling spoken warnings.")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Focus Vision Sentinel JSONL telemetry.")
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--require-records", action="store_true")
    parser.add_argument("--require-state", action="append", default=[])
    parser.add_argument("--allow-non-dry-run", action="store_true")
    parser.add_argument("--max-gap-seconds", type=float, default=3.0)
    args = parser.parse_args()

    analysis = analyze_focus_vision_telemetry(
        args.telemetry,
        require_records=args.require_records,
        require_states=tuple(args.require_state),
        expected_dry_run=None if args.allow_non_dry_run else True,
        max_expected_gap_seconds=args.max_gap_seconds,
    )
    print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if analysis.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
