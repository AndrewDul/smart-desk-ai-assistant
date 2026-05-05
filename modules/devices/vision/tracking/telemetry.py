from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class VisionTrackingTelemetryWriter:
    """
    Persist the latest dry-run tracking status as a small JSON snapshot.

    This writer is intentionally not a high-frequency JSONL logger. It stores
    only the latest plan so command-level dry-run decisions can be inspected
    without creating heavy disk I/O in future tracking loops.
    """

    def __init__(self, *, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def write_snapshot(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serializable = _to_json_safe(payload)

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self._path.parent),
            delete=False,
        ) as handle:
            json.dump(serializable, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_name = handle.name

        os.replace(temporary_name, self._path)


def _to_json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _to_json_safe(asdict(value))

    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


__all__ = ["VisionTrackingTelemetryWriter"]
