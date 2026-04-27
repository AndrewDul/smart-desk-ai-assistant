from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_BACKUP_DIR = Path("var/backups/config")
DEFAULT_SHADOW_LOG_PATH = Path("var/data/voice_engine_v2_shadow.jsonl")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def load_settings(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("settings.json must contain a JSON object.")

    return payload


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def voice_engine_config(settings: dict[str, Any]) -> dict[str, Any]:
    config = settings.get("voice_engine")
    if not isinstance(config, dict):
        raise ValueError("Missing required voice_engine config section.")
    return config


def shadow_log_path(settings: dict[str, Any]) -> Path:
    config = settings.get("voice_engine", {})
    if not isinstance(config, dict):
        return DEFAULT_SHADOW_LOG_PATH

    configured_path = _as_text(config.get("shadow_log_path"))
    if configured_path:
        return Path(configured_path)

    return DEFAULT_SHADOW_LOG_PATH


def check_shadow_enable_safety(settings: dict[str, Any]) -> list[str]:
    """Return safety issues that would make shadow-mode enabling unsafe."""

    issues: list[str] = []
    config = voice_engine_config(settings)

    if _as_bool(config.get("enabled")):
        issues.append("voice_engine.enabled must remain false for shadow validation.")

    mode = _as_text(config.get("mode"))
    if mode != "legacy":
        issues.append("voice_engine.mode must remain legacy for shadow validation.")

    if _as_bool(config.get("command_first_enabled")):
        issues.append(
            "voice_engine.command_first_enabled must remain false for shadow validation."
        )

    if config.get("fallback_to_legacy_enabled") is False:
        issues.append(
            "voice_engine.fallback_to_legacy_enabled must not be false for shadow validation."
        )

    return issues


def apply_shadow_mode(settings: dict[str, Any], enabled: bool) -> dict[str, Any]:
    updated = deepcopy(settings)
    config = voice_engine_config(updated)
    config["shadow_mode_enabled"] = bool(enabled)
    return updated


def create_config_backup(settings_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{settings_path.name}.{_timestamp()}.bak"
    shutil.copy2(settings_path, backup_path)
    return backup_path


def archive_existing_shadow_log(log_path: Path) -> Path | None:
    if not log_path.exists():
        return None

    archive_path = log_path.with_name(f"{log_path.stem}.{_timestamp()}{log_path.suffix}.bak")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(log_path), str(archive_path))
    return archive_path


def status_lines(settings_path: Path, settings: dict[str, Any]) -> list[str]:
    config = voice_engine_config(settings)
    safety_issues = check_shadow_enable_safety(settings)

    return [
        "Voice Engine v2 shadow mode status",
        f"settings_path: {settings_path}",
        f"voice_engine.enabled: {bool(config.get('enabled', False))}",
        f"voice_engine.mode: {_as_text(config.get('mode'))}",
        f"voice_engine.command_first_enabled: {bool(config.get('command_first_enabled', False))}",
        f"voice_engine.fallback_to_legacy_enabled: {bool(config.get('fallback_to_legacy_enabled', False))}",
        f"voice_engine.shadow_mode_enabled: {bool(config.get('shadow_mode_enabled', False))}",
        f"voice_engine.shadow_log_path: {shadow_log_path(settings)}",
        f"safe_to_enable_shadow: {not safety_issues}",
        *[f"safety_issue: {issue}" for issue in safety_issues],
    ]


def _print_lines(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely enable or disable Voice Engine v2 shadow telemetry without "
            "making Voice Engine v2 production-primary."
        )
    )
    parser.add_argument(
        "--settings",
        default=str(DEFAULT_SETTINGS_PATH),
        help="Path to config/settings.json.",
    )
    parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Directory for settings.json backups.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current Voice Engine v2 shadow-mode status.",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable voice_engine.shadow_mode_enabled only when safety checks pass.",
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable voice_engine.shadow_mode_enabled.",
    )
    parser.add_argument(
        "--archive-existing-log",
        action="store_true",
        help="Move the existing shadow telemetry JSONL file aside before enabling shadow mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the planned change without writing settings.json.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    action_count = sum(bool(value) for value in (args.status, args.enable, args.disable))
    if action_count != 1:
        parser.error("Choose exactly one action: --status, --enable, or --disable.")

    settings_path = Path(args.settings)
    backup_dir = Path(args.backup_dir)
    settings = load_settings(settings_path)

    if args.status:
        _print_lines(status_lines(settings_path, settings))
        return 0

    if args.enable:
        safety_issues = check_shadow_enable_safety(settings)
        if safety_issues:
            print("Refusing to enable Voice Engine v2 shadow mode.")
            for issue in safety_issues:
                print(f"- {issue}")
            return 2

        updated = apply_shadow_mode(settings, True)

        print("Planned change: voice_engine.shadow_mode_enabled false -> true")
        print("Voice Engine v2 production takeover: false")
        print("Legacy runtime remains primary: true")

        log_archive_path: Path | None = None
        if args.archive_existing_log:
            log_path = shadow_log_path(settings)
            if args.dry_run:
                print(f"Dry run: would archive existing shadow log if present: {log_path}")
            else:
                log_archive_path = archive_existing_shadow_log(log_path)
                if log_archive_path is not None:
                    print(f"Archived existing shadow log: {log_archive_path}")
                else:
                    print(f"No existing shadow log to archive: {log_path}")

        if args.dry_run:
            print("Dry run: settings.json was not changed.")
            return 0

        backup_path = create_config_backup(settings_path, backup_dir)
        write_settings(settings_path, updated)

        print(f"Backup written: {backup_path}")
        print(f"Updated settings: {settings_path}")
        print("Shadow mode enabled for controlled validation.")
        print("Disable it after the run with:")
        print(f"python {Path(__file__).as_posix()} --disable")
        return 0

    if args.disable:
        updated = apply_shadow_mode(settings, False)

        print("Planned change: voice_engine.shadow_mode_enabled -> false")

        if args.dry_run:
            print("Dry run: settings.json was not changed.")
            return 0

        backup_path = create_config_backup(settings_path, backup_dir)
        write_settings(settings_path, updated)

        print(f"Backup written: {backup_path}")
        print(f"Updated settings: {settings_path}")
        print("Shadow mode disabled.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())