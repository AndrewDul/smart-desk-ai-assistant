#!/usr/bin/env python3
"""Check that NeXa can build real microphone + wake-word backends."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    os.environ["NEXA_REQUIRE_REAL_VOICE_INPUT"] = "1"
    os.environ["NEXA_REQUIRE_REAL_WAKE_GATE"] = "1"

    from modules.runtime.builder.core import RuntimeBuilder
    from modules.shared.config.settings import load_settings, reset_settings_cache

    reset_settings_cache()
    settings = load_settings()
    voice_input: dict[str, Any] = dict(settings.get("voice_input", {}) or {})
    print("[CHECK] Voice settings:")
    print(json.dumps({
        "enabled": voice_input.get("enabled"),
        "engine": voice_input.get("engine"),
        "wake_engine": voice_input.get("wake_engine"),
        "wake_model_path": voice_input.get("wake_model_path"),
        "wake_prefer_dedicated_gate": voice_input.get("wake_prefer_dedicated_gate"),
        "device_index": voice_input.get("device_index"),
        "device_name_contains": voice_input.get("device_name_contains"),
        "sample_rate": voice_input.get("sample_rate"),
    }, indent=2, sort_keys=True))

    try:
        runtime = RuntimeBuilder(settings=settings).build()
    except Exception as error:
        print(f"[CHECK FAIL] Real voice runtime could not be built: {type(error).__name__}: {error}")
        return 2

    statuses = {
        name: status.to_snapshot()
        for name, status in dict(runtime.backend_statuses).items()
        if name in {"voice_input", "wake_gate", "voice_output"}
    }
    print("[CHECK] Backend statuses:")
    print(json.dumps(statuses, indent=2, sort_keys=True))

    for obj in (getattr(runtime, "voice_input", None), getattr(runtime, "wake_gate", None), getattr(runtime, "voice_output", None)):
        close = getattr(obj, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    print("[CHECK OK] Real voice input and wake gate are available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
