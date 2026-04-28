#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.runtime.voice_engine_v2.vosk_shadow_asr_result import (  # noqa: E402
    ASR_RESULT_NOT_ATTEMPTED_REASON,
    DEFAULT_ASR_RESULT_METADATA_KEY,
    VOSK_SHADOW_ASR_RESULT_VERSION,
    validate_vosk_shadow_asr_result,
)
from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (  # noqa: E402
    EXPECTED_HOOK,
    EXPECTED_PUBLISH_STAGE,
    EXPECTED_SOURCE,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")

UNSAFE_ASR_RESULT_FIELDS: tuple[str, ...] = (
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "independent_microphone_stream_started",
    "live_command_recognition_enabled",
)

CURRENTLY_BLOCKED_RECOGNITION_FIELDS: tuple[str, ...] = (
    "recognition_invocation_performed",
    "recognition_attempted",
    "recognized",
    "command_matched",
    "pcm_retrieval_performed",
)


def validate_vosk_shadow_asr_result_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_result_attached: bool = False,
    require_enabled: bool = False,
    require_not_attempted: bool = False,
    require_capture_window_hook: bool = True,
    require_expected_source: bool = True,
    allow_recognition_attempt: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []
    record_count = 0
    invalid_json_lines = 0
    invalid_record_lines = 0
    result_records = 0
    enabled_result_records = 0
    not_attempted_result_records = 0
    result_present_records = 0
    expected_version_records = 0
    capture_window_hook_records = 0
    non_capture_window_hook_records = 0
    expected_source_records = 0
    expected_publish_stage_records = 0
    unsafe_result_records = 0
    recognition_attempt_records = 0
    positive_segment_sample_count_records = 0
    positive_segment_byte_count_records = 0

    reason_counts: Counter[str] = Counter()
    version_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    publish_stage_counts: Counter[str] = Counter()
    unsafe_field_counts: Counter[str] = Counter()
    recognition_field_counts: Counter[str] = Counter()

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=record_count,
            invalid_json_lines=invalid_json_lines,
            invalid_record_lines=invalid_record_lines,
            result_records=result_records,
            enabled_result_records=enabled_result_records,
            not_attempted_result_records=not_attempted_result_records,
            result_present_records=result_present_records,
            expected_version_records=expected_version_records,
            capture_window_hook_records=capture_window_hook_records,
            non_capture_window_hook_records=non_capture_window_hook_records,
            expected_source_records=expected_source_records,
            expected_publish_stage_records=expected_publish_stage_records,
            unsafe_result_records=unsafe_result_records,
            recognition_attempt_records=recognition_attempt_records,
            positive_segment_sample_count_records=positive_segment_sample_count_records,
            positive_segment_byte_count_records=positive_segment_byte_count_records,
            reason_counts=reason_counts,
            version_counts=version_counts,
            source_counts=source_counts,
            publish_stage_counts=publish_stage_counts,
            unsafe_field_counts=unsafe_field_counts,
            recognition_field_counts=recognition_field_counts,
            issues=issues,
            require_records=require_records,
            require_result_attached=require_result_attached,
            require_enabled=require_enabled,
            require_not_attempted=require_not_attempted,
            require_capture_window_hook=require_capture_window_hook,
            require_expected_source=require_expected_source,
            allow_recognition_attempt=allow_recognition_attempt,
        )

    for line_number, raw_line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue

        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid_json_lines += 1
            issues.append(f"line_{line_number}:invalid_json")
            continue

        if not isinstance(record, Mapping):
            invalid_record_lines += 1
            issues.append(f"line_{line_number}:record_must_be_object")
            continue

        record_count += 1

        metadata = _mapping(record.get("metadata"))
        result = _mapping(metadata.get(DEFAULT_ASR_RESULT_METADATA_KEY))
        if not result:
            continue

        result_records += 1

        reason = str(result.get("reason") or "")
        version = str(result.get("result_version") or "")
        source = str(result.get("source") or "")
        publish_stage = str(result.get("publish_stage") or "")

        if reason:
            reason_counts[reason] += 1
        if version:
            version_counts[version] += 1
        if source:
            source_counts[source] += 1
        if publish_stage:
            publish_stage_counts[publish_stage] += 1

        if version == VOSK_SHADOW_ASR_RESULT_VERSION:
            expected_version_records += 1

        if result.get("enabled") is True:
            enabled_result_records += 1

        if result.get("result_present") is True:
            result_present_records += 1

        if reason == ASR_RESULT_NOT_ATTEMPTED_REASON:
            not_attempted_result_records += 1

        record_hook = str(record.get("hook") or "")
        result_hook = str(result.get("hook") or "")
        if record_hook == EXPECTED_HOOK and result_hook == EXPECTED_HOOK:
            capture_window_hook_records += 1
        else:
            non_capture_window_hook_records += 1
            if require_capture_window_hook:
                issues.append(f"line_{line_number}:non_capture_window_hook")

        if source == EXPECTED_SOURCE:
            expected_source_records += 1
        elif require_expected_source:
            issues.append(f"line_{line_number}:unexpected_audio_source")

        if publish_stage == EXPECTED_PUBLISH_STAGE:
            expected_publish_stage_records += 1
        elif require_expected_source:
            issues.append(f"line_{line_number}:unexpected_publish_stage")

        if _positive_int(result.get("segment_audio_sample_count")) > 0:
            positive_segment_sample_count_records += 1

        if _positive_int(result.get("segment_published_byte_count")) > 0:
            positive_segment_byte_count_records += 1

        result_validation = validate_vosk_shadow_asr_result(result)
        for validation_issue in result_validation.get("issues", []):
            issues.append(f"line_{line_number}:{validation_issue}")

        unsafe_fields = [
            field_name
            for field_name in UNSAFE_ASR_RESULT_FIELDS
            if result.get(field_name) is not False
        ]
        if unsafe_fields:
            unsafe_result_records += 1
            for field_name in unsafe_fields:
                unsafe_field_counts[field_name] += 1

        blocked_recognition_fields = [
            field_name
            for field_name in CURRENTLY_BLOCKED_RECOGNITION_FIELDS
            if result.get(field_name) is not False
        ]
        if blocked_recognition_fields:
            recognition_attempt_records += 1
            for field_name in blocked_recognition_fields:
                recognition_field_counts[field_name] += 1
            if not allow_recognition_attempt:
                issues.append(f"line_{line_number}:recognition_attempt_not_allowed")

    if require_records and record_count <= 0:
        issues.append("records_missing")
    if require_result_attached and result_records <= 0:
        issues.append("vosk_shadow_asr_result_records_missing")
    if require_enabled and enabled_result_records <= 0:
        issues.append("enabled_vosk_shadow_asr_result_records_missing")
    if require_not_attempted and not_attempted_result_records <= 0:
        issues.append("not_attempted_vosk_shadow_asr_result_records_missing")
    if result_records > 0 and expected_version_records != result_records:
        issues.append("unexpected_vosk_shadow_asr_result_version")
    if result_present_records > 0 and not allow_recognition_attempt:
        issues.append("result_present_records_not_allowed")
    if unsafe_result_records > 0:
        issues.append("unsafe_vosk_shadow_asr_result_records_present")
    if recognition_attempt_records > 0 and not allow_recognition_attempt:
        issues.append("recognition_attempt_records_not_allowed")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=record_count,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        result_records=result_records,
        enabled_result_records=enabled_result_records,
        not_attempted_result_records=not_attempted_result_records,
        result_present_records=result_present_records,
        expected_version_records=expected_version_records,
        capture_window_hook_records=capture_window_hook_records,
        non_capture_window_hook_records=non_capture_window_hook_records,
        expected_source_records=expected_source_records,
        expected_publish_stage_records=expected_publish_stage_records,
        unsafe_result_records=unsafe_result_records,
        recognition_attempt_records=recognition_attempt_records,
        positive_segment_sample_count_records=positive_segment_sample_count_records,
        positive_segment_byte_count_records=positive_segment_byte_count_records,
        reason_counts=reason_counts,
        version_counts=version_counts,
        source_counts=source_counts,
        publish_stage_counts=publish_stage_counts,
        unsafe_field_counts=unsafe_field_counts,
        recognition_field_counts=recognition_field_counts,
        issues=issues,
        require_records=require_records,
        require_result_attached=require_result_attached,
        require_enabled=require_enabled,
        require_not_attempted=require_not_attempted,
        require_capture_window_hook=require_capture_window_hook,
        require_expected_source=require_expected_source,
        allow_recognition_attempt=allow_recognition_attempt,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    result_records: int,
    enabled_result_records: int,
    not_attempted_result_records: int,
    result_present_records: int,
    expected_version_records: int,
    capture_window_hook_records: int,
    non_capture_window_hook_records: int,
    expected_source_records: int,
    expected_publish_stage_records: int,
    unsafe_result_records: int,
    recognition_attempt_records: int,
    positive_segment_sample_count_records: int,
    positive_segment_byte_count_records: int,
    reason_counts: Counter[str],
    version_counts: Counter[str],
    source_counts: Counter[str],
    publish_stage_counts: Counter[str],
    unsafe_field_counts: Counter[str],
    recognition_field_counts: Counter[str],
    issues: list[str],
    require_records: bool,
    require_result_attached: bool,
    require_enabled: bool,
    require_not_attempted: bool,
    require_capture_window_hook: bool,
    require_expected_source: bool,
    allow_recognition_attempt: bool,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "vosk_shadow_asr_result",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "result_records": result_records,
        "enabled_result_records": enabled_result_records,
        "not_attempted_result_records": not_attempted_result_records,
        "result_present_records": result_present_records,
        "expected_version_records": expected_version_records,
        "capture_window_hook_records": capture_window_hook_records,
        "non_capture_window_hook_records": non_capture_window_hook_records,
        "expected_source_records": expected_source_records,
        "expected_publish_stage_records": expected_publish_stage_records,
        "unsafe_result_records": unsafe_result_records,
        "recognition_attempt_records": recognition_attempt_records,
        "positive_segment_sample_count_records": positive_segment_sample_count_records,
        "positive_segment_byte_count_records": positive_segment_byte_count_records,
        "reason_counts": dict(reason_counts),
        "version_counts": dict(version_counts),
        "source_counts": dict(source_counts),
        "publish_stage_counts": dict(publish_stage_counts),
        "unsafe_field_counts": dict(unsafe_field_counts),
        "recognition_field_counts": dict(recognition_field_counts),
        "issues": issues,
        "required_records": require_records,
        "required_result_attached": require_result_attached,
        "required_enabled": require_enabled,
        "required_not_attempted": require_not_attempted,
        "required_capture_window_hook": require_capture_window_hook,
        "required_expected_source": require_expected_source,
        "recognition_attempt_allowed": allow_recognition_attempt,
        "runtime_integration_allowed": False,
        "command_execution_allowed": False,
        "faster_whisper_bypass_allowed": False,
        "independent_microphone_stream_allowed": False,
        "live_command_recognition_allowed": False,
    }


def _mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _positive_int(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate observe-only Voice Engine v2 Vosk shadow ASR result "
            "telemetry from the VAD timing bridge JSONL log."
        )
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
        help="Require at least one telemetry record.",
    )
    parser.add_argument(
        "--require-result-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_asr_result record.",
    )
    parser.add_argument(
        "--require-enabled",
        action="store_true",
        help="Require at least one enabled ASR result record.",
    )
    parser.add_argument(
        "--require-not-attempted",
        action="store_true",
        help="Require at least one safe not-attempted ASR result record.",
    )
    parser.add_argument(
        "--allow-non-capture-window-hook",
        action="store_true",
        help="Allow ASR result records outside capture_window_pre_transcription.",
    )
    parser.add_argument(
        "--allow-unexpected-source",
        action="store_true",
        help="Allow ASR result records from non-standard audio sources.",
    )
    parser.add_argument(
        "--allow-recognition-attempt",
        action="store_true",
        help=(
            "Allow recognition attempt/result telemetry. Keep this disabled for "
            "Stage 24AT runtime validation."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        result = validate_vosk_shadow_asr_result_log(
            log_path=args.log_path,
            require_records=args.require_records,
            require_result_attached=args.require_result_attached,
            require_enabled=args.require_enabled,
            require_not_attempted=args.require_not_attempted,
            require_capture_window_hook=not args.allow_non_capture_window_hook,
            require_expected_source=not args.allow_unexpected_source,
            allow_recognition_attempt=args.allow_recognition_attempt,
        )
    except OSError as error:
        result = {
            "accepted": False,
            "validator": "vosk_shadow_asr_result",
            "error": str(error),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())