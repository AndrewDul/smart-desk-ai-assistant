from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FocusVisionTelemetryWriter:
    """Append focus vision decisions and reminder candidates as JSONL telemetry."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = ["FocusVisionTelemetryWriter"]
