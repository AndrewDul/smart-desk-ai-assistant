#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
SAFE_ALLOWED_SPOKEN_KINDS = {"phone_distraction"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _load_settings(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_focus_vision_voice_readiness(
    *,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    allow_absence_voice: bool = False,
) -> dict[str, Any]:
    settings = _load_settings(settings_path)
    focus_vision = settings.get("focus_vision", {})
    if not isinstance(focus_vision, dict):
        focus_vision = {}

    enabled = _as_bool(focus_vision.get("enabled"))
    dry_run = _as_bool(focus_vision.get("dry_run"))
    voice_warnings_enabled = _as_bool(focus_vision.get("voice_warnings_enabled"))
    pan_tilt_scan_enabled = _as_bool(focus_vision.get("pan_tilt_scan_enabled"))
    enabled_reminder_kinds = _as_list(focus_vision.get("enabled_reminder_kinds"))
    enabled_kind_set = set(enabled_reminder_kinds)

    failures: list[str] = []
    warnings: list[str] = []

    if not enabled:
        failures.append("focus_vision.enabled must be true before spoken Focus Vision warnings can run.")
    if dry_run:
        failures.append("focus_vision.dry_run must be false for spoken Focus Vision warnings.")
    if not voice_warnings_enabled:
        failures.append("focus_vision.voice_warnings_enabled must be true for spoken Focus Vision warnings.")
    if pan_tilt_scan_enabled:
        failures.append("focus_vision.pan_tilt_scan_enabled must stay false during Sprint 7.")
    if "phone_distraction" not in enabled_kind_set:
        failures.append("focus_vision.enabled_reminder_kinds must include phone_distraction during Sprint 7.")
    if "absence" in enabled_kind_set and not allow_absence_voice:
        failures.append("focus_vision.enabled_reminder_kinds must not include absence during Sprint 7A.")

    unexpected = sorted(enabled_kind_set - SAFE_ALLOWED_SPOKEN_KINDS)
    if unexpected and not allow_absence_voice:
        warnings.append(f"Unexpected spoken reminder kinds for Sprint 7A: {unexpected}")

    return {
        "ok": not failures,
        "settings_path": str(settings_path),
        "focus_vision": {
            "enabled": enabled,
            "dry_run": dry_run,
            "voice_warnings_enabled": voice_warnings_enabled,
            "pan_tilt_scan_enabled": pan_tilt_scan_enabled,
            "enabled_reminder_kinds": enabled_reminder_kinds,
        },
        "sprint_scope": "phone_distraction_voice_only",
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Focus Vision Sprint 7 voice-readiness gates.")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument("--allow-absence-voice", action="store_true")
    args = parser.parse_args()

    summary = inspect_focus_vision_voice_readiness(
        settings_path=args.settings,
        allow_absence_voice=args.allow_absence_voice,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
