#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"
DEFAULT_TAP_MAX_DURATION_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class AudioBusTapSafetyStatus:
    settings_path: Path
    voice_engine_enabled: bool
    voice_engine_mode: str
    command_first_enabled: bool
    fallback_to_legacy_enabled: bool
    runtime_candidates_enabled: bool
    pre_stt_shadow_enabled: bool
    faster_whisper_audio_bus_tap_enabled: bool
    faster_whisper_audio_bus_tap_max_duration_seconds: float
    safe_to_enable_audio_bus_tap: bool
    reason: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "settings_path": str(self.settings_path),
            "voice_engine.enabled": self.voice_engine_enabled,
            "voice_engine.mode": self.voice_engine_mode,
            "voice_engine.command_first_enabled": self.command_first_enabled,
            "voice_engine.fallback_to_legacy_enabled": self.fallback_to_legacy_enabled,
            "voice_engine.runtime_candidates_enabled": self.runtime_candidates_enabled,
            "voice_engine.pre_stt_shadow_enabled": self.pre_stt_shadow_enabled,
            "voice_engine.faster_whisper_audio_bus_tap_enabled": (
                self.faster_whisper_audio_bus_tap_enabled
            ),
            "voice_engine.faster_whisper_audio_bus_tap_max_duration_seconds": (
                self.faster_whisper_audio_bus_tap_max_duration_seconds
            ),
            "safe_to_enable_audio_bus_tap": self.safe_to_enable_audio_bus_tap,
            "reason": self.reason,
        }


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file does not exist: {path}")

    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)

    if not isinstance(loaded, dict):
        raise ValueError("Settings root must be a JSON object")

    voice_engine = loaded.get("voice_engine")
    if not isinstance(voice_engine, dict):
        raise ValueError("Settings must contain a voice_engine object")

    return loaded


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(settings, file, indent=2, ensure_ascii=False)
        file.write("\n")


def create_backup(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def status_from_settings(
    *,
    settings_path: Path,
    settings: dict[str, Any],
) -> AudioBusTapSafetyStatus:
    voice_engine = settings.get("voice_engine", {})

    enabled = bool(voice_engine.get("enabled", False))
    mode = str(voice_engine.get("mode", "legacy"))
    command_first_enabled = bool(voice_engine.get("command_first_enabled", False))
    fallback_to_legacy_enabled = bool(
        voice_engine.get("fallback_to_legacy_enabled", True)
    )
    runtime_candidates_enabled = bool(
        voice_engine.get("runtime_candidates_enabled", False)
    )
    pre_stt_shadow_enabled = bool(
        voice_engine.get("pre_stt_shadow_enabled", False)
    )
    tap_enabled = bool(
        voice_engine.get("faster_whisper_audio_bus_tap_enabled", False)
    )
    tap_max_duration = _positive_float(
        voice_engine.get(
            "faster_whisper_audio_bus_tap_max_duration_seconds",
            DEFAULT_TAP_MAX_DURATION_SECONDS,
        ),
        fallback=DEFAULT_TAP_MAX_DURATION_SECONDS,
    )

    safe_to_enable = (
        not enabled
        and mode == "legacy"
        and not command_first_enabled
        and fallback_to_legacy_enabled
        and not runtime_candidates_enabled
        and pre_stt_shadow_enabled
    )

    reason = "safe"
    if enabled:
        reason = "voice_engine_enabled_must_remain_false"
    elif mode != "legacy":
        reason = "voice_engine_mode_must_remain_legacy"
    elif command_first_enabled:
        reason = "command_first_enabled_must_remain_false"
    elif not fallback_to_legacy_enabled:
        reason = "fallback_to_legacy_enabled_must_remain_true"
    elif runtime_candidates_enabled:
        reason = "runtime_candidates_enabled_must_remain_false_for_audio_bus_tap"
    elif not pre_stt_shadow_enabled:
        reason = "pre_stt_shadow_enabled_must_be_true_for_audio_bus_tap_validation"

    return AudioBusTapSafetyStatus(
        settings_path=settings_path,
        voice_engine_enabled=enabled,
        voice_engine_mode=mode,
        command_first_enabled=command_first_enabled,
        fallback_to_legacy_enabled=fallback_to_legacy_enabled,
        runtime_candidates_enabled=runtime_candidates_enabled,
        pre_stt_shadow_enabled=pre_stt_shadow_enabled,
        faster_whisper_audio_bus_tap_enabled=tap_enabled,
        faster_whisper_audio_bus_tap_max_duration_seconds=tap_max_duration,
        safe_to_enable_audio_bus_tap=safe_to_enable,
        reason=reason,
    )


def enable_audio_bus_tap(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    current_status = status_from_settings(
        settings_path=settings_path,
        settings=settings,
    )

    if not current_status.safe_to_enable_audio_bus_tap:
        raise RuntimeError(
            "Refusing to enable FasterWhisper audio bus tap: "
            f"{current_status.reason}"
        )

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["faster_whisper_audio_bus_tap_enabled"] = True
    voice_engine["faster_whisper_audio_bus_tap_max_duration_seconds"] = (
        current_status.faster_whisper_audio_bus_tap_max_duration_seconds
    )

    write_settings(settings_path, settings)

    updated_status = status_from_settings(
        settings_path=settings_path,
        settings=settings,
    )

    return {
        "changed": True,
        "action": "enable",
        "backup_path": str(backup_path) if backup_path is not None else None,
        "status": updated_status.to_json_dict(),
    }


def disable_audio_bus_tap(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["faster_whisper_audio_bus_tap_enabled"] = False
    voice_engine.setdefault(
        "faster_whisper_audio_bus_tap_max_duration_seconds",
        DEFAULT_TAP_MAX_DURATION_SECONDS,
    )

    write_settings(settings_path, settings)

    updated_status = status_from_settings(
        settings_path=settings_path,
        settings=settings,
    )

    return {
        "changed": True,
        "action": "disable",
        "backup_path": str(backup_path) if backup_path is not None else None,
        "status": updated_status.to_json_dict(),
    }


def _positive_float(raw_value: Any, *, fallback: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely inspect, enable or disable the Voice Engine v2 "
            "FasterWhisper audio bus shadow tap."
        )
    )
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--status", action="store_true")
    action_group.add_argument("--enable", action="store_true")
    action_group.add_argument("--disable", action="store_true")

    parser.add_argument(
        "--settings-path",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Path to config/settings.json.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a config backup before writing changes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings_path = args.settings_path.resolve()

    try:
        settings = load_settings(settings_path)

        if args.status:
            result: dict[str, Any] = {
                "changed": False,
                "action": "status",
                "status": status_from_settings(
                    settings_path=settings_path,
                    settings=settings,
                ).to_json_dict(),
            }
        elif args.enable:
            result = enable_audio_bus_tap(
                settings_path=settings_path,
                create_config_backup=not args.no_backup,
            )
        elif args.disable:
            result = disable_audio_bus_tap(
                settings_path=settings_path,
                create_config_backup=not args.no_backup,
            )
        else:
            parser.error("No action selected")
            return 2

    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(error).__name__,
                    "message": str(error),
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"ok": True, **result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())