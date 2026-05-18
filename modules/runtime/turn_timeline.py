from __future__ import annotations

import itertools
import re
import time
from datetime import datetime
from typing import Any

_COUNTER = itertools.count(1)


def create_timeline_turn_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{next(_COUNTER):04d}"


def start_turn_timeline(owner: Any, *, event: str, turn_id: str | None = None, **fields: Any) -> str:
    safe_turn_id = str(turn_id or "").strip() or create_timeline_turn_id()
    started_at = time.perf_counter()
    try:
        owner._turn_timeline = {
            "turn_id": safe_turn_id,
            "started_at": started_at,
        }
    except Exception:
        pass
    log_turn_timeline(owner, event=event, turn_id=safe_turn_id, event_time=started_at, **fields)
    return safe_turn_id


def current_turn_id(owner: Any) -> str:
    timeline = getattr(owner, "_turn_timeline", None)
    if isinstance(timeline, dict):
        return str(timeline.get("turn_id", "") or "").strip()
    return ""


def current_timeline_started_at(owner: Any) -> float:
    timeline = getattr(owner, "_turn_timeline", None)
    if isinstance(timeline, dict):
        try:
            return float(timeline.get("started_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def log_turn_timeline(
    owner: Any,
    *,
    event: str,
    turn_id: str | None = None,
    event_time: float | None = None,
    **fields: Any,
) -> None:
    safe_turn_id = str(turn_id or current_turn_id(owner) or "-").strip() or "-"
    started_at = current_timeline_started_at(owner)
    now = time.perf_counter() if event_time is None else float(event_time)
    if started_at > 0.0:
        fields = {"delta_ms": f"{max(0.0, (now - started_at) * 1000.0):.1f}", **fields}
    line = render_turn_timeline_line(turn_id=safe_turn_id, event=event, **fields)
    print(line)


def render_turn_timeline_line(*, turn_id: str | None, event: str, **fields: Any) -> str:
    parts = [
        "[turn-timeline]",
        f"turn_id={_safe_token(turn_id or '-')}",
        f"event={_safe_token(event or 'unknown')}",
    ]
    for key, value in fields.items():
        if value is None:
            continue
        safe_key = _safe_key(key)
        if not safe_key:
            continue
        parts.append(f"{safe_key}={_format_value(value)}")
    return " ".join(parts)


def _safe_key(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip()).strip("_")


def _safe_token(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return re.sub(r"\s+", "_", text)


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, int):
        return str(value)
    text = str(value or "").strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    if text == "":
        return '""'
    if re.search(r"[\s\"=]", text):
        text = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{text}"'
    return text


__all__ = [
    "create_timeline_turn_id",
    "current_timeline_started_at",
    "current_turn_id",
    "log_turn_timeline",
    "render_turn_timeline_line",
    "start_turn_timeline",
]
