#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_voice_engine_v2_vosk_shadow_observation import (  # noqa: E402
    DEFAULT_SETTINGS_PATH,
    OBSERVATION_FLAGS,
    RESTORED_OBSERVATION_FLAGS,
    baseline_safety_issues,
    load_settings,
    observation_flag_status,
)
from scripts.validate_voice_engine_v2_vad_timing_vosk_live_shadow import (  # noqa: E402
    DEFAULT_LOG_PATH,
    validate_vad_timing_vosk_live_shadow_log,
)
from scripts.validate_voice_engine_v2_vosk_shadow_invocation_plan import (  # noqa: E402
    validate_vosk_shadow_invocation_plan_log,
)
from scripts.validate_voice_engine_v2_vosk_shadow_pcm_reference import (  # noqa: E402
    validate_vosk_shadow_pcm_reference_log,
)
from scripts.validate_voice_engine_v2_vosk_shadow_asr_result import (  # noqa: E402
    validate_vosk_shadow_asr_result_log,
)
from scripts.validate_voice_engine_v2_vosk_shadow_recognition_preflight import (  # noqa: E402
    validate_vosk_shadow_recognition_preflight_log,
)


def validate_observation_config(
    *,
    settings_path: Path,
    require_restored: bool,
) -> dict[str, Any]:
    settings = load_settings(settings_path)
    baseline_issues = baseline_safety_issues(settings)
    observation_flags = observation_flag_status(settings)
    issues = list(baseline_issues)

    if require_restored:
        for key, expected_value in RESTORED_OBSERVATION_FLAGS.items():
            actual_value = observation_flags.get(key, False)
            if actual_value is not expected_value:
                issues.append(f"voice_engine.{key}_must_be_false_after_observation")

    return {
        "accepted": not issues,
        "settings_path": str(settings_path),
        "require_restored": require_restored,
        "baseline_issues": baseline_issues,
        "observation_flags": observation_flags,
        "expected_observation_flags": (
            RESTORED_OBSERVATION_FLAGS if require_restored else OBSERVATION_FLAGS
        ),
        "issues": issues,
    }


def validate_vosk_shadow_observation(
    *,
    settings_path: Path,
    log_path: Path,
    require_contract_attached: bool,
    require_invocation_plan_attached: bool,
    require_invocation_plan_ready: bool,
    require_pcm_reference_attached: bool,
    require_pcm_reference_ready: bool,
    require_asr_result_attached: bool,
    require_asr_result_not_attempted: bool,
    require_recognition_preflight_attached: bool,
    require_recognition_preflight_ready: bool,
    require_restored_config: bool,
    allow_recognition_attempt: bool,
) -> dict[str, Any]:
    config_result = validate_observation_config(
        settings_path=settings_path,
        require_restored=require_restored_config,
    )
    telemetry_result = validate_vad_timing_vosk_live_shadow_log(
        log_path=log_path,
        require_records=True,
        require_contract_attached=require_contract_attached,
        require_enabled_shape_only=True,
        require_capture_window_hook=True,
    )

    invocation_plan_result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=require_invocation_plan_attached,
        require_enabled=require_invocation_plan_attached,
        require_ready=require_invocation_plan_ready,
        require_capture_window_hook=True,
    )
    pcm_reference_result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=require_pcm_reference_attached,
        require_enabled=require_pcm_reference_attached,
        require_ready=require_pcm_reference_ready,
        require_capture_window_hook=True,
        require_expected_source=True,
    )
    asr_result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=require_asr_result_attached,
        require_enabled=require_asr_result_attached,
        require_not_attempted=require_asr_result_not_attempted,
        require_capture_window_hook=True,
        require_expected_source=True,
        allow_recognition_attempt=allow_recognition_attempt,
    )
    recognition_preflight_result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=require_recognition_preflight_attached,
        require_enabled=require_recognition_preflight_attached,
        require_ready=require_recognition_preflight_ready,
        require_capture_window_hook=True,
        require_expected_source=True,
    )

    accepted = (
        bool(config_result.get("accepted", False))
        and bool(telemetry_result.get("accepted", False))
        and bool(invocation_plan_result.get("accepted", False))
        and bool(pcm_reference_result.get("accepted", False))
        and bool(asr_result.get("accepted", False))
        and bool(recognition_preflight_result.get("accepted", False))
    )

    return {
        "accepted": accepted,
        "validator": "vosk_shadow_observation",
        "settings_path": str(settings_path),
        "log_path": str(log_path),
        "config": config_result,
        "telemetry": telemetry_result,
        "invocation_plan": invocation_plan_result,
        "pcm_reference": pcm_reference_result,
        "asr_result": asr_result,
        "recognition_preflight": recognition_preflight_result,
        "issues": [
            *[f"config:{issue}" for issue in config_result.get("issues", [])],
            *[f"telemetry:{issue}" for issue in telemetry_result.get("issues", [])],
            *[
                f"invocation_plan:{issue}"
                for issue in invocation_plan_result.get("issues", [])
            ],
            *[
                f"pcm_reference:{issue}"
                for issue in pcm_reference_result.get("issues", [])
            ],
            *[
                f"asr_result:{issue}"
                for issue in asr_result.get("issues", [])
            ],
            *[
                f"recognition_preflight:{issue}"
                for issue in recognition_preflight_result.get("issues", [])
            ],
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the observe-only Voice Engine v2 Vosk shadow observation "
            "procedure after runtime telemetry capture."
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
        help="Path to VAD timing bridge JSONL telemetry.",
    )
    parser.add_argument(
        "--require-contract-attached",
        action="store_true",
        help="Require at least one metadata.vosk_live_shadow record.",
    )
    parser.add_argument(
        "--require-invocation-plan-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_invocation_plan record.",
    )
    parser.add_argument(
        "--require-invocation-plan-ready",
        action="store_true",
        help="Require at least one plan_ready=true invocation plan record.",
    )
    parser.add_argument(
        "--require-pcm-reference-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_pcm_reference record.",
    )
    parser.add_argument(
        "--require-pcm-reference-ready",
        action="store_true",
        help="Require at least one reference_ready=true PCM reference record.",
    )
    parser.add_argument(
        "--require-asr-result-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_asr_result record.",
    )
    parser.add_argument(
        "--require-asr-result-not-attempted",
        action="store_true",
        help="Require at least one safe not-attempted Vosk shadow ASR result record.",
    )
    parser.add_argument(
        "--require-recognition-preflight-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_recognition_preflight record.",
    )
    parser.add_argument(
        "--require-recognition-preflight-ready",
        action="store_true",
        help="Require at least one ready-but-blocked Vosk recognition preflight record.",
    )
    parser.add_argument(
        "--allow-recognition-attempt",
        action="store_true",
        help=(
            "Allow recognition attempt/result telemetry. Do not use this for "
            "Stage 24AV final acceptance."
        ),
    )
    parser.add_argument(
        "--allow-active-observation-config",
        action="store_true",
        help=(
            "Allow observation flags to remain enabled. Use only before the "
            "restore command, never for final acceptance."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_vosk_shadow_observation(
            settings_path=args.settings,
            log_path=args.log_path,
            require_contract_attached=args.require_contract_attached,
            require_invocation_plan_attached=args.require_invocation_plan_attached,
            require_invocation_plan_ready=args.require_invocation_plan_ready,
            require_pcm_reference_attached=args.require_pcm_reference_attached,
            require_pcm_reference_ready=args.require_pcm_reference_ready,
            require_asr_result_attached=args.require_asr_result_attached,
            require_asr_result_not_attempted=args.require_asr_result_not_attempted,
            require_recognition_preflight_attached=(
                args.require_recognition_preflight_attached
            ),
            require_recognition_preflight_ready=(
                args.require_recognition_preflight_ready
            ),
            require_restored_config=not args.allow_active_observation_config,
            allow_recognition_attempt=args.allow_recognition_attempt,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "accepted": False,
            "validator": "vosk_shadow_observation",
            "error": str(error),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())