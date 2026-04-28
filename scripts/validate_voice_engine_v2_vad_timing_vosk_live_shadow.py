from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")
EXPECTED_HOOK = "capture_window_pre_transcription"


def validate_vad_timing_vosk_live_shadow_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_contract_attached: bool = False,
    require_enabled_shape_only: bool = True,
    require_capture_window_hook: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []

    if not log_path.exists():
        if require_records:
            issues.append("log_path_missing")
        return {
            "accepted": not issues,
            "validator": "vad_timing_vosk_live_shadow",
            "expected_log_path": str(DEFAULT_LOG_PATH),
            "log_path": str(log_path),
            "records": 0,
            "contract_records": 0,
            "issues": issues,
        }

    records = 0
    contract_records = 0
    enabled_contract_records = 0
    observed_contract_records = 0
    recognition_attempted_records = 0
    recognized_records = 0
    command_matched_records = 0
    capture_window_hook_records = 0
    non_capture_window_hook_records = 0
    unsafe_action_records = 0
    unsafe_full_stt_records = 0
    unsafe_takeover_records = 0
    unsafe_microphone_records = 0
    unsafe_independent_microphone_records = 0
    unsafe_live_command_records = 0
    unsafe_faster_whisper_bypass_records = 0
    unsafe_runtime_integration_records = 0
    raw_pcm_records = 0

    hook_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            issues.append(f"line_{line_number}:invalid_json")
            continue

        if not isinstance(record, dict):
            issues.append(f"line_{line_number}:record_not_object")
            continue

        records += 1
        metadata = _mapping(record.get("metadata"))
        contract = _mapping(metadata.get("vosk_live_shadow"))
        if not contract:
            continue

        contract_records += 1

        hook = str(record.get("hook") or "")
        if hook:
            hook_counts[hook] += 1
        if hook == EXPECTED_HOOK:
            capture_window_hook_records += 1
        else:
            non_capture_window_hook_records += 1
            if require_capture_window_hook:
                issues.append(
                    f"line_{line_number}:unexpected_hook:{hook or '<missing>'}"
                )

        reason = str(contract.get("reason") or "")
        if reason:
            reason_counts[reason] += 1

        if contract.get("enabled") is True:
            enabled_contract_records += 1
        if contract.get("observed") is True:
            observed_contract_records += 1
        if contract.get("recognition_attempted") is True:
            recognition_attempted_records += 1
        if contract.get("recognized") is True:
            recognized_records += 1
        if contract.get("command_matched") is True:
            command_matched_records += 1

        if contract.get("action_executed") is not False:
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:action_executed")
        if contract.get("full_stt_prevented") is not False:
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:full_stt_prevented")
        if contract.get("runtime_takeover") is not False:
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:runtime_takeover")
        if contract.get("microphone_stream_started") is not False:
            unsafe_microphone_records += 1
            issues.append(f"line_{line_number}:microphone_stream_started")
        if contract.get("independent_microphone_stream_started") is not False:
            unsafe_independent_microphone_records += 1
            issues.append(f"line_{line_number}:independent_microphone_stream_started")
        if contract.get("live_command_recognition_enabled") is not False:
            unsafe_live_command_records += 1
            issues.append(f"line_{line_number}:live_command_recognition_enabled")
        if contract.get("faster_whisper_bypass_enabled") is not False:
            unsafe_faster_whisper_bypass_records += 1
            issues.append(f"line_{line_number}:faster_whisper_bypass_enabled")
        if contract.get("runtime_integration") is not False:
            unsafe_runtime_integration_records += 1
            issues.append(f"line_{line_number}:runtime_integration")
        if contract.get("raw_pcm_included") is not False:
            raw_pcm_records += 1
            issues.append(f"line_{line_number}:raw_pcm_included")

        if require_enabled_shape_only:
            if contract.get("enabled") is not True:
                issues.append(f"line_{line_number}:contract_not_enabled")
            if contract.get("observed") is not False:
                issues.append(f"line_{line_number}:contract_observed")
            if contract.get("recognition_attempted") is not False:
                issues.append(f"line_{line_number}:recognition_attempted")
            if contract.get("recognized") is not False:
                issues.append(f"line_{line_number}:recognized")
            if contract.get("command_matched") is not False:
                issues.append(f"line_{line_number}:command_matched")

    if require_records and records <= 0:
        issues.append("records_missing")
    if require_contract_attached and contract_records <= 0:
        issues.append("vosk_live_shadow_records_missing")

    return {
        "accepted": not issues,
        "validator": "vad_timing_vosk_live_shadow",
        "expected_log_path": str(DEFAULT_LOG_PATH),
        "log_path": str(log_path),
        "records": records,
        "contract_records": contract_records,
        "enabled_contract_records": enabled_contract_records,
        "observed_contract_records": observed_contract_records,
        "recognition_attempted_records": recognition_attempted_records,
        "recognized_records": recognized_records,
        "command_matched_records": command_matched_records,
        "capture_window_hook_records": capture_window_hook_records,
        "non_capture_window_hook_records": non_capture_window_hook_records,
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "unsafe_microphone_records": unsafe_microphone_records,
        "unsafe_independent_microphone_records": unsafe_independent_microphone_records,
        "unsafe_live_command_records": unsafe_live_command_records,
        "unsafe_faster_whisper_bypass_records": unsafe_faster_whisper_bypass_records,
        "unsafe_runtime_integration_records": unsafe_runtime_integration_records,
        "raw_pcm_records": raw_pcm_records,
        "hook_counts": dict(hook_counts),
        "reason_counts": dict(reason_counts),
        "required_enabled_shape_only": require_enabled_shape_only,
        "required_capture_window_hook": require_capture_window_hook,
        "issues": issues,
    }


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Vosk live shadow contract records embedded inside "
            "Voice Engine v2 VAD timing bridge telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-records", action="store_true")
    parser.add_argument("--require-contract-attached", action="store_true")
    parser.add_argument(
        "--allow-recognition",
        action="store_true",
        help=(
            "Allow recognition_attempted/recognized/observed records for later "
            "observation procedures."
        ),
    )
    parser.add_argument(
        "--allow-non-capture-window-hook",
        action="store_true",
        help="Allow Vosk shadow contract records outside capture window hook.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_vad_timing_vosk_live_shadow_log(
        log_path=args.log_path,
        require_records=args.require_records,
        require_contract_attached=args.require_contract_attached,
        require_enabled_shape_only=not args.allow_recognition,
        require_capture_window_hook=not args.allow_non_capture_window_hook,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())