#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_voice_engine_v2_capture_window_readiness import (  # noqa: E402
    DEFAULT_LOG_PATH,
)
from scripts.validate_voice_engine_v2_controlled_recognition_readiness import (  # noqa: E402
    validate_controlled_recognition_readiness,
)


DEFAULT_SETTINGS_PATH = Path("config/settings.json")

SAFE_BASELINE_FIELDS: dict[str, Any] = {
    "enabled": False,
    "mode": "legacy",
    "command_first_enabled": False,
    "fallback_to_legacy_enabled": True,
    "runtime_candidates_enabled": False,
}

OBSERVATION_FLAGS: tuple[str, ...] = (
    "pre_stt_shadow_enabled",
    "faster_whisper_audio_bus_tap_enabled",
    "vad_shadow_enabled",
    "vad_timing_bridge_enabled",
    "command_asr_shadow_bridge_enabled",
    "vosk_live_shadow_contract_enabled",
    "vosk_shadow_invocation_plan_enabled",
    "vosk_shadow_pcm_reference_enabled",
    "vosk_shadow_asr_result_enabled",
    "vosk_shadow_recognition_preflight_enabled",
    "vosk_shadow_invocation_attempt_enabled",
)

CONTROLLED_RECOGNITION_FLAGS: tuple[str, ...] = (
    "vosk_shadow_controlled_recognition_enabled",
    "vosk_shadow_controlled_recognition_dry_run_enabled",
    "vosk_shadow_controlled_recognition_result_enabled",
)


def validate_controlled_recognition_boundary(
    *,
    settings_path: Path,
    log_path: Path,
    require_records: bool = False,
    require_command_candidates: bool = False,
    require_restored_config: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []

    settings_result = _validate_settings_boundary(
        settings_path=settings_path,
        require_restored_config=require_restored_config,
    )
    if not settings_result["accepted"]:
        for issue in settings_result["issues"]:
            issues.append(f"settings:{issue}")

    readiness_result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=require_records,
        require_command_candidates=require_command_candidates,
    )
    if not bool(readiness_result.get("accepted", False)):
        for issue in _string_list(readiness_result.get("issues")):
            issues.append(f"readiness:{issue}")

    accepted = not issues

    return {
        "accepted": accepted,
        "validator": "controlled_recognition_boundary",
        "settings_path": str(settings_path),
        "log_path": str(log_path),
        "issues": issues,
        "decision": _decision(
            accepted=accepted,
            settings_accepted=bool(settings_result.get("accepted", False)),
            readiness_accepted=bool(readiness_result.get("accepted", False)),
            controlled_flags_enabled=settings_result["controlled_flags_enabled"],
        ),
        "settings": settings_result,
        "controlled_recognition_readiness": readiness_result,
        "policy": {
            "current_stage_controlled_recognition_enabled": False,
            "current_stage_vosk_recognition_allowed": False,
            "current_stage_command_execution_allowed": False,
            "current_stage_faster_whisper_bypass_allowed": False,
            "current_stage_runtime_takeover_allowed": False,
            "controlled_flags_may_be_missing_or_false": True,
            "future_observe_only_invocation_requires_new_flag": True,
        },
        "safety": {
            "observe_only": True,
            "command_execution_allowed": False,
            "runtime_takeover_allowed": False,
            "faster_whisper_bypass_allowed": False,
            "raw_pcm_logging_allowed": False,
            "controlled_recognition_enabled": False,
        },
        "required_records": require_records,
        "required_command_candidates": require_command_candidates,
        "require_restored_config": require_restored_config,
    }


def _validate_settings_boundary(
    *,
    settings_path: Path,
    require_restored_config: bool,
) -> dict[str, Any]:
    issues: list[str] = []

    if not settings_path.exists():
        return {
            "accepted": False,
            "settings_path": str(settings_path),
            "issues": ["settings_file_missing"],
            "baseline": {},
            "observation_flags": {},
            "controlled_flags": {},
            "controlled_flags_enabled": [],
        }

    try:
        raw_settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "accepted": False,
            "settings_path": str(settings_path),
            "issues": ["settings_json_invalid"],
            "baseline": {},
            "observation_flags": {},
            "controlled_flags": {},
            "controlled_flags_enabled": [],
        }

    if not isinstance(raw_settings, Mapping):
        return {
            "accepted": False,
            "settings_path": str(settings_path),
            "issues": ["settings_root_must_be_object"],
            "baseline": {},
            "observation_flags": {},
            "controlled_flags": {},
            "controlled_flags_enabled": [],
        }

    voice_engine = raw_settings.get("voice_engine")
    if not isinstance(voice_engine, Mapping):
        return {
            "accepted": False,
            "settings_path": str(settings_path),
            "issues": ["voice_engine_settings_missing"],
            "baseline": {},
            "observation_flags": {},
            "controlled_flags": {},
            "controlled_flags_enabled": [],
        }

    baseline: dict[str, Any] = {}
    for key, expected in SAFE_BASELINE_FIELDS.items():
        actual = voice_engine.get(key)
        baseline[key] = actual
        if actual != expected:
            issues.append(f"unsafe_baseline_{key}")

    observation_flags: dict[str, bool] = {}
    for key in OBSERVATION_FLAGS:
        value = bool(voice_engine.get(key, False))
        observation_flags[key] = value
        if require_restored_config and value:
            issues.append(f"observation_flag_not_restored_{key}")

    controlled_flags: dict[str, bool] = {}
    controlled_flags_enabled: list[str] = []
    for key in CONTROLLED_RECOGNITION_FLAGS:
        value = bool(voice_engine.get(key, False))
        controlled_flags[key] = value
        if value:
            controlled_flags_enabled.append(key)
            issues.append(f"controlled_recognition_flag_enabled_{key}")

    return {
        "accepted": not issues,
        "settings_path": str(settings_path),
        "issues": issues,
        "baseline": baseline,
        "observation_flags": observation_flags,
        "controlled_flags": controlled_flags,
        "controlled_flags_enabled": controlled_flags_enabled,
    }


def _decision(
    *,
    accepted: bool,
    settings_accepted: bool,
    readiness_accepted: bool,
    controlled_flags_enabled: list[str],
) -> str:
    if controlled_flags_enabled:
        return "disable_controlled_recognition_flags_before_boundary_acceptance"
    if not settings_accepted:
        return "restore_safe_config_before_controlled_recognition_boundary"
    if not readiness_accepted:
        return "fix_controlled_recognition_readiness_before_boundary_acceptance"
    if accepted:
        return "controlled_recognition_boundary_ready_but_current_stage_disabled"
    return "controlled_recognition_boundary_not_ready"


def _string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    return [str(item) for item in raw_value]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the disabled-by-default boundary before any controlled "
            "observe-only Vosk recognition invocation is introduced."
        )
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Path to config/settings.json.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument(
        "--require-records",
        action="store_true",
        help="Require at least one JSONL telemetry record.",
    )
    parser.add_argument(
        "--require-command-candidates",
        action="store_true",
        help="Require safe command/wake_command capture-window candidates.",
    )
    parser.add_argument(
        "--allow-active-observation-config",
        action="store_true",
        help="Allow active observation flags in settings.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_controlled_recognition_boundary(
        settings_path=args.settings,
        log_path=args.log_path,
        require_records=args.require_records,
        require_command_candidates=args.require_command_candidates,
        require_restored_config=not args.allow_active_observation_config,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
