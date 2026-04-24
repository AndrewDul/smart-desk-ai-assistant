from __future__ import annotations

from enum import StrEnum


class VisualState(StrEnum):
    """Canonical state names rendered by the NEXA Visual Shell."""

    IDLE_PARTICLE_CLOUD = "IDLE_PARTICLE_CLOUD"
    LISTENING_CLOUD = "LISTENING_CLOUD"
    THINKING_SWARM = "THINKING_SWARM"
    SPEAKING_PULSE = "SPEAKING_PULSE"
    SCANNING_EYES = "SCANNING_EYES"
    SHOW_SELF_EYES = "SHOW_SELF_EYES"
    FACE_CONTOUR = "FACE_CONTOUR"
    BORED_MICRO_ANIMATION = "BORED_MICRO_ANIMATION"
    TEMPERATURE_GLYPH = "TEMPERATURE_GLYPH"
    BATTERY_GLYPH = "BATTERY_GLYPH"
    DESKTOP_HIDDEN = "DESKTOP_HIDDEN"
    DESKTOP_DOCKED = "DESKTOP_DOCKED"
    DESKTOP_RETURNING = "DESKTOP_RETURNING"
    ERROR_DEGRADED = "ERROR_DEGRADED"

    @classmethod
    def coerce(
        cls,
        value: object,
        *,
        default: "VisualState" | None = None,
    ) -> "VisualState":
        if isinstance(value, cls):
            return value

        normalized = str(value or "").strip().upper()
        if normalized:
            try:
                return cls(normalized)
            except ValueError:
                pass

        if default is not None:
            return default

        raise ValueError(f"Unsupported visual state: {value!r}")