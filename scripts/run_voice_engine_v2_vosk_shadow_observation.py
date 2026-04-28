#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_voice_engine_v2_vad_timing_vosk_live_shadow import (  # noqa: E402
    DEFAULT_LOG_PATH,
    validate_vad_timing_vosk_live_shadow_log,
)


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_BACKUP_DIR = Path("var/backups/config")

OBSERVATION_FLAGS: dict[str, bool] = {
    "pre_stt_shadow_enabled": True,
    "faster_whisper_audio_bus_tap_enabled": True,
    "vad_shadow_enabled": True,
    "vad_timing_bridge_enabled": True,
    "command_asr_shadow_bridge_enabled": True,
    "vosk_live_shadow_contract_enabled": True,
    "vosk_shadow_invocation_plan_enabled": True,
    "vosk_shadow_pcm_reference_enabled": True,
    "vosk_shadow_asr_result_enabled": True,
}
RESTORED_OBSERVATION_FLAGS: dict[str, bool] = {
    key: False for key in OBSERVATION_FLAGS
}

BASELINE_SAFE_VALUES: dict[str, object] = {
    "enabled": False,
    "mode": "legacy",
    "command_first_enabled": False,
    "fallback_to_legacy_enabled": True,
    "runtime_candidates_enabled": False,
}


class ObservationConfigError(RuntimeError):
    """Raised when the observation procedure would violate runtime safety."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("settings.json root must be a JSON object")

    if not isinstance(payload.get("voice_engine"), dict):
        raise ValueError("settings.json must contain a voice_engine object")

    return payload


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def voice_engine_config(settings: dict[str, Any]) -> dict[str, Any]:
    config = settings.get("voice_engine")
    if not isinstance(config, dict):
        raise ValueError("settings.json must contain a voice_engine object")
    return config


def create_config_backup(settings_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{settings_path.name}.{utc_timestamp()}.bak"
    shutil.copy2(settings_path, backup_path)
    return backup_path


def archive_existing_log(log_path: Path) -> Path | None:
    if not log_path.exists():
        return None

    archive_path = log_path.with_name(
        f"{log_path.stem}.{utc_timestamp()}{log_path.suffix}.bak"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(log_path), str(archive_path))
    return archive_path


def baseline_safety_issues(settings: dict[str, Any]) -> list[str]:
    config = voice_engine_config(settings)
    issues: list[str] = []

    if bool(config.get("enabled", False)):
        issues.append("voice_engine.enabled_must_remain_false")

    if str(config.get("mode", "")).strip() != "legacy":
        issues.append("voice_engine.mode_must_remain_legacy")

    if bool(config.get("command_first_enabled", False)):
        issues.append("voice_engine.command_first_enabled_must_remain_false")

    if config.get("fallback_to_legacy_enabled") is not True:
        issues.append("voice_engine.fallback_to_legacy_enabled_must_remain_true")

    if bool(config.get("runtime_candidates_enabled", False)):
        issues.append("voice_engine.runtime_candidates_enabled_must_remain_false")

    return issues


def apply_voice_engine_flags(
    settings: dict[str, Any],
    flags: dict[str, bool],
) -> dict[str, Any]:
    updated = deepcopy(settings)
    config = voice_engine_config(updated)

    for key, value in flags.items():
        config[key] = value

    return updated


def observation_flag_status(settings: dict[str, Any]) -> dict[str, bool]:
    config = voice_engine_config(settings)
    return {
        key: bool(config.get(key, False))
        for key in OBSERVATION_FLAGS
    }


def baseline_status(settings: dict[str, Any]) -> dict[str, object]:
    config = voice_engine_config(settings)
    return {
        key: config.get(key)
        for key in BASELINE_SAFE_VALUES
    }


def build_status(settings_path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    issues = baseline_safety_issues(settings)
    flags = observation_flag_status(settings)
    return {
        "settings_path": str(settings_path),
        "baseline_safe": not issues,
        "baseline_safety_issues": issues,
        "baseline_status": baseline_status(settings),
        "observation_flags": flags,
        "all_observation_flags_enabled": all(flags.values()),
        "all_observation_flags_restored": not any(flags.values()),
        "runtime_takeover_enabled": bool(
            voice_engine_config(settings).get("enabled", False)
        ),
        "command_first_enabled": bool(
            voice_engine_config(settings).get("command_first_enabled", False)
        ),
        "legacy_runtime_primary": (
            not bool(voice_engine_config(settings).get("enabled", False))
            and str(voice_engine_config(settings).get("mode", "")).strip() == "legacy"
        ),
    }


def prepare_observation(
    *,
    settings_path: Path,
    backup_dir: Path,
    log_path: Path,
    archive_log: bool,
    dry_run: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    issues = baseline_safety_issues(settings)
    if issues:
        raise ObservationConfigError(
            "Refusing to prepare Vosk shadow observation: " + ",".join(issues)
        )

    updated = apply_voice_engine_flags(settings, OBSERVATION_FLAGS)
    result: dict[str, Any] = {
        "accepted": True,
        "action": "prepare",
        "dry_run": dry_run,
        "settings_path": str(settings_path),
        "backup_path": None,
        "archived_log_path": None,
        "log_path": str(log_path),
        "applied_flags": OBSERVATION_FLAGS,
        "safety": build_status(settings_path, updated),
        "runtime_integration_enabled": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "independent_microphone_stream_started": False,
    }

    if dry_run:
        return result

    if archive_log:
        archived_log_path = archive_existing_log(log_path)
        result["archived_log_path"] = (
            str(archived_log_path) if archived_log_path is not None else None
        )

    backup_path = create_config_backup(settings_path, backup_dir)
    write_settings(settings_path, updated)
    result["backup_path"] = str(backup_path)
    return result


def restore_observation(
    *,
    settings_path: Path,
    backup_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    updated = apply_voice_engine_flags(settings, RESTORED_OBSERVATION_FLAGS)

    config = voice_engine_config(updated)
    config["enabled"] = False
    config["mode"] = "legacy"
    config["command_first_enabled"] = False
    config["fallback_to_legacy_enabled"] = True
    config["runtime_candidates_enabled"] = False

    result: dict[str, Any] = {
        "accepted": True,
        "action": "restore",
        "dry_run": dry_run,
        "settings_path": str(settings_path),
        "backup_path": None,
        "restored_flags": RESTORED_OBSERVATION_FLAGS,
        "safety": build_status(settings_path, updated),
    }

    if dry_run:
        return result

    backup_path = create_config_backup(settings_path, backup_dir)
    write_settings(settings_path, updated)
    result["backup_path"] = str(backup_path)
    return result


def validate_observation_log(
    *,
    log_path: Path,
    require_contract_attached: bool,
) -> dict[str, Any]:
    result = validate_vad_timing_vosk_live_shadow_log(
        log_path=log_path,
        require_records=True,
        require_contract_attached=require_contract_attached,
        require_enabled_shape_only=True,
        require_capture_window_hook=True,
    )
    return {
        "accepted": bool(result.get("accepted", False)),
        "action": "validate",
        "log_path": str(log_path),
        "telemetry": result,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare, validate, or restore the observe-only Voice Engine v2 "
            "Vosk shadow observation procedure."
        )
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--validate", action="store_true")
    action.add_argument("--restore", action="store_true")
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Path to config/settings.json.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory for settings backups.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to VAD timing bridge JSONL telemetry.",
    )
    parser.add_argument(
        "--archive-existing-log",
        action="store_true",
        help="Archive the existing VAD timing bridge log before preparing.",
    )
    parser.add_argument(
        "--require-contract-attached",
        action="store_true",
        help="Require at least one metadata.vosk_live_shadow record during validation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned prepare/restore result without writing settings.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.status:
            settings = load_settings(args.settings)
            result = {
                "accepted": not baseline_safety_issues(settings),
                "action": "status",
                "safety": build_status(args.settings, settings),
            }
        elif args.prepare:
            result = prepare_observation(
                settings_path=args.settings,
                backup_dir=args.backup_dir,
                log_path=args.log_path,
                archive_log=args.archive_existing_log,
                dry_run=args.dry_run,
            )
        elif args.validate:
            result = validate_observation_log(
                log_path=args.log_path,
                require_contract_attached=args.require_contract_attached,
            )
        elif args.restore:
            result = restore_observation(
                settings_path=args.settings,
                backup_dir=args.backup_dir,
                dry_run=args.dry_run,
            )
        else:
            raise AssertionError("unreachable observation action")
    except (ObservationConfigError, OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "accepted": False,
            "error": str(error),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())