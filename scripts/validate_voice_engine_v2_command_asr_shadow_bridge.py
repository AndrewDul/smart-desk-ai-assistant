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


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_command_asr_shadow_bridge.jsonl")


def validate_command_asr_shadow_bridge_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_candidate_attached: bool = False,
    require_disabled_only: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []

    total_lines = 0
    valid_json_records = 0
    invalid_json_records = 0

    bridge_records = 0
    enabled_records = 0
    disabled_records = 0
    observed_records = 0
    candidate_attached_records = 0
    command_asr_candidate_present_records = 0

    recognizer_enabled_records = 0
    recognition_attempted_records = 0
    recognized_records = 0
    raw_pcm_records = 0

    unsafe_action_records = 0
    unsafe_full_stt_records = 0
    unsafe_takeover_records = 0

    bridge_reason_counts: Counter[str] = Counter()
    command_asr_reason_counts: Counter[str] = Counter()
    asr_reason_counts: Counter[str] = Counter()
    recognizer_name_counts: Counter[str] = Counter()

    if not log_path.exists():
        return {
            "accepted": False,
            "log_path": str(log_path),
            "issues": [f"log_missing:{log_path}"],
        }

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        total_lines += 1

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as error:
            invalid_json_records += 1
            issues.append(f"line_{line_number}:invalid_json:{error.msg}")
            continue

        valid_json_records += 1

        if not isinstance(record, dict):
            issues.append(f"line_{line_number}:record_not_object")
            continue

        metadata = _mapping(record.get("metadata"))
        bridge = _mapping(metadata.get("command_asr_shadow_bridge"))
        if not bridge:
            continue

        bridge_records += 1

        if bool(bridge.get("enabled", False)):
            enabled_records += 1
        else:
            disabled_records += 1

        if bool(bridge.get("observed", False)):
            observed_records += 1

        if bool(bridge.get("candidate_attached", False)):
            candidate_attached_records += 1
            candidate = _mapping(metadata.get("command_asr_candidate"))
            if not candidate:
                issues.append(f"line_{line_number}:candidate_attached_but_missing")

        if bool(bridge.get("command_asr_candidate_present", False)):
            command_asr_candidate_present_records += 1

        bridge_reason = str(bridge.get("reason") or "")
        command_asr_reason = str(bridge.get("command_asr_reason") or "")
        asr_reason = str(bridge.get("asr_reason") or "")
        recognizer_name = str(bridge.get("recognizer_name") or "")

        if bridge_reason:
            bridge_reason_counts[bridge_reason] += 1
        if command_asr_reason:
            command_asr_reason_counts[command_asr_reason] += 1
        if asr_reason:
            asr_reason_counts[asr_reason] += 1
        if recognizer_name:
            recognizer_name_counts[recognizer_name] += 1

        if bool(bridge.get("recognizer_enabled", False)):
            recognizer_enabled_records += 1
            if require_disabled_only:
                issues.append(f"line_{line_number}:recognizer_enabled")
        if bool(bridge.get("recognition_attempted", False)):
            recognition_attempted_records += 1
            if require_disabled_only:
                issues.append(f"line_{line_number}:recognition_attempted")
        if bool(bridge.get("recognized", False)):
            recognized_records += 1
            if require_disabled_only:
                issues.append(f"line_{line_number}:recognized")
        if bool(bridge.get("raw_pcm_included", False)):
            raw_pcm_records += 1
            issues.append(f"line_{line_number}:bridge_raw_pcm_included")
        if bool(bridge.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:bridge_action_executed")
        if bool(bridge.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:bridge_full_stt_prevented")
        if bool(bridge.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:bridge_runtime_takeover")

        candidate = _mapping(metadata.get("command_asr_candidate"))
        if candidate:
            if bool(candidate.get("raw_pcm_included", False)):
                raw_pcm_records += 1
                issues.append(f"line_{line_number}:candidate_raw_pcm_included")
            if bool(candidate.get("action_executed", False)):
                unsafe_action_records += 1
                issues.append(f"line_{line_number}:candidate_action_executed")
            if bool(candidate.get("full_stt_prevented", False)):
                unsafe_full_stt_records += 1
                issues.append(f"line_{line_number}:candidate_full_stt_prevented")
            if bool(candidate.get("runtime_takeover", False)):
                unsafe_takeover_records += 1
                issues.append(f"line_{line_number}:candidate_runtime_takeover")

    if invalid_json_records > 0:
        issues.append("invalid_json_records_present")

    if require_records and bridge_records <= 0:
        issues.append("command_asr_shadow_bridge_records_missing")

    if require_candidate_attached and candidate_attached_records <= 0:
        issues.append("command_asr_shadow_bridge_candidate_attached_records_missing")

    return {
        "accepted": not issues,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "invalid_json_records": invalid_json_records,
        "bridge_records": bridge_records,
        "enabled_records": enabled_records,
        "disabled_records": disabled_records,
        "observed_records": observed_records,
        "candidate_attached_records": candidate_attached_records,
        "command_asr_candidate_present_records": (
            command_asr_candidate_present_records
        ),
        "recognizer_enabled_records": recognizer_enabled_records,
        "recognition_attempted_records": recognition_attempted_records,
        "recognized_records": recognized_records,
        "raw_pcm_records": raw_pcm_records,
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "bridge_reason_counts": dict(bridge_reason_counts),
        "command_asr_reason_counts": dict(command_asr_reason_counts),
        "asr_reason_counts": dict(asr_reason_counts),
        "recognizer_name_counts": dict(recognizer_name_counts),
        "required_records": require_records,
        "required_candidate_attached": require_candidate_attached,
        "required_disabled_only": require_disabled_only,
        "issues": issues,
    }


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Voice Engine v2 command ASR shadow bridge telemetry."
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to command ASR shadow bridge JSONL telemetry.",
    )
    parser.add_argument("--require-records", action="store_true")
    parser.add_argument("--require-candidate-attached", action="store_true")
    parser.add_argument("--require-disabled-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_command_asr_shadow_bridge_log(
        log_path=args.log_path,
        require_records=args.require_records,
        require_candidate_attached=args.require_candidate_attached,
        require_disabled_only=args.require_disabled_only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())