#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "var" / "backups" / f"focus_vision_sprint5_docs_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

ARCH_MARKER = "Focus Vision Sprint 5 telemetry analysis tooling"
TROUBLE_MARKER = "Focus Vision Sprint 5 telemetry analyzer troubleshooting"

ARCH_ENTRY = """

## 2026-05-07 — Focus Vision Sprint 5 telemetry analysis tooling

### Summary

Added a dedicated Focus Vision telemetry analyzer so Focus Mode dry-run sessions can be evaluated from `var/data/focus_vision_sentinel.jsonl` before spoken warnings are enabled.

### Architecture changes

- Added `scripts/analyze_focus_vision_telemetry.py`.
- The analyzer reads the existing Focus Vision Sentinel JSONL stream and reports:
  - observed Focus Vision states,
  - maximum stable time per state,
  - reminder candidate counts,
  - dry-run safety values,
  - runtime errors and delivery errors,
  - evidence activity counters for presence, desk activity, computer work, phone usage, and study activity.
- The analyzer is intentionally read-only. It does not change runtime settings, does not speak, does not move pan-tilt, and does not move the mobile base.
- This keeps Sprint 5 focused on real observation quality and threshold tuning before enabling voice warnings.

### Validation target

Run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/scripts/test_analyze_focus_vision_telemetry.py

Then after a real Focus Mode dry-run session:

    python3 scripts/analyze_focus_vision_telemetry.py --require-records

Optional scenario checks:

    python3 scripts/analyze_focus_vision_telemetry.py --require-records --require-state absent --require-state phone_distraction

### Next step

Use the analyzer output after a real desk/absence/phone test to tune Focus Vision thresholds and workspace zones before enabling spoken PL/EN reminders.
"""

TROUBLE_ENTRY = """

## 2026-05-07 — Focus Vision Sprint 5 telemetry analyzer troubleshooting

### Status

Sprint 5 adds telemetry analysis only. It should not change runtime behaviour.

### Basic command

Run after a Focus Mode dry-run session:

    python3 scripts/analyze_focus_vision_telemetry.py --require-records

### If the analyzer says no records were found

Check:

    ls -la var/data/focus_vision_sentinel.jsonl
    tail -n 20 var/data/focus_vision_sentinel.jsonl
    python3 scripts/check_focus_vision_dry_run_readiness.py

Likely causes:

1. Focus Mode was not started.
2. Runtime was not restarted after enabling `focus_vision.enabled=true`.
3. The vision backend did not attach to the runtime builder.
4. The telemetry path was changed in `config/settings.json`.

### If all states are `no_observation`

This means the Focus Vision service is running, but it is not receiving usable `VisionObservation` data. Check camera/perception runtime readiness before tuning thresholds.

### If `absent` never appears

Run a dedicated absence scenario: start Focus Mode, leave the desk for at least 30 seconds, then analyze telemetry again.

### If `phone_distraction` never appears

Run a dedicated phone scenario: start Focus Mode, sit at the desk, hold the phone in normal use position for 10-15 seconds, then analyze telemetry again. If the state still does not appear, tune phone detection evidence and workspace zones before enabling spoken reminders.

### If dry-run is false

During this sprint dry-run should remain true. Re-check safe settings before continuing:

    python3 scripts/check_focus_vision_dry_run_readiness.py
"""


def _backup(path: Path) -> None:
    if not path.exists():
        return
    target = BACKUP_DIR / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def _append_once(path: Path, marker: str, entry: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return False
    path.write_text(text.rstrip() + entry.rstrip() + "\n", encoding="utf-8")
    return True


def main() -> int:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    architecture_path = ROOT / "docs" / "architecture_notes.md"
    troubleshooting_path = ROOT / "docs" / "troubleshooting.md"

    for path in (architecture_path, troubleshooting_path):
        if not path.exists():
            raise FileNotFoundError(path)
        _backup(path)

    changed = {
        str(architecture_path.relative_to(ROOT)): _append_once(architecture_path, ARCH_MARKER, ARCH_ENTRY),
        str(troubleshooting_path.relative_to(ROOT)): _append_once(troubleshooting_path, TROUBLE_MARKER, TROUBLE_ENTRY),
    }
    print(json.dumps({"ok": True, "backup_dir": str(BACKUP_DIR), "changed": changed}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
