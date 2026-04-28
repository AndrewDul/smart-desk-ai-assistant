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

from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (  # noqa: E402
    EXPECTED_HOOK,
    EXPECTED_PUBLISH_STAGE,
    EXPECTED_SOURCE,
)
from modules.runtime.voice_engine_v2.vosk_shadow_recognition_preflight import (  # noqa: E402
    DEFAULT_RECOGNITION_PREFLIGHT_METADATA_KEY,
    RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON,
    VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION,
    validate_vosk_shadow_recognition_preflight,
)


DEFAULT_LOG_PATH = Path("var/data/voice_engine_v2_vad_timing_bridge.jsonl")

UNSAFE_PREFLIGHT_FIELDS: tuple[str, ...] = (
    "pcm_retrieval_allowed",
    "pcm_retrieval_performed",
    "recognition_invocation_allowed",
    "recognition_invocation_performed",
    "recognition_attempted",
    "result_present",
    "recognized",
    "command_matched",
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

READY_DEPENDENCY_FIELDS: tuple[str, ...] = (
    "live_shadow_present",
    "invocation_plan_present",
    "invocation_plan_ready",
    "pcm_reference_present",
    "pcm_reference_ready",
    "asr_result_present",
    "asr_result_not_attempted",
)


def validate_vosk_shadow_recognition_preflight_log(
    *,
    log_path: Path,
    require_records: bool = False,
    require_preflight_attached: bool = False,
    require_enabled: bool = False,
    require_ready: bool = False,
    require_capture_window_hook: bool = True,
    require_expected_source: bool = True,
) -> dict[str, Any]:
    issues: list[str] = []
    record_count = 0
    invalid_json_lines = 0
    invalid_record_lines = 0
    preflight_records = 0
    enabled_preflight_records = 0
    ready_preflight_records = 0
    blocked_preflight_records = 0
    ready_blocked_reason_records = 0
    expected_version_records = 0
    capture_window_hook_records = 0
    non_capture_window_hook_records = 0
    expected_source_records = 0
    expected_publish_stage_records = 0
    positive_audio_sample_count_records = 0
    positive_published_byte_count_records = 0
    unsafe_preflight_records = 0
    recognition_permission_records = 0
    ready_dependency_records = 0

    reason_counts: Counter[str] = Counter()
    version_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    publish_stage_counts: Counter[str] = Counter()
    unsafe_field_counts: Counter[str] = Counter()
    permission_field_counts: Counter[str] = Counter()

    if not log_path.exists():
        if require_records:
            issues.append("log_file_missing")
        return _result(
            accepted=not issues,
            log_path=log_path,
            records=record_count,
            invalid_json_lines=invalid_json_lines,
            invalid_record_lines=invalid_record_lines,
            preflight_records=preflight_records,
            enabled_preflight_records=enabled_preflight_records,
            ready_preflight_records=ready_preflight_records,
            blocked_preflight_records=blocked_preflight_records,
            ready_blocked_reason_records=ready_blocked_reason_records,
            expected_version_records=expected_version_records,
            capture_window_hook_records=capture_window_hook_records,
            non_capture_window_hook_records=non_capture_window_hook_records,
            expected_source_records=expected_source_records,
            expected_publish_stage_records=expected_publish_stage_records,
            positive_audio_sample_count_records=positive_audio_sample_count_records,
            positive_published_byte_count_records=positive_published_byte_count_records,
            unsafe_preflight_records=unsafe_preflight_records,
            recognition_permission_records=recognition_permission_records,
            ready_dependency_records=ready_dependency_records,
            reason_counts=reason_counts,
            version_counts=version_counts,
            source_counts=source_counts,
            publish_stage_counts=publish_stage_counts,
            unsafe_field_counts=unsafe_field_counts,
            permission_field_counts=permission_field_counts,
            issues=issues,
            require_records=require_records,
            require_preflight_attached=require_preflight_attached,
            require_enabled=require_enabled,
            require_ready=require_ready,
            require_capture_window_hook=require_capture_window_hook,
            require_expected_source=require_expected_source,
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
        preflight = _mapping(
            metadata.get(DEFAULT_RECOGNITION_PREFLIGHT_METADATA_KEY)
        )
        if not preflight:
            continue

        preflight_records += 1

        reason = str(preflight.get("reason") or "")
        version = str(preflight.get("preflight_version") or "")
        source = str(preflight.get("source") or "")
        publish_stage = str(preflight.get("publish_stage") or "")

        if reason:
            reason_counts[reason] += 1
        if version:
            version_counts[version] += 1
        if source:
            source_counts[source] += 1
        if publish_stage:
            publish_stage_counts[publish_stage] += 1

        if version == VOSK_SHADOW_RECOGNITION_PREFLIGHT_VERSION:
            expected_version_records += 1

        if preflight.get("enabled") is True:
            enabled_preflight_records += 1

        if preflight.get("preflight_ready") is True:
            ready_preflight_records += 1

        if preflight.get("recognition_blocked") is True:
            blocked_preflight_records += 1

        if reason == RECOGNITION_PREFLIGHT_READY_BLOCKED_REASON:
            ready_blocked_reason_records += 1

        if all(preflight.get(field_name) is True for field_name in READY_DEPENDENCY_FIELDS):
            ready_dependency_records += 1

        record_hook = str(record.get("hook") or "")
        preflight_hook = str(preflight.get("hook") or "")
        if record_hook == EXPECTED_HOOK and preflight_hook == EXPECTED_HOOK:
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

        if _positive_int(preflight.get("audio_sample_count")) > 0:
            positive_audio_sample_count_records += 1

        if _positive_int(preflight.get("published_byte_count")) > 0:
            positive_published_byte_count_records += 1

        validation = validate_vosk_shadow_recognition_preflight(preflight)
        for validation_issue in validation.get("issues", []):
            issues.append(f"line_{line_number}:{validation_issue}")

        unsafe_fields = [
            field_name
            for field_name in UNSAFE_PREFLIGHT_FIELDS
            if preflight.get(field_name) is not False
        ]
        if unsafe_fields:
            unsafe_preflight_records += 1
            for field_name in unsafe_fields:
                unsafe_field_counts[field_name] += 1

        permission_fields = [
            field_name
            for field_name in (
                "recognition_allowed",
                "recognition_invocation_allowed",
                "recognition_invocation_performed",
                "recognition_attempted",
                "pcm_retrieval_allowed",
                "pcm_retrieval_performed",
            )
            if preflight.get(field_name) is not False
        ]
        if permission_fields:
            recognition_permission_records += 1
            for field_name in permission_fields:
                permission_field_counts[field_name] += 1
            issues.append(f"line_{line_number}:recognition_permission_not_allowed")

    if require_records and record_count <= 0:
        issues.append("records_missing")
    if require_preflight_attached and preflight_records <= 0:
        issues.append("vosk_shadow_recognition_preflight_records_missing")
    if require_enabled and enabled_preflight_records <= 0:
        issues.append("enabled_vosk_shadow_recognition_preflight_records_missing")
    if require_ready and ready_preflight_records <= 0:
        issues.append("ready_vosk_shadow_recognition_preflight_records_missing")
    if preflight_records > 0 and expected_version_records != preflight_records:
        issues.append("unexpected_vosk_shadow_recognition_preflight_version")
    if ready_preflight_records > 0 and ready_blocked_reason_records != ready_preflight_records:
        issues.append("ready_preflight_must_use_blocked_reason")
    if ready_preflight_records > 0 and ready_dependency_records < ready_preflight_records:
        issues.append("ready_preflight_dependency_flags_missing")
    if blocked_preflight_records != preflight_records and preflight_records > 0:
        issues.append("recognition_blocked_must_be_true_for_all_preflight_records")
    if unsafe_preflight_records > 0:
        issues.append("unsafe_vosk_shadow_recognition_preflight_records_present")
    if recognition_permission_records > 0:
        issues.append("recognition_permission_records_not_allowed")

    return _result(
        accepted=not issues,
        log_path=log_path,
        records=record_count,
        invalid_json_lines=invalid_json_lines,
        invalid_record_lines=invalid_record_lines,
        preflight_records=preflight_records,
        enabled_preflight_records=enabled_preflight_records,
        ready_preflight_records=ready_preflight_records,
        blocked_preflight_records=blocked_preflight_records,
        ready_blocked_reason_records=ready_blocked_reason_records,
        expected_version_records=expected_version_records,
        capture_window_hook_records=capture_window_hook_records,
        non_capture_window_hook_records=non_capture_window_hook_records,
        expected_source_records=expected_source_records,
        expected_publish_stage_records=expected_publish_stage_records,
        positive_audio_sample_count_records=positive_audio_sample_count_records,
        positive_published_byte_count_records=positive_published_byte_count_records,
        unsafe_preflight_records=unsafe_preflight_records,
        recognition_permission_records=recognition_permission_records,
        ready_dependency_records=ready_dependency_records,
        reason_counts=reason_counts,
        version_counts=version_counts,
        source_counts=source_counts,
        publish_stage_counts=publish_stage_counts,
        unsafe_field_counts=unsafe_field_counts,
        permission_field_counts=permission_field_counts,
        issues=issues,
        require_records=require_records,
        require_preflight_attached=require_preflight_attached,
        require_enabled=require_enabled,
        require_ready=require_ready,
        require_capture_window_hook=require_capture_window_hook,
        require_expected_source=require_expected_source,
    )


def _result(
    *,
    accepted: bool,
    log_path: Path,
    records: int,
    invalid_json_lines: int,
    invalid_record_lines: int,
    preflight_records: int,
    enabled_preflight_records: int,
    ready_preflight_records: int,
    blocked_preflight_records: int,
    ready_blocked_reason_records: int,
    expected_version_records: int,
    capture_window_hook_records: int,
    non_capture_window_hook_records: int,
    expected_source_records: int,
    expected_publish_stage_records: int,
    positive_audio_sample_count_records: int,
    positive_published_byte_count_records: int,
    unsafe_preflight_records: int,
    recognition_permission_records: int,
    ready_dependency_records: int,
    reason_counts: Counter[str],
    version_counts: Counter[str],
    source_counts: Counter[str],
    publish_stage_counts: Counter[str],
    unsafe_field_counts: Counter[str],
    permission_field_counts: Counter[str],
    issues: list[str],
    require_records: bool,
    require_preflight_attached: bool,
    require_enabled: bool,
    require_ready: bool,
    require_capture_window_hook: bool,
    require_expected_source: bool,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "validator": "vosk_shadow_recognition_preflight",
        "log_path": str(log_path),
        "records": records,
        "invalid_json_lines": invalid_json_lines,
        "invalid_record_lines": invalid_record_lines,
        "preflight_records": preflight_records,
        "enabled_preflight_records": enabled_preflight_records,
        "ready_preflight_records": ready_preflight_records,
        "blocked_preflight_records": blocked_preflight_records,
        "ready_blocked_reason_records": ready_blocked_reason_records,
        "expected_version_records": expected_version_records,
        "capture_window_hook_records": capture_window_hook_records,
        "non_capture_window_hook_records": non_capture_window_hook_records,
        "expected_source_records": expected_source_records,
        "expected_publish_stage_records": expected_publish_stage_records,
        "positive_audio_sample_count_records": positive_audio_sample_count_records,
        "positive_published_byte_count_records": positive_published_byte_count_records,
        "unsafe_preflight_records": unsafe_preflight_records,
        "recognition_permission_records": recognition_permission_records,
        "ready_dependency_records": ready_dependency_records,
        "reason_counts": dict(reason_counts),
        "version_counts": dict(version_counts),
        "source_counts": dict(source_counts),
        "publish_stage_counts": dict(publish_stage_counts),
        "unsafe_field_counts": dict(unsafe_field_counts),
        "permission_field_counts": dict(permission_field_counts),
        "issues": issues,
        "required_records": require_records,
        "required_preflight_attached": require_preflight_attached,
        "required_enabled": require_enabled,
        "required_ready": require_ready,
        "required_capture_window_hook": require_capture_window_hook,
        "required_expected_source": require_expected_source,
        "recognition_permission_allowed": False,
        "pcm_retrieval_allowed": False,
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
            "Validate observe-only Voice Engine v2 Vosk shadow recognition "
            "preflight telemetry from the VAD timing bridge JSONL log."
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
        "--require-preflight-attached",
        action="store_true",
        help="Require at least one metadata.vosk_shadow_recognition_preflight record.",
    )
    parser.add_argument(
        "--require-enabled",
        action="store_true",
        help="Require at least one enabled recognition preflight record.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Require at least one ready-but-blocked recognition preflight record.",
    )
    parser.add_argument(
        "--allow-non-capture-window-hook",
        action="store_true",
        help="Allow preflight records outside capture_window_pre_transcription.",
    )
    parser.add_argument(
        "--allow-unexpected-source",
        action="store_true",
        help="Allow preflight records from non-standard audio sources.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        result = validate_vosk_shadow_recognition_preflight_log(
            log_path=args.log_path,
            require_records=args.require_records,
            require_preflight_attached=args.require_preflight_attached,
            require_enabled=args.require_enabled,
            require_ready=args.require_ready,
            require_capture_window_hook=not args.allow_non_capture_window_hook,
            require_expected_source=not args.allow_unexpected_source,
        )
    except OSError as error:
        result = {
            "accepted": False,
            "validator": "vosk_shadow_recognition_preflight",
            "error": str(error),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if bool(result.get("accepted", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())