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

DEFAULT_RUNTIME_CANDIDATE_ALLOWLIST = (
    "assistant.identity",
    "system.current_time",
)

SUPPORTED_RUNTIME_CANDIDATE_INTENTS = frozenset(DEFAULT_RUNTIME_CANDIDATE_ALLOWLIST)


@dataclass(frozen=True, slots=True)
class RuntimeCandidateSafetyStatus:
    settings_path: Path
    voice_engine_enabled: bool
    voice_engine_mode: str
    command_first_enabled: bool
    fallback_to_legacy_enabled: bool
    runtime_candidates_enabled: bool
    runtime_candidate_intent_allowlist: tuple[str, ...]
    safe_to_enable_runtime_candidates: bool
    reason: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "settings_path": str(self.settings_path),
            "voice_engine.enabled": self.voice_engine_enabled,
            "voice_engine.mode": self.voice_engine_mode,
            "voice_engine.command_first_enabled": self.command_first_enabled,
            "voice_engine.fallback_to_legacy_enabled": self.fallback_to_legacy_enabled,
            "voice_engine.runtime_candidates_enabled": (
                self.runtime_candidates_enabled
            ),
            "voice_engine.runtime_candidate_intent_allowlist": list(
                self.runtime_candidate_intent_allowlist
            ),
            "safe_to_enable_runtime_candidates": (
                self.safe_to_enable_runtime_candidates
            ),
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


def normalize_allowlist(raw_value: Any) -> tuple[str, ...]:
    if isinstance(raw_value, str):
        raw_items = raw_value.split(",")
    elif isinstance(raw_value, list | tuple | set | frozenset):
        raw_items = list(raw_value)
    else:
        raw_items = []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)

    return tuple(normalized)


def status_from_settings(
    *,
    settings_path: Path,
    settings: dict[str, Any],
) -> RuntimeCandidateSafetyStatus:
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
    allowlist = normalize_allowlist(
        voice_engine.get(
            "runtime_candidate_intent_allowlist",
            DEFAULT_RUNTIME_CANDIDATE_ALLOWLIST,
        )
    )

    safe_to_enable = (
        not enabled
        and mode == "legacy"
        and not command_first_enabled
        and fallback_to_legacy_enabled
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

    return RuntimeCandidateSafetyStatus(
        settings_path=settings_path,
        voice_engine_enabled=enabled,
        voice_engine_mode=mode,
        command_first_enabled=command_first_enabled,
        fallback_to_legacy_enabled=fallback_to_legacy_enabled,
        runtime_candidates_enabled=runtime_candidates_enabled,
        runtime_candidate_intent_allowlist=allowlist,
        safe_to_enable_runtime_candidates=safe_to_enable,
        reason=reason,
    )


def validate_runtime_candidate_allowlist(allowlist: tuple[str, ...]) -> None:
    unsupported = sorted(set(allowlist) - SUPPORTED_RUNTIME_CANDIDATE_INTENTS)
    if unsupported:
        raise ValueError(
            "Unsupported Stage 20A runtime candidate intents: "
            + ", ".join(unsupported)
            + ". Supported intents: "
            + ", ".join(sorted(SUPPORTED_RUNTIME_CANDIDATE_INTENTS))
        )


def enable_runtime_candidates(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    current_status = status_from_settings(
        settings_path=settings_path,
        settings=settings,
    )

    if not current_status.safe_to_enable_runtime_candidates:
        raise RuntimeError(
            "Refusing to enable runtime candidates: "
            f"{current_status.reason}"
        )

    allowlist = DEFAULT_RUNTIME_CANDIDATE_ALLOWLIST
    validate_runtime_candidate_allowlist(allowlist)

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["runtime_candidates_enabled"] = True
    voice_engine["runtime_candidate_intent_allowlist"] = list(allowlist)

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


def disable_runtime_candidates(
    *,
    settings_path: Path,
    create_config_backup: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)

    backup_path: Path | None = None
    if create_config_backup:
        backup_path = create_backup(settings_path)

    voice_engine = settings["voice_engine"]
    voice_engine["runtime_candidates_enabled"] = False
    voice_engine.setdefault(
        "runtime_candidate_intent_allowlist",
        list(DEFAULT_RUNTIME_CANDIDATE_ALLOWLIST),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely inspect, enable or disable Voice Engine v2 runtime candidates."
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
            result = enable_runtime_candidates(
                settings_path=settings_path,
                create_config_backup=not args.no_backup,
            )
        elif args.disable:
            result = disable_runtime_candidates(
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