#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path("var/data/focus_vision_sentinel.jsonl")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            output.append(item)
    return output


def _snapshot(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("snapshot")
    return value if isinstance(value, dict) else {}


def _decision(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("decision")
    return value if isinstance(value, dict) else {}


def _evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    decision = _decision(snapshot)
    value = decision.get("evidence")
    return value if isinstance(value, dict) else {}


def _labels(evidence: dict[str, Any]) -> list[str]:
    value = evidence.get("labels")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _state(record: dict[str, Any]) -> str:
    return str(_snapshot(record).get("current_state") or "unknown")


def _run_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current_state: str | None = None
    start_created_at = 0.0
    end_created_at = 0.0
    count = 0
    max_stable = 0.0

    for record in records:
        state = _state(record)
        created_at = _as_float(record.get("created_at"))
        stable = _as_float(_snapshot(record).get("stable_seconds"))

        if current_state is None:
            current_state = state
            start_created_at = created_at
            end_created_at = created_at
            count = 1
            max_stable = stable
            continue

        if state == current_state:
            end_created_at = created_at
            count += 1
            max_stable = max(max_stable, stable)
            continue

        runs.append({
            "state": current_state,
            "start_created_at": round(start_created_at, 3),
            "end_created_at": round(end_created_at, 3),
            "duration_seconds": round(max(0.0, end_created_at - start_created_at), 3),
            "records": count,
            "max_stable_seconds": round(max_stable, 3),
        })

        current_state = state
        start_created_at = created_at
        end_created_at = created_at
        count = 1
        max_stable = stable

    if current_state is not None:
        runs.append({
            "state": current_state,
            "start_created_at": round(start_created_at, 3),
            "end_created_at": round(end_created_at, 3),
            "duration_seconds": round(max(0.0, end_created_at - start_created_at), 3),
            "records": count,
            "max_stable_seconds": round(max_stable, 3),
        })
    return runs


def analyze(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    records = _records(path)
    state_counts = Counter(_state(record) for record in records)
    label_counts: Counter[str] = Counter()
    absent_label_counts: Counter[str] = Counter()
    on_task_label_counts: Counter[str] = Counter()
    stale_counts: Counter[str] = Counter()
    absence_blockers: Counter[str] = Counter()

    selected: list[dict[str, Any]] = []

    for record in records:
        snapshot = _snapshot(record)
        evidence = _evidence(snapshot)
        labels = _labels(evidence)
        state = _state(record)

        label_counts.update(labels)
        stale_counts[str(bool(record.get("observation_stale"))).lower()] += 1

        if state == "absent":
            absent_label_counts.update(labels)
        if state == "on_task":
            on_task_label_counts.update(labels)

        person_visible = any(label in {"object:person", "person_in_desk_zone"} for label in labels)
        face_visible = any(label in {"face_detected", "face_in_engagement_zone"} for label in labels)
        presence_active = bool(evidence.get("presence_active"))
        desk_activity_active = bool(evidence.get("desk_activity_active"))

        if state != "absent" and person_visible:
            absence_blockers["person_visible"] += 1
        if state != "absent" and face_visible:
            absence_blockers["face_visible"] += 1
        if state != "absent" and presence_active:
            absence_blockers["presence_active"] += 1
        if state != "absent" and desk_activity_active:
            absence_blockers["desk_activity_active"] += 1

        if state in {"absent", "on_task", "no_observation", "uncertain"}:
            selected.append({
                "created_at": round(_as_float(record.get("created_at")), 3),
                "state": state,
                "stable_seconds": snapshot.get("stable_seconds"),
                "observation_age_seconds": record.get("observation_age_seconds"),
                "observation_stale": record.get("observation_stale"),
                "presence_active": evidence.get("presence_active"),
                "desk_activity_active": evidence.get("desk_activity_active"),
                "presence_confidence": evidence.get("presence_confidence"),
                "desk_activity_confidence": evidence.get("desk_activity_confidence"),
                "labels": labels,
            })

    runs = _run_summary(records)
    longest_runs = sorted(runs, key=lambda item: item["max_stable_seconds"], reverse=True)[:10]

    return {
        "ok": bool(records),
        "path": str(path),
        "valid_records": len(records),
        "state_counts": dict(sorted(state_counts.items())),
        "max_stable_absent_seconds": max(
            (float(run["max_stable_seconds"]) for run in runs if run["state"] == "absent"),
            default=0.0,
        ),
        "longest_runs": longest_runs,
        "absence_blockers_when_not_absent": dict(sorted(absence_blockers.items())),
        "stale_counts": dict(sorted(stale_counts.items())),
        "top_labels": dict(label_counts.most_common(15)),
        "top_absent_labels": dict(absent_label_counts.most_common(15)),
        "top_on_task_labels": dict(on_task_label_counts.most_common(15)),
        "last_25_selected_records": selected[-25:],
        "next_actions": [
            "For absent warning, max_stable_absent_seconds should be >= 10.",
            "If on_task labels still include face_detected/person_in_desk_zone after you leave, narrow desk/engagement zones.",
            "If no_observation interrupts absence, tune observation freshness or add an away-from-desk continuity tracker.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Focus Vision desk absence calibration telemetry.")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()

    summary = analyze(args.path)
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
