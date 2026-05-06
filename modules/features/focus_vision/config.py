from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: Any, default: float, *, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, result)


def _as_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, result)


@dataclass(frozen=True, slots=True)
class FocusVisionConfig:
    """Configuration for focus-mode vision monitoring."""

    enabled: bool = False
    dry_run: bool = True
    voice_warnings_enabled: bool = False
    visual_warnings_enabled: bool = True
    observation_interval_seconds: float = 1.0
    startup_grace_seconds: float = 10.0
    absence_warning_after_seconds: float = 25.0
    phone_warning_after_seconds: float = 10.0
    warning_cooldown_seconds: float = 60.0
    max_warnings_per_session: int = 5
    telemetry_path: str = "var/data/focus_vision_sentinel.jsonl"
    latest_observation_force_refresh: bool = True
    pan_tilt_scan_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "FocusVisionConfig":
        payload = dict(raw or {})
        if isinstance(payload.get("focus_vision"), dict):
            payload = dict(payload["focus_vision"])

        return cls(
            enabled=_as_bool(payload.get("enabled"), cls.enabled),
            dry_run=_as_bool(payload.get("dry_run"), cls.dry_run),
            voice_warnings_enabled=_as_bool(payload.get("voice_warnings_enabled"), cls.voice_warnings_enabled),
            visual_warnings_enabled=_as_bool(payload.get("visual_warnings_enabled"), cls.visual_warnings_enabled),
            observation_interval_seconds=_as_float(payload.get("observation_interval_seconds"), cls.observation_interval_seconds, minimum=0.2),
            startup_grace_seconds=_as_float(payload.get("startup_grace_seconds"), cls.startup_grace_seconds),
            absence_warning_after_seconds=_as_float(payload.get("absence_warning_after_seconds"), cls.absence_warning_after_seconds),
            phone_warning_after_seconds=_as_float(payload.get("phone_warning_after_seconds"), cls.phone_warning_after_seconds),
            warning_cooldown_seconds=_as_float(payload.get("warning_cooldown_seconds"), cls.warning_cooldown_seconds),
            max_warnings_per_session=_as_int(payload.get("max_warnings_per_session"), cls.max_warnings_per_session),
            telemetry_path=str(payload.get("telemetry_path") or cls.telemetry_path),
            latest_observation_force_refresh=_as_bool(payload.get("latest_observation_force_refresh"), cls.latest_observation_force_refresh),
            pan_tilt_scan_enabled=_as_bool(payload.get("pan_tilt_scan_enabled"), cls.pan_tilt_scan_enabled),
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "voice_warnings_enabled": self.voice_warnings_enabled,
            "visual_warnings_enabled": self.visual_warnings_enabled,
            "observation_interval_seconds": self.observation_interval_seconds,
            "startup_grace_seconds": self.startup_grace_seconds,
            "absence_warning_after_seconds": self.absence_warning_after_seconds,
            "phone_warning_after_seconds": self.phone_warning_after_seconds,
            "warning_cooldown_seconds": self.warning_cooldown_seconds,
            "max_warnings_per_session": self.max_warnings_per_session,
            "telemetry_path": self.telemetry_path,
            "latest_observation_force_refresh": self.latest_observation_force_refresh,
            "pan_tilt_scan_enabled": self.pan_tilt_scan_enabled,
        }


__all__ = ["FocusVisionConfig"]
