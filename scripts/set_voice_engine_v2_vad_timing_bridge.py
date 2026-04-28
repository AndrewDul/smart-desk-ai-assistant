#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.json"
DEFAULT_LOG_PATH = "var/data/voice_engine_v2_vad_timing_bridge.jsonl"


@dataclass(frozen=True, slots=True)
class VadTimingBridgeSafetyStatus:
    settings_path: Path
    voice_engine_enabled: bool
    voice_engine_mode: str
    command_first_enabled: bool
    fallback_to_legacy_enabled: bool
    runtime_candidates_enabled: bool
    pre_stt_shadow_enabled: bool
    faster_whisper_audio_bus_tap_enabled: bool
    vad_shadow_enabled: bool
    vad_timing_bridge_enabled: bool
    vad_timing_bridge_log_path: str
    safe_to_enable_vad_timing_bridge: bool
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
            "voice_engine.vad_shadow_enabled": self.vad_shadow_enabled,
            "voice_engine.vad_timing_bridge_enabled": (
                self.vad_timing_bridge_enabled
            ),
            "voice_engine.vad_timing_bridge_log_path": (
                self.vad_timing_bridge_log_path
            ),
            "safe_to_enable_vad_timing_bridge": (
                self.safe_to_enable_vad_timing_bridge
            ),
            "reason": self.reason,
        }


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file does not exist: {path}")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Settings root must be a JSON object")

    voice_engine = loaded.get("voice_engine")
    if not isinstance(voice_engine, dict):
        raise ValueError("Settings must contain a voice_engine object")

    return loaded


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def create_backup(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def status_from_settings(
    *,
    settings_path: Path,
    settings: dict[str, Any],
) -> VadTimingBridgeSafetyStatus:
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
    pre_stt_shadow_enabled = bool(voice_engine.get("pre_stt_shadow_enabled", False))
    audio_bus_tap_enabled = bool(
        voice_engine.get("faster_whisper_audio_bus_tap_enabled", False)
    )
    vad_shadow_enabled = bool(voice_engine.get("vad_shadow_enabled", False))
    vad_timing_bridge_enabled = bool(
        voice_engine.get("vad_timing_bridge_enabled", False)
    )
    log_path = str(
        voice_engine.get("vad_timing_bridge_log_path", DEFAULT_LOG_PATH)
        or DEFAULT_LOG_PATH
    )

    safe_to_enable = (
        not enabled
        and mode == "legacy"
        and not command_first_enabled
        and fallback_to_legacy_enabled
        and not runtime_candidates_enabled
        and pre_stt_shadow_enabled
        and audio_bus_tap_enabled
        and vad_shadow_enabled
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
        reason = "runtime_candidates_enabled_must_remain_false_for_vad_timing_bridge"
    elif not pre_stt_shadow_enabled:
        reason = "pre_stt_shadow_enabled_must_be_true_for_vad_timing_bridge"
    elif not audio_bus_tap_enabled:
        reason = "audio_bus_tap_enabled_must_be_true_for_vad_timing_bridge"
    elif not vad_shadow_enabled:
        reason = "vad_shadow_enabled_must_be_true_for_vad_timing_bridge"

    return VadTimingBridgeSafetyStatus(
        settings_path=settings_path,
        voice_engine_enabled=enabled,
        voice_engine_mode=mode,
        command_first_enabled=command_first_enabled,
        fallback_to_legacy_enabled=fallback_to_legacy_enabled,
        runtime_candidates_enabled=runtime_candidates_enabled,
        pre_stt_shadow_enabled=pre_stt_shadow_enabled,
        faster_whisper_audio_bus_tap_enabled=audio_bus_tap_enabled,
        vad_shadow_enabled=vad_shadow_enabled,
        vad_timing_bridge_enabled=vad_timing_bridge_enabled,
        vad_timing_bridge_log_path=log_path,
        safe_to_enable_vad_timing_bridge=safe_to_enable,
        reason=reason,
    )


def enable_vad_timing_bridge(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    current_status = status_from_settings(
        settings_path=settings_path,
        settings=settings,
    )

    if not current_status.safe_to_enable_vad_timing_bridge:
        raise RuntimeError(
            f"Refusing to enable VAD timing bridge: {current_status.reason}"
        )

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["vad_timing_bridge_enabled"] = True
    voice_engine["vad_timing_bridge_log_path"] = (
        current_status.vad_timing_bridge_log_path
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


def disable_vad_timing_bridge(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["vad_timing_bridge_enabled"] = False
    voice_engine.setdefault("vad_timing_bridge_log_path", DEFAULT_LOG_PATH)

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enable or disable the Voice Engine v2 VAD timing bridge."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument(
        "--settings-path",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a settings backup before writing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.settings_path)

    if args.status:
        status = status_from_settings(
            settings_path=args.settings_path,
            settings=settings,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "changed": False,
                    "action": "status",
                    "status": status.to_json_dict(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    try:
        if args.enable:
            result = enable_vad_timing_bridge(
                settings_path=args.settings_path,
                create_config_backup=not args.no_backup,
            )
        else:
            result = disable_vad_timing_bridge(
                settings_path=args.settings_path,
                create_config_backup=not args.no_backup,
            )
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "changed": False,
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                **result,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())