from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VOSK_FIXTURE_REPORT_SUMMARY_STAGE = "vosk_fixture_report_summary"
VOSK_FIXTURE_REPORT_SUMMARY_VERSION = "stage_24af_v1"

DEFAULT_REPORT_PATTERN = "*.json"

TOP_LEVEL_FALSE_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "live_command_recognition_enabled",
)

RESULT_FALSE_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "live_command_recognition_enabled",
    "raw_pcm_included",
    "action_executed",
    "full_stt_prevented",
    "runtime_takeover",
)

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "pl")


def summarize_vosk_fixture_reports(
    *,
    report_dir: Path,
    report_pattern: str = DEFAULT_REPORT_PATTERN,
    require_reports: bool = False,
    require_languages: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Summarize offline Vosk fixture recognition probe reports.

    This function only reads local JSON reports. It never starts microphone
    capture, never executes commands, and never integrates with live runtime.
    """

    report_dir = Path(report_dir)
    report_paths = _discover_report_paths(report_dir, report_pattern)

    records: list[dict[str, Any]] = []
    issues: list[str] = []

    if require_reports and not report_paths:
        issues.append("vosk_fixture_reports_missing")

    for report_path in report_paths:
        record, record_issues = _load_report_record(report_path)
        records.append(record)
        issues.extend(record_issues)

    language_counts = _count_by_key(records, "command_language")
    expected_language_counts = _count_by_key(records, "expected_language")
    intent_counts = _count_by_key(records, "command_intent_key")

    for language in require_languages:
        if language not in SUPPORTED_LANGUAGES:
            issues.append(f"unsupported_required_language:{language}")
        elif language_counts.get(language, 0) <= 0:
            issues.append(f"required_language_missing:{language}")

    elapsed_values = [
        float(record["elapsed_ms"])
        for record in records
        if isinstance(record.get("elapsed_ms"), int | float)
    ]

    total_reports = len(records)
    accepted_reports = sum(1 for record in records if record["accepted"] is True)
    rejected_reports = total_reports - accepted_reports
    matched_reports = sum(1 for record in records if record["command_matched"] is True)
    unmatched_reports = total_reports - matched_reports
    attempted_reports = sum(
        1 for record in records if record["fixture_recognition_attempted"] is True
    )
    language_match_records = sum(1 for record in records if record["language_match"] is True)
    language_mismatch_records = sum(
        1 for record in records if record["language_match"] is False
    )
    unsafe_flag_records = sum(1 for record in records if record["unsafe_flags"])

    summary = {
        "accepted": not issues,
        "summary_stage": VOSK_FIXTURE_REPORT_SUMMARY_STAGE,
        "summary_version": VOSK_FIXTURE_REPORT_SUMMARY_VERSION,
        "report_dir": str(report_dir),
        "report_pattern": report_pattern,
        "report_files": [str(path) for path in report_paths],
        "total_reports": total_reports,
        "accepted_reports": accepted_reports,
        "rejected_reports": rejected_reports,
        "attempted_reports": attempted_reports,
        "matched_reports": matched_reports,
        "unmatched_reports": unmatched_reports,
        "language_match_records": language_match_records,
        "language_mismatch_records": language_mismatch_records,
        "unsafe_flag_records": unsafe_flag_records,
        "language_counts": language_counts,
        "expected_language_counts": expected_language_counts,
        "intent_counts": intent_counts,
        "elapsed_ms": {
            "avg": _round_or_none(_average(elapsed_values)),
            "min": _round_or_none(min(elapsed_values) if elapsed_values else None),
            "max": _round_or_none(max(elapsed_values) if elapsed_values else None),
        },
        "per_language": _summarize_by_language(records),
        "per_intent": _summarize_by_intent(records),
        "issues": issues,
        "records": records,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }
    return summary


def _discover_report_paths(report_dir: Path, report_pattern: str) -> list[Path]:
    if not report_dir.exists() or not report_dir.is_dir():
        return []
    return sorted(path for path in report_dir.glob(report_pattern) if path.is_file())


def _load_report_record(report_path: Path) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    report_name = report_path.name

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return (
            _invalid_record(
                report_path=report_path,
                reason="invalid_json",
                error=f"JSONDecodeError:{error}",
            ),
            [f"invalid_report_json:{report_name}"],
        )

    if not isinstance(payload, dict):
        return (
            _invalid_record(
                report_path=report_path,
                reason="invalid_payload",
                error="payload_not_object",
            ),
            [f"invalid_report_payload:{report_name}"],
        )

    result = payload.get("result", {})
    if not isinstance(result, dict):
        result = {}
        issues.append(f"report_result_missing:{report_name}")

    accepted = payload.get("accepted") is True
    command_matched = result.get("command_matched") is True
    fixture_recognition_attempted = result.get("fixture_recognition_attempted") is True

    expected_language = str(result.get("expected_language") or "all")
    command_language = str(result.get("command_language") or "unknown")
    command_intent_key = _optional_str(result.get("command_intent_key"))
    elapsed_ms = _optional_number(result.get("elapsed_ms"))
    transcript = str(result.get("transcript") or "")
    normalized_text = str(result.get("normalized_text") or "")

    language_match = _language_match(
        expected_language=expected_language,
        command_language=command_language,
    )

    unsafe_flags: list[str] = []
    unsafe_flags.extend(
        _unsafe_fields(
            payload=payload,
            fields=TOP_LEVEL_FALSE_FIELDS,
            location="top_level",
        )
    )
    unsafe_flags.extend(
        _unsafe_fields(
            payload=result,
            fields=RESULT_FALSE_FIELDS,
            location="result",
        )
    )

    if not accepted:
        issues.append(f"report_not_accepted:{report_name}")
    if not command_matched:
        issues.append(f"command_match_missing:{report_name}")
    if language_match is False:
        issues.append(f"command_language_mismatch:{report_name}")
    for unsafe_flag in unsafe_flags:
        issues.append(f"unsafe_flag:{report_name}:{unsafe_flag}")

    return (
        {
            "report_file": str(report_path),
            "accepted": accepted,
            "report_issues": list(payload.get("issues") or ()),
            "fixture_recognition_attempted": fixture_recognition_attempted,
            "command_matched": command_matched,
            "expected_language": expected_language,
            "command_language": command_language,
            "language_match": language_match,
            "command_intent_key": command_intent_key,
            "command_matched_phrase": _optional_str(result.get("command_matched_phrase")),
            "command_status": str(result.get("command_status") or "unknown"),
            "transcript": transcript,
            "normalized_text": normalized_text,
            "elapsed_ms": elapsed_ms,
            "vocabulary_size": _optional_number(result.get("vocabulary_size")),
            "unsafe_flags": unsafe_flags,
        },
        issues,
    )


def _invalid_record(
    *,
    report_path: Path,
    reason: str,
    error: str,
) -> dict[str, Any]:
    return {
        "report_file": str(report_path),
        "accepted": False,
        "report_issues": [reason],
        "fixture_recognition_attempted": False,
        "command_matched": False,
        "expected_language": "unknown",
        "command_language": "unknown",
        "language_match": None,
        "command_intent_key": None,
        "command_matched_phrase": None,
        "command_status": "invalid",
        "transcript": "",
        "normalized_text": "",
        "elapsed_ms": None,
        "vocabulary_size": None,
        "unsafe_flags": [],
        "error": error,
    }


def _language_match(
    *,
    expected_language: str,
    command_language: str,
) -> bool | None:
    if expected_language in SUPPORTED_LANGUAGES:
        return command_language == expected_language
    return None


def _unsafe_fields(
    *,
    payload: dict[str, Any],
    fields: tuple[str, ...],
    location: str,
) -> list[str]:
    unsafe: list[str] = []
    for field in fields:
        if payload.get(field) is not False:
            unsafe.append(f"{location}:{field}")
    return unsafe


def _count_by_key(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        value_key = str(value)
        counts[value_key] = counts.get(value_key, 0) + 1
    return dict(sorted(counts.items()))


def _summarize_by_language(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        language = str(record.get("command_language") or "unknown")
        grouped.setdefault(language, []).append(record)

    return {
        language: _summarize_records(language_records)
        for language, language_records in sorted(grouped.items())
    }


def _summarize_by_intent(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        intent = str(record.get("command_intent_key") or "unknown")
        grouped.setdefault(intent, []).append(record)

    return {
        intent: _summarize_records(intent_records)
        for intent, intent_records in sorted(grouped.items())
    }


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed_values = [
        float(record["elapsed_ms"])
        for record in records
        if isinstance(record.get("elapsed_ms"), int | float)
    ]

    return {
        "reports": len(records),
        "accepted": sum(1 for record in records if record["accepted"] is True),
        "matched": sum(1 for record in records if record["command_matched"] is True),
        "language_matches": sum(
            1 for record in records if record["language_match"] is True
        ),
        "unsafe_flag_records": sum(1 for record in records if record["unsafe_flags"]),
        "avg_elapsed_ms": _round_or_none(_average(elapsed_values)),
        "max_elapsed_ms": _round_or_none(max(elapsed_values) if elapsed_values else None),
    }


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_number(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


__all__ = [
    "DEFAULT_REPORT_PATTERN",
    "RESULT_FALSE_FIELDS",
    "SUPPORTED_LANGUAGES",
    "TOP_LEVEL_FALSE_FIELDS",
    "VOSK_FIXTURE_REPORT_SUMMARY_STAGE",
    "VOSK_FIXTURE_REPORT_SUMMARY_VERSION",
    "summarize_vosk_fixture_reports",
]