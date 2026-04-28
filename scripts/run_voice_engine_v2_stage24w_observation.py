from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from scripts.validate_voice_engine_v2_vad_timing_command_asr_shadow import (  # noqa: E402
    validate_vad_timing_command_asr_shadow_log,
)


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_BACKUP_PATH = Path("var/data/voice_engine_v2_stage24w_settings_backup.json")
DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")


SAFE_GUARD_VALUES: dict[str, Any] = {
    "enabled": False,
    "mode": "legacy",
    "command_first_enabled": False,
    "fallback_to_legacy_enabled": True,
    "runtime_candidates_enabled": False,
}

OBSERVATION_ENABLE_VALUES: dict[str, Any] = {
    "pre_stt_shadow_enabled": True,
    "faster_whisper_audio_bus_tap_enabled": True,
    "vad_shadow_enabled": True,
    "vad_timing_bridge_enabled": True,
    "command_asr_shadow_bridge_enabled": True,
}

OBSERVATION_RESTORE_VALUES: dict[str, Any] = {
    "pre_stt_shadow_enabled": False,
    "faster_whisper_audio_bus_tap_enabled": False,
    "vad_shadow_enabled": False,
    "vad_timing_bridge_enabled": False,
    "command_asr_shadow_bridge_enabled": False,
}


def enable_stage24w_observation(
    *,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
    overwrite_backup: bool = False,
) -> dict[str, Any]:
    settings = _load_json(settings_path)

    if backup_path.exists() and not overwrite_backup:
        return {
            "accepted": False,
            "action": "enable",
            "settings_path": str(settings_path),
            "backup_path": str(backup_path),
            "issues": ["backup_already_exists"],
        }

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(backup_path, settings)

    updated = _with_voice_engine_values(
        settings,
        {
            **SAFE_GUARD_VALUES,
            **OBSERVATION_ENABLE_VALUES,
        },
    )
    _write_json(settings_path, updated)

    voice_engine = _voice_engine_config(updated)

    return {
        "accepted": True,
        "action": "enable",
        "settings_path": str(settings_path),
        "backup_path": str(backup_path),
        "voice_engine_snapshot": {
            key: voice_engine.get(key)
            for key in (
                *SAFE_GUARD_VALUES.keys(),
                *OBSERVATION_ENABLE_VALUES.keys(),
            )
        },
        "issues": [],
        "next_steps": [
            "Run NEXA manually and collect a few short command turns.",
            "Then run validate.",
            "Always run restore after observation.",
        ],
    }


def restore_stage24w_observation(
    *,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
) -> dict[str, Any]:
    if backup_path.exists():
        settings = _load_json(backup_path)
        backup_used = True
    else:
        settings = _load_json(settings_path)
        backup_used = False

    restored = _with_voice_engine_values(
        settings,
        {
            **SAFE_GUARD_VALUES,
            **OBSERVATION_RESTORE_VALUES,
        },
    )
    _write_json(settings_path, restored)

    voice_engine = _voice_engine_config(restored)

    return {
        "accepted": True,
        "action": "restore",
        "settings_path": str(settings_path),
        "backup_path": str(backup_path),
        "backup_used": backup_used,
        "voice_engine_snapshot": {
            key: voice_engine.get(key)
            for key in (
                *SAFE_GUARD_VALUES.keys(),
                *OBSERVATION_RESTORE_VALUES.keys(),
            )
        },
        "issues": [],
    }


def validate_stage24w_observation(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    require_records: bool = True,
    require_candidate_attached: bool = True,
    require_disabled_only: bool = True,
) -> dict[str, Any]:
    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=require_records,
        require_candidate_attached=require_candidate_attached,
        require_disabled_only=require_disabled_only,
        require_capture_window_hook=True,
    )

    return {
        **result,
        "action": "validate",
        "stage": "24W",
        "expected_runtime_mode": "legacy_observe_only",
    }


def status_stage24w_observation(
    *,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
) -> dict[str, Any]:
    settings = _load_json(settings_path)
    voice_engine = _voice_engine_config(settings)

    return {
        "accepted": True,
        "action": "status",
        "settings_path": str(settings_path),
        "backup_path": str(backup_path),
        "log_path": str(log_path),
        "backup_exists": backup_path.exists(),
        "log_exists": log_path.exists(),
        "voice_engine_snapshot": {
            key: voice_engine.get(key)
            for key in (
                *SAFE_GUARD_VALUES.keys(),
                *OBSERVATION_ENABLE_VALUES.keys(),
            )
        },
        "issues": [],
    }


def _with_voice_engine_values(
    settings: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(settings)
    voice_engine = _voice_engine_config(updated)

    for key, value in values.items():
        voice_engine[key] = value

    updated["voice_engine"] = voice_engine
    return updated


def _voice_engine_config(settings: dict[str, Any]) -> dict[str, Any]:
    raw = settings.get("voice_engine")
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return raw


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Stage 24W controlled Voice Engine v2 command ASR shadow "
            "observation procedure."
        )
    )
    parser.add_argument(
        "action",
        choices=("status", "enable", "validate", "restore"),
        help="Procedure action to run.",
    )
    parser.add_argument(
        "--settings-path",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Path to config/settings.json.",
    )
    parser.add_argument(
        "--backup-path",
        type=Path,
        default=DEFAULT_BACKUP_PATH,
        help="Path to write/read the Stage 24W settings backup.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument(
        "--overwrite-backup",
        action="store_true",
        help="Allow enable to overwrite an existing backup.",
    )
    parser.add_argument(
        "--no-require-records",
        action="store_true",
        help="Validation only: do not require bridge records.",
    )
    parser.add_argument(
        "--no-require-candidate-attached",
        action="store_true",
        help="Validation only: do not require attached command ASR candidate.",
    )
    parser.add_argument(
        "--allow-recognition",
        action="store_true",
        help=(
            "Validation only: allow recognizer_enabled/recognition_attempted. "
            "Do not use for Stage 24W disabled observation."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.action == "status":
        result = status_stage24w_observation(
            settings_path=args.settings_path,
            backup_path=args.backup_path,
            log_path=args.log_path,
        )
    elif args.action == "enable":
        result = enable_stage24w_observation(
            settings_path=args.settings_path,
            backup_path=args.backup_path,
            overwrite_backup=args.overwrite_backup,
        )
    elif args.action == "validate":
        result = validate_stage24w_observation(
            log_path=args.log_path,
            require_records=not args.no_require_records,
            require_candidate_attached=not args.no_require_candidate_attached,
            require_disabled_only=not args.allow_recognition,
        )
    elif args.action == "restore":
        result = restore_stage24w_observation(
            settings_path=args.settings_path,
            backup_path=args.backup_path,
        )
    else:
        raise ValueError(f"Unsupported action: {args.action}")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())