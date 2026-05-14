from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.presentation.visual_shell.service.system_metrics import (  # noqa: E402
    VisualShellSystemMetricsProvider,
)

provider = VisualShellSystemMetricsProvider()
reading = provider.read_battery()

if reading is None:
    print("battery_unavailable")
    raise SystemExit(2)

print("battery_available")
print(f"percent={reading.percent}")
print(f"raw_percent={reading.raw_percent}")
print(f"voltage_v={reading.voltage_v}")
print(f"source={reading.source}")
