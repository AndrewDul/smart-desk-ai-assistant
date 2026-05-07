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


def _as_string_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        return default

    normalized = tuple(item for item in items if item)
    return normalized or default


def _normalize_reminder_kind(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "absent": "absence",
        "away": "absence",
        "desk_absence": "absence",
        "phone": "phone_distraction",
        "phone_usage": "phone_distraction",
    }
    return aliases.get(normalized, normalized)


def _as_reminder_kind_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_items = _as_string_tuple(value, default)
    normalized: list[str] = []
    for item in raw_items:
        reminder_kind = _normalize_reminder_kind(item)
        if reminder_kind and reminder_kind not in normalized:
            normalized.append(reminder_kind)
    return tuple(normalized) or default


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
    enabled_reminder_kinds: tuple[str, ...] = ("absence", "phone_distraction")
    telemetry_path: str = "var/data/focus_vision_sentinel.jsonl"
    latest_observation_force_refresh: bool = False
    cache_miss_force_refresh_enabled: bool = True
    cache_miss_force_refresh_cooldown_seconds: float = 2.0
    max_observation_age_seconds: float = 8.0
    pan_tilt_scan_enabled: bool = False

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "FocusVisionConfig":
        defaults = cls()
        payload = dict(raw or {})
        if isinstance(payload.get("focus_vision"), dict):
            payload = dict(payload["focus_vision"])

        return cls(
            enabled=_as_bool(payload.get("enabled"), defaults.enabled),
            dry_run=_as_bool(payload.get("dry_run"), defaults.dry_run),
            voice_warnings_enabled=_as_bool(payload.get("voice_warnings_enabled"), defaults.voice_warnings_enabled),
            visual_warnings_enabled=_as_bool(payload.get("visual_warnings_enabled"), defaults.visual_warnings_enabled),
            observation_interval_seconds=_as_float(payload.get("observation_interval_seconds"), defaults.observation_interval_seconds, minimum=0.2),
            startup_grace_seconds=_as_float(payload.get("startup_grace_seconds"), defaults.startup_grace_seconds),
            absence_warning_after_seconds=_as_float(payload.get("absence_warning_after_seconds"), defaults.absence_warning_after_seconds),
            phone_warning_after_seconds=_as_float(payload.get("phone_warning_after_seconds"), defaults.phone_warning_after_seconds),
            warning_cooldown_seconds=_as_float(payload.get("warning_cooldown_seconds"), defaults.warning_cooldown_seconds),
            max_warnings_per_session=_as_int(payload.get("max_warnings_per_session"), defaults.max_warnings_per_session),
            enabled_reminder_kinds=_as_reminder_kind_tuple(payload.get("enabled_reminder_kinds"), defaults.enabled_reminder_kinds),
            telemetry_path=str(payload.get("telemetry_path") or defaults.telemetry_path),
            latest_observation_force_refresh=_as_bool(payload.get("latest_observation_force_refresh"), defaults.latest_observation_force_refresh),
            cache_miss_force_refresh_enabled=_as_bool(payload.get("cache_miss_force_refresh_enabled"), defaults.cache_miss_force_refresh_enabled),
            cache_miss_force_refresh_cooldown_seconds=_as_float(payload.get("cache_miss_force_refresh_cooldown_seconds"), defaults.cache_miss_force_refresh_cooldown_seconds, minimum=0.0),
            max_observation_age_seconds=_as_float(payload.get("max_observation_age_seconds"), defaults.max_observation_age_seconds, minimum=0.0),
            pan_tilt_scan_enabled=_as_bool(payload.get("pan_tilt_scan_enabled"), defaults.pan_tilt_scan_enabled),
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
            "enabled_reminder_kinds": list(self.enabled_reminder_kinds),
            "telemetry_path": self.telemetry_path,
            "latest_observation_force_refresh": self.latest_observation_force_refresh,
            "cache_miss_force_refresh_enabled": self.cache_miss_force_refresh_enabled,
            "cache_miss_force_refresh_cooldown_seconds": self.cache_miss_force_refresh_cooldown_seconds,
            "max_observation_age_seconds": self.max_observation_age_seconds,
            "pan_tilt_scan_enabled": self.pan_tilt_scan_enabled,
        }


__all__ = ["FocusVisionConfig"]
