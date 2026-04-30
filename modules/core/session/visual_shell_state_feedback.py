from __future__ import annotations

from typing import Any

from modules.presentation.visual_shell.contracts import VisualEventName
from modules.shared.logging.logger import append_log


def _visual_shell_lane(assistant: Any) -> Any | None:
    fast_lane = getattr(assistant, "fast_command_lane", None)
    if fast_lane is None:
        return None

    return getattr(fast_lane, "visual_shell_lane", None)


def notify_visual_shell_voice_event(
    assistant: Any,
    event_name: VisualEventName,
    *,
    source: str,
    detail: str = "",
    payload: dict[str, object] | None = None,
) -> bool:
    """Notify Visual Shell about a voice-session state transition.

    This is intentionally best-effort. Visual Shell must improve UX, but it must
    never block or break the voice runtime when the renderer is unavailable.
    """

    lane = _visual_shell_lane(assistant)
    if lane is None:
        append_log(
            "Visual Shell voice cue skipped: lane unavailable "
            f"event={event_name.value} source={source}"
        )
        return False

    dispatch_event = getattr(lane, "dispatch_event", None)
    if not callable(dispatch_event):
        append_log(
            "Visual Shell voice cue skipped: dispatch_event unavailable "
            f"event={event_name.value} source={source}"
        )
        return False

    safe_payload = dict(payload or {})
    if detail:
        safe_payload.setdefault("detail", detail)

    handled = bool(
        dispatch_event(
            event_name=event_name,
            payload=safe_payload,
            source=source,
        )
    )

    append_log(
        "Visual Shell voice cue: "
        f"event={event_name.value} source={source} "
        f"detail={detail or '-'} result={'ok' if handled else 'failed'}"
    )
    return handled


def notify_visual_shell_idle(
    assistant: Any,
    *,
    source: str,
    detail: str = "",
) -> bool:
    """Return Visual Shell to idle after command windows close."""

    lane = _visual_shell_lane(assistant)
    if lane is None:
        append_log(
            "Visual Shell idle cue skipped: lane unavailable "
            f"source={source} detail={detail or '-'}"
        )
        return False

    dispatch_return_to_idle = getattr(lane, "dispatch_return_to_idle", None)
    if not callable(dispatch_return_to_idle):
        append_log(
            "Visual Shell idle cue skipped: dispatch_return_to_idle unavailable "
            f"source={source} detail={detail or '-'}"
        )
        return False

    handled = bool(dispatch_return_to_idle(source=source))

    append_log(
        "Visual Shell idle cue: "
        f"source={source} detail={detail or '-'} "
        f"result={'ok' if handled else 'failed'}"
    )
    return handled
