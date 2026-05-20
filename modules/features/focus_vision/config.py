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
    phone_warning_after_seconds: float = 20.0
    away_soft_reminder_after_seconds: float = 30.0
    warning_cooldown_seconds: float = 120.0
    max_warnings_per_session: int = 5
    enabled_reminder_kinds: tuple[str, ...] = ("absence", "phone_distraction", "away_soft")
    telemetry_path: str = "var/data/focus_vision_sentinel.jsonl"
    latest_observation_force_refresh: bool = False
    cache_miss_force_refresh_enabled: bool = True
    cache_miss_force_refresh_cooldown_seconds: float = 2.0
    max_observation_age_seconds: float = 8.0
    reactive_max_observation_age_seconds: float = 2.0
    observation_refresh_timeout_seconds: float = 1.2
    pan_tilt_scan_enabled: bool = False
    absence_pending_scan_after_seconds: float = 2.0
    active_monitoring_enabled: bool = True
    continuous_tracking_enabled: bool = True
    tracking_interval_seconds: float = 0.10
    tracking_max_observation_age_seconds: float = 1.5
    tracking_pan_gain_degrees: float = 16.0
    tracking_tilt_gain_degrees: float = 22.0
    tracking_max_pan_step_degrees: float = 1.0
    tracking_max_tilt_step_degrees: float = 1.2
    tracking_min_move_degrees: float = 0.12
    tracking_hold_zone_x: float = 0.035
    tracking_hold_zone_y: float = 0.025
    tracking_invert_tilt: bool = False
    tracking_max_step_degrees: float = 1.2
    periodic_scan_enabled: bool = False
    periodic_scan_interval_seconds: float = 35.0
    away_recheck_scan_after_seconds: float = 2.0
    phone_gap_tolerance_seconds: float = 5.0
    scan_pan_degrees: float = 12.0
    scan_point_settle_seconds: float = 0.35
    scan_observation_refresh_timeout_seconds: float = 0.45
    away_scan_max_duration_seconds: float = 4.0
    face_lost_debounce_seconds: float = 0.5
    face_stale_hold_max_seconds: float = 1.2
    focus_scan_once_per_absence_episode: bool = True
    focus_tracking_command_coalesce_seconds: float = 0.12
    focus_tracking_command_change_threshold_degrees: float = 0.25

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
            away_soft_reminder_after_seconds=_as_float(payload.get("away_soft_reminder_after_seconds"), defaults.away_soft_reminder_after_seconds, minimum=10.0),
            warning_cooldown_seconds=_as_float(payload.get("warning_cooldown_seconds"), defaults.warning_cooldown_seconds),
            max_warnings_per_session=_as_int(payload.get("max_warnings_per_session"), defaults.max_warnings_per_session),
            enabled_reminder_kinds=_as_reminder_kind_tuple(payload.get("enabled_reminder_kinds"), defaults.enabled_reminder_kinds),
            telemetry_path=str(payload.get("telemetry_path") or defaults.telemetry_path),
            latest_observation_force_refresh=_as_bool(payload.get("latest_observation_force_refresh"), defaults.latest_observation_force_refresh),
            cache_miss_force_refresh_enabled=_as_bool(payload.get("cache_miss_force_refresh_enabled"), defaults.cache_miss_force_refresh_enabled),
            cache_miss_force_refresh_cooldown_seconds=_as_float(payload.get("cache_miss_force_refresh_cooldown_seconds"), defaults.cache_miss_force_refresh_cooldown_seconds, minimum=0.0),
            max_observation_age_seconds=_as_float(payload.get("max_observation_age_seconds"), defaults.max_observation_age_seconds, minimum=0.0),
            reactive_max_observation_age_seconds=_as_float(payload.get("reactive_max_observation_age_seconds"), defaults.reactive_max_observation_age_seconds, minimum=0.0),
            observation_refresh_timeout_seconds=_as_float(payload.get("observation_refresh_timeout_seconds"), defaults.observation_refresh_timeout_seconds, minimum=0.05),
            pan_tilt_scan_enabled=_as_bool(payload.get("pan_tilt_scan_enabled"), defaults.pan_tilt_scan_enabled),
            absence_pending_scan_after_seconds=_as_float(payload.get("absence_pending_scan_after_seconds"), defaults.absence_pending_scan_after_seconds, minimum=1.0),
            active_monitoring_enabled=_as_bool(payload.get("active_monitoring_enabled"), defaults.active_monitoring_enabled),
            continuous_tracking_enabled=_as_bool(payload.get("continuous_tracking_enabled"), defaults.continuous_tracking_enabled),
            tracking_interval_seconds=_as_float(payload.get("tracking_interval_seconds"), defaults.tracking_interval_seconds, minimum=0.05),
            tracking_max_observation_age_seconds=_as_float(payload.get("tracking_max_observation_age_seconds"), defaults.tracking_max_observation_age_seconds, minimum=0.0),
            tracking_pan_gain_degrees=_as_float(payload.get("tracking_pan_gain_degrees"), defaults.tracking_pan_gain_degrees, minimum=0.0),
            tracking_tilt_gain_degrees=_as_float(payload.get("tracking_tilt_gain_degrees"), defaults.tracking_tilt_gain_degrees, minimum=0.0),
            tracking_max_pan_step_degrees=_as_float(payload.get("tracking_max_pan_step_degrees"), defaults.tracking_max_pan_step_degrees, minimum=0.1),
            tracking_max_tilt_step_degrees=_as_float(payload.get("tracking_max_tilt_step_degrees"), defaults.tracking_max_tilt_step_degrees, minimum=0.1),
            tracking_min_move_degrees=_as_float(payload.get("tracking_min_move_degrees"), defaults.tracking_min_move_degrees, minimum=0.0),
            tracking_max_step_degrees=_as_float(payload.get("tracking_max_step_degrees"), defaults.tracking_max_step_degrees, minimum=0.1),
            tracking_hold_zone_x=_as_float(payload.get("tracking_hold_zone_x"), defaults.tracking_hold_zone_x, minimum=0.0),
            tracking_hold_zone_y=_as_float(payload.get("tracking_hold_zone_y"), defaults.tracking_hold_zone_y, minimum=0.0),
            tracking_invert_tilt=_as_bool(payload.get("tracking_invert_tilt"), defaults.tracking_invert_tilt),
            periodic_scan_enabled=_as_bool(payload.get("periodic_scan_enabled"), defaults.periodic_scan_enabled),
            periodic_scan_interval_seconds=_as_float(payload.get("periodic_scan_interval_seconds"), defaults.periodic_scan_interval_seconds, minimum=5.0),
            away_recheck_scan_after_seconds=_as_float(payload.get("away_recheck_scan_after_seconds"), defaults.away_recheck_scan_after_seconds, minimum=1.0),
            phone_gap_tolerance_seconds=_as_float(payload.get("phone_gap_tolerance_seconds"), defaults.phone_gap_tolerance_seconds, minimum=0.0),
            scan_pan_degrees=_as_float(payload.get("scan_pan_degrees"), defaults.scan_pan_degrees, minimum=0.0),
            scan_point_settle_seconds=_as_float(payload.get("scan_point_settle_seconds"), defaults.scan_point_settle_seconds, minimum=0.0),
            scan_observation_refresh_timeout_seconds=_as_float(payload.get("scan_observation_refresh_timeout_seconds"), defaults.scan_observation_refresh_timeout_seconds, minimum=0.05),
            away_scan_max_duration_seconds=_as_float(payload.get("away_scan_max_duration_seconds"), defaults.away_scan_max_duration_seconds, minimum=1.0),
            face_lost_debounce_seconds=_as_float(payload.get("face_lost_debounce_seconds"), defaults.face_lost_debounce_seconds, minimum=0.0),
            face_stale_hold_max_seconds=_as_float(payload.get("face_stale_hold_max_seconds"), defaults.face_stale_hold_max_seconds, minimum=0.0),
            focus_scan_once_per_absence_episode=_as_bool(payload.get("focus_scan_once_per_absence_episode"), defaults.focus_scan_once_per_absence_episode),
            focus_tracking_command_coalesce_seconds=_as_float(payload.get("focus_tracking_command_coalesce_seconds"), defaults.focus_tracking_command_coalesce_seconds, minimum=0.0),
            focus_tracking_command_change_threshold_degrees=_as_float(payload.get("focus_tracking_command_change_threshold_degrees"), defaults.focus_tracking_command_change_threshold_degrees, minimum=0.0),
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
            "away_soft_reminder_after_seconds": self.away_soft_reminder_after_seconds,
            "warning_cooldown_seconds": self.warning_cooldown_seconds,
            "max_warnings_per_session": self.max_warnings_per_session,
            "enabled_reminder_kinds": list(self.enabled_reminder_kinds),
            "telemetry_path": self.telemetry_path,
            "latest_observation_force_refresh": self.latest_observation_force_refresh,
            "cache_miss_force_refresh_enabled": self.cache_miss_force_refresh_enabled,
            "cache_miss_force_refresh_cooldown_seconds": self.cache_miss_force_refresh_cooldown_seconds,
            "max_observation_age_seconds": self.max_observation_age_seconds,
            "reactive_max_observation_age_seconds": self.reactive_max_observation_age_seconds,
            "observation_refresh_timeout_seconds": self.observation_refresh_timeout_seconds,
            "pan_tilt_scan_enabled": self.pan_tilt_scan_enabled,
            "absence_pending_scan_after_seconds": self.absence_pending_scan_after_seconds,
            "active_monitoring_enabled": self.active_monitoring_enabled,
            "continuous_tracking_enabled": self.continuous_tracking_enabled,
            "tracking_interval_seconds": self.tracking_interval_seconds,
            "tracking_max_observation_age_seconds": self.tracking_max_observation_age_seconds,
            "tracking_pan_gain_degrees": self.tracking_pan_gain_degrees,
            "tracking_tilt_gain_degrees": self.tracking_tilt_gain_degrees,
            "tracking_max_pan_step_degrees": self.tracking_max_pan_step_degrees,
            "tracking_max_tilt_step_degrees": self.tracking_max_tilt_step_degrees,
            "tracking_min_move_degrees": self.tracking_min_move_degrees,
            "tracking_max_step_degrees": self.tracking_max_step_degrees,
            "tracking_hold_zone_x": self.tracking_hold_zone_x,
            "tracking_hold_zone_y": self.tracking_hold_zone_y,
            "tracking_invert_tilt": self.tracking_invert_tilt,
            "periodic_scan_enabled": self.periodic_scan_enabled,
            "periodic_scan_interval_seconds": self.periodic_scan_interval_seconds,
            "away_recheck_scan_after_seconds": self.away_recheck_scan_after_seconds,
            "phone_gap_tolerance_seconds": self.phone_gap_tolerance_seconds,
            "scan_pan_degrees": self.scan_pan_degrees,
            "scan_point_settle_seconds": self.scan_point_settle_seconds,
            "scan_observation_refresh_timeout_seconds": self.scan_observation_refresh_timeout_seconds,
            "away_scan_max_duration_seconds": self.away_scan_max_duration_seconds,
            "face_lost_debounce_seconds": self.face_lost_debounce_seconds,
            "face_stale_hold_max_seconds": self.face_stale_hold_max_seconds,
            "focus_scan_once_per_absence_episode": self.focus_scan_once_per_absence_episode,
            "focus_tracking_command_coalesce_seconds": self.focus_tracking_command_coalesce_seconds,
            "focus_tracking_command_change_threshold_degrees": self.focus_tracking_command_change_threshold_degrees,
        }


__all__ = ["FocusVisionConfig"]
