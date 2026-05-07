#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_TELEMETRY_PATH = Path("var/data/focus_vision_sentinel.jsonl")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nested_dict(value: Any, key: str) -> dict[str, Any]:
    if isinstance(value, dict):
        nested = value.get(key, {})
        if isinstance(nested, dict):
            return nested
    return {}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_focus_config(settings_path: Path) -> dict[str, Any]:
    settings = _load_json(settings_path)
    focus_vision = settings.get("focus_vision", {})
    if not isinstance(focus_vision, dict):
        return {}
    return dict(focus_vision)


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _state_from_record(record: dict[str, Any]) -> str:
    snapshot = _nested_dict(record, "snapshot")
    state = str(snapshot.get("current_state") or "").strip()
    return state or "unknown"


def _summarize_telemetry(path: Path) -> dict[str, Any]:
    records = _iter_jsonl(path)
    states = Counter(_state_from_record(record) for record in records)
    reminder_count = sum(1 for record in records if record.get("reminder") is not None)
    delivered_count = sum(1 for record in records if _as_bool(record.get("reminder_delivered")))
    delivery_error_count = sum(1 for record in records if record.get("reminder_delivery_error"))
    latest = records[-1] if records else {}

    return {
        "path": str(path),
        "exists": path.exists(),
        "valid_json_records": len(records),
        "states": dict(sorted(states.items())),
        "latest_state": _state_from_record(latest) if latest else None,
        "reminder_candidate_count": reminder_count,
        "reminder_delivered_count": delivered_count,
        "reminder_delivery_error_count": delivery_error_count,
    }


def inspect_focus_vision_dry_run_readiness(
    *,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    telemetry_path: Path = DEFAULT_TELEMETRY_PATH,
    require_telemetry: bool = False,
) -> dict[str, Any]:
    focus_config = _load_focus_config(settings_path)
    enabled = _as_bool(focus_config.get("enabled"))
    dry_run = _as_bool(focus_config.get("dry_run"))
    voice_warnings_enabled = _as_bool(focus_config.get("voice_warnings_enabled"))
    pan_tilt_scan_enabled = _as_bool(focus_config.get("pan_tilt_scan_enabled"))
    interval = _as_float(focus_config.get("observation_interval_seconds"), default=0.0)
    telemetry = _summarize_telemetry(telemetry_path)

    failures: list[str] = []
    warnings: list[str] = []

    if not enabled:
        failures.append("focus_vision.enabled must be true for Sprint 4 dry-run observation.")
    if not dry_run:
        failures.append("focus_vision.dry_run must stay true during Sprint 4.")
    if voice_warnings_enabled:
        failures.append("focus_vision.voice_warnings_enabled must stay false during Sprint 4.")
    if pan_tilt_scan_enabled:
        failures.append("focus_vision.pan_tilt_scan_enabled must stay false during Sprint 4.")
    if interval <= 0.0:
        failures.append("focus_vision.observation_interval_seconds must be positive.")
    elif interval > 1.5:
        warnings.append("Observation interval is above 1.5 seconds; keep it near 1.0 for responsive telemetry.")
    if require_telemetry and telemetry["valid_json_records"] <= 0:
        failures.append("Focus Vision telemetry is required but no valid JSONL records were found.")

    return {
        "ok": not failures,
        "settings_path": str(settings_path),
        "focus_vision": {
            "enabled": enabled,
            "dry_run": dry_run,
            "voice_warnings_enabled": voice_warnings_enabled,
            "pan_tilt_scan_enabled": pan_tilt_scan_enabled,
            "observation_interval_seconds": interval,
            "telemetry_path": str(focus_config.get("telemetry_path") or telemetry_path),
        },
        "telemetry": telemetry,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Focus Vision Sprint 4 dry-run readiness.")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--require-telemetry", action="store_true")
    args = parser.parse_args()

    summary = inspect_focus_vision_dry_run_readiness(
        settings_path=args.settings,
        telemetry_path=args.telemetry,
        require_telemetry=args.require_telemetry,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
