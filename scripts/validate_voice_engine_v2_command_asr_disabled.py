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


from modules.runtime.voice_engine_v2.command_asr import (  # noqa: E402
    DISABLED_COMMAND_ASR_REASON,
    build_disabled_command_asr_candidate,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")


def validate_disabled_command_asr_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_segment_backed_disabled_records: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []

    total_lines = 0
    valid_json_records = 0
    invalid_json_records = 0

    command_asr_contract_records = 0
    segment_backed_disabled_records = 0
    not_ready_records = 0

    reason_counts: Counter[str] = Counter()
    asr_reason_counts: Counter[str] = Counter()
    recognizer_name_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    publish_stage_counts: Counter[str] = Counter()

    recognizer_enabled_records = 0
    recognition_attempted_records = 0
    recognized_records = 0
    candidate_present_records = 0
    raw_pcm_records = 0

    unsafe_action_records = 0
    unsafe_full_stt_records = 0
    unsafe_takeover_records = 0

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

        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue

        endpointing_candidate = metadata.get("endpointing_candidate")
        if not isinstance(endpointing_candidate, dict):
            continue

        try:
            candidate = build_disabled_command_asr_candidate(record=record)
        except ValueError as error:
            issues.append(f"line_{line_number}:unsafe_command_asr:{error}")
            continue

        payload = candidate.to_json_dict()
        command_asr_contract_records += 1

        reason = str(payload.get("reason") or "")
        asr_reason = str(payload.get("asr_reason") or "")
        recognizer_name = str(payload.get("recognizer_name") or "")
        source = str(payload.get("source") or "")
        publish_stage = str(payload.get("publish_stage") or "")

        if reason:
            reason_counts[reason] += 1
        if asr_reason:
            asr_reason_counts[asr_reason] += 1
        if recognizer_name:
            recognizer_name_counts[recognizer_name] += 1
        if source:
            source_counts[source] += 1
        if publish_stage:
            publish_stage_counts[publish_stage] += 1

        segment_present = bool(payload.get("segment_present", False))
        recognizer_enabled = bool(payload.get("recognizer_enabled", False))
        recognition_attempted = bool(payload.get("recognition_attempted", False))
        recognized = bool(payload.get("recognized", False))
        candidate_present = bool(payload.get("candidate_present", False))

        if segment_present and reason == DISABLED_COMMAND_ASR_REASON:
            segment_backed_disabled_records += 1
        if not segment_present:
            not_ready_records += 1

        if recognizer_enabled:
            recognizer_enabled_records += 1
            issues.append(f"line_{line_number}:command_asr_recognizer_enabled")
        if recognition_attempted:
            recognition_attempted_records += 1
            issues.append(f"line_{line_number}:command_asr_recognition_attempted")
        if recognized:
            recognized_records += 1
            issues.append(f"line_{line_number}:command_asr_recognized_text")
        if candidate_present:
            candidate_present_records += 1
            issues.append(f"line_{line_number}:command_asr_candidate_present")
        if bool(payload.get("raw_pcm_included", False)):
            raw_pcm_records += 1
            issues.append(f"line_{line_number}:command_asr_raw_pcm_included")
        if bool(payload.get("action_executed", False)):
            unsafe_action_records += 1
            issues.append(f"line_{line_number}:command_asr_action_executed")
        if bool(payload.get("full_stt_prevented", False)):
            unsafe_full_stt_records += 1
            issues.append(f"line_{line_number}:command_asr_full_stt_prevented")
        if bool(payload.get("runtime_takeover", False)):
            unsafe_takeover_records += 1
            issues.append(f"line_{line_number}:command_asr_runtime_takeover")

    if invalid_json_records > 0:
        issues.append("invalid_json_records_present")

    if require_records and command_asr_contract_records <= 0:
        issues.append("command_asr_contract_records_missing")

    if (
        require_segment_backed_disabled_records
        and segment_backed_disabled_records <= 0
    ):
        issues.append("command_asr_segment_backed_disabled_records_missing")

    return {
        "accepted": not issues,
        "log_path": str(log_path),
        "total_lines": total_lines,
        "valid_json_records": valid_json_records,
        "invalid_json_records": invalid_json_records,
        "command_asr_contract_records": command_asr_contract_records,
        "segment_backed_disabled_records": segment_backed_disabled_records,
        "not_ready_records": not_ready_records,
        "reason_counts": dict(reason_counts),
        "asr_reason_counts": dict(asr_reason_counts),
        "recognizer_name_counts": dict(recognizer_name_counts),
        "source_counts": dict(source_counts),
        "publish_stage_counts": dict(publish_stage_counts),
        "recognizer_enabled_records": recognizer_enabled_records,
        "recognition_attempted_records": recognition_attempted_records,
        "recognized_records": recognized_records,
        "candidate_present_records": candidate_present_records,
        "raw_pcm_records": raw_pcm_records,
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "required_records": require_records,
        "required_segment_backed_disabled_records": (
            require_segment_backed_disabled_records
        ),
        "issues": issues,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate disabled Voice Engine v2 command ASR contracts from "
            "VAD timing bridge telemetry."
        )
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to voice_engine_v2_vad_timing_bridge.jsonl.",
    )
    parser.add_argument("--require-records", action="store_true")
    parser.add_argument(
        "--require-segment-backed-disabled-records",
        action="store_true",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = validate_disabled_command_asr_log(
        log_path=args.log_path,
        require_records=args.require_records,
        require_segment_backed_disabled_records=(
            args.require_segment_backed_disabled_records
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())