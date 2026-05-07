#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
BACKUP_DIR = ROOT / "var" / "backups" / f"focus_vision_sprint6_docs_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

ARCH_MARKER = "Focus Vision Sentinel Sprint 6 responsive cached-observation ticks"
TROUBLE_MARKER = "Focus Vision Sprint 6 telemetry cadence and stale-observation notes"

ARCH_ENTRY = f"""

## 2026-05-07 — {ARCH_MARKER}

### Summary

Focus Vision Sentinel now reads the latest cached vision observation by default instead of forcing a fresh camera/perception refresh on every sentinel tick. This keeps the Focus Mode monitoring loop responsive and aligned with the product target that reminder decisions should be available within roughly 3 seconds after a stable condition threshold is crossed.

### Architecture changes

- `focus_vision.latest_observation_force_refresh` now defaults to `false` for Focus Vision.
- Added `focus_vision.max_observation_age_seconds` with a default of `8.0` seconds.
- `FocusVisionSentinelService` now records observation freshness in telemetry:
  - `latest_observation_force_refresh`,
  - `observation_age_seconds`,
  - `observation_stale`.
- Time stabilization now uses the sentinel tick clock, not the camera frame timestamp, so cached observations can still produce timely stable-state durations while the camera pipeline updates asynchronously.
- If the cached observation becomes older than the configured max age, the sentinel treats it as `no_observation` instead of trusting stale evidence.
- `scripts/analyze_focus_vision_telemetry.py` now reports force-refresh and stale-observation counts.

### Safety boundaries

- Voice warnings remain controlled by `focus_vision.voice_warnings_enabled`.
- Dry-run can remain enabled for observation-only validation.
- Pan-tilt scanning remains disabled and is not part of this sprint.
- Mobile-base movement remains disabled.

### Validation target

Run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/features/focus_vision tests/scripts/test_analyze_focus_vision_telemetry.py tests/vision/unit/runtime/test_focus_vision_focus_mode_hooks.py tests/vision/unit/runtime/test_focus_vision_builder_integration.py tests/vision/unit/runtime/test_ai_broker_focus_hooks.py tests/vision/unit/runtime/test_ai_broker_service.py tests/vision/unit/behavior/test_pipeline.py tests/vision/unit/behavior/phone_usage/test_interpreter.py

### Next step

Run another Focus Mode dry-run session and analyze `var/data/focus_vision_sentinel.jsonl`. The expected improvement is a lower `max_gap_seconds`, ideally near the configured 1-second interval and below the 3-second warning threshold.
"""

TROUBLE_ENTRY = f"""

## 2026-05-07 — {TROUBLE_MARKER}

### Status

A previous real Focus Mode dry-run produced correct states (`on_task`, `absent`, and `phone_distraction`) but showed a largest telemetry gap of about 5.35 seconds. That is too slow for the target Focus Mode UX, where reminder decisions should be ready within roughly 3 seconds after a stable threshold is crossed.

### Root cause direction

Focus Vision was forcing a fresh latest observation on every sentinel tick. In the real camera pipeline, this can block behind camera/perception cadence and stretch the sentinel telemetry interval even though `focus_vision.observation_interval_seconds=1.0`.

### Sprint 6 fix

Expected settings after Sprint 6:

- `focus_vision.latest_observation_force_refresh=false`,
- `focus_vision.max_observation_age_seconds=8.0`,
- `focus_vision.dry_run=true` during validation,
- `focus_vision.voice_warnings_enabled=false` until spoken-warning validation,
- `focus_vision.pan_tilt_scan_enabled=false`.

### Validation commands

Run a fresh Focus Mode dry-run and then inspect:

    python3 scripts/analyze_focus_vision_telemetry.py --require-records --require-state absent --require-state phone_distraction

If `max_gap_seconds` is still above `3.0`, check whether telemetry contains:

- `latest_observation_force_refresh_values` with `true`,
- `observation_stale_values` with `true`,
- runtime errors in `last_error`.

### If stale observations appear

If `observation_stale=true` appears often, the camera/perception backend is not updating observations fast enough for Focus Mode. Keep voice warnings disabled and inspect camera/perception cadence before enabling spoken reminders.
"""


def backup(path: Path) -> None:
    if not path.exists():
        return
    target = BACKUP_DIR / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def append_once(path: Path, marker: str, entry: str) -> bool:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return False
    path.write_text(text.rstrip() + entry.rstrip() + "\n", encoding="utf-8")
    return True


def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    architecture_path = Path("docs/architecture_notes.md")
    troubleshooting_path = Path("docs/troubleshooting.md")
    backup(architecture_path)
    backup(troubleshooting_path)
    changed = {
        str(architecture_path): append_once(architecture_path, ARCH_MARKER, ARCH_ENTRY),
        str(troubleshooting_path): append_once(troubleshooting_path, TROUBLE_MARKER, TROUBLE_ENTRY),
    }
    print(json.dumps({"ok": True, "backup_dir": str(BACKUP_DIR), "changed": changed}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
