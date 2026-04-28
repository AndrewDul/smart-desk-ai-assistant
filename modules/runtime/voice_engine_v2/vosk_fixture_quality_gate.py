from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VOSK_FIXTURE_QUALITY_GATE_STAGE = "vosk_fixture_quality_gate"
VOSK_FIXTURE_QUALITY_GATE_VERSION = "stage_24ah_v1"

DEFAULT_MATRIX_SUMMARY_PATH = Path(
    "var/data/stage24ag_vosk_fixture_matrix_summary.json"
)

TOP_LEVEL_FALSE_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "live_command_recognition_enabled",
)

SUMMARY_FALSE_FIELDS: tuple[str, ...] = (
    "runtime_integration",
    "command_execution_enabled",
    "faster_whisper_bypass_enabled",
    "microphone_stream_started",
    "live_command_recognition_enabled",
)

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "pl")


def check_vosk_fixture_matrix_quality(
    *,
    summary_path: Path = DEFAULT_MATRIX_SUMMARY_PATH,
    min_total_items: int = 6,
    min_accepted_items: int = 6,
    max_failed_items: int = 0,
    min_total_reports: int = 6,
    min_matched_reports: int = 6,
    min_language_match_records: int = 6,
    max_language_mismatch_records: int = 0,
    max_unsafe_flag_records: int = 0,
    max_elapsed_ms: float | None = None,
    require_languages: tuple[str, ...] = ("en", "pl"),
) -> dict[str, Any]:
    """Validate the offline Vosk fixture matrix summary against quality gates.

    This function only reads a local JSON summary. It never starts microphone
    capture, never executes commands, and never integrates with live runtime.
    """

    summary_path = Path(summary_path)
    issues: list[str] = []

    payload, load_issues = _load_summary_payload(summary_path)
    issues.extend(load_issues)

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
        issues.append("matrix_summary_missing")

    if payload:
        _check_bool_true(
            issues=issues,
            payload=payload,
            field="accepted",
            issue="matrix_not_accepted",
        )
        _check_bool_true(
            issues=issues,
            payload=summary,
            field="accepted",
            issue="summary_not_accepted",
        )

        _check_min_number(
            issues=issues,
            payload=payload,
            field="total_items",
            minimum=min_total_items,
            issue="total_items_below_minimum",
        )
        _check_min_number(
            issues=issues,
            payload=payload,
            field="accepted_items",
            minimum=min_accepted_items,
            issue="accepted_items_below_minimum",
        )
        _check_max_number(
            issues=issues,
            payload=payload,
            field="failed_items",
            maximum=max_failed_items,
            issue="failed_items_above_maximum",
        )

        _check_min_number(
            issues=issues,
            payload=summary,
            field="total_reports",
            minimum=min_total_reports,
            issue="total_reports_below_minimum",
        )
        _check_min_number(
            issues=issues,
            payload=summary,
            field="matched_reports",
            minimum=min_matched_reports,
            issue="matched_reports_below_minimum",
        )
        _check_min_number(
            issues=issues,
            payload=summary,
            field="language_match_records",
            minimum=min_language_match_records,
            issue="language_match_records_below_minimum",
        )
        _check_max_number(
            issues=issues,
            payload=summary,
            field="language_mismatch_records",
            maximum=max_language_mismatch_records,
            issue="language_mismatch_records_above_maximum",
        )
        _check_max_number(
            issues=issues,
            payload=summary,
            field="unsafe_flag_records",
            maximum=max_unsafe_flag_records,
            issue="unsafe_flag_records_above_maximum",
        )

        if max_elapsed_ms is not None:
            elapsed = summary.get("elapsed_ms", {})
            if not isinstance(elapsed, dict):
                issues.append("elapsed_ms_summary_missing")
            else:
                _check_max_number(
                    issues=issues,
                    payload=elapsed,
                    field="max",
                    maximum=max_elapsed_ms,
                    issue="max_elapsed_ms_above_threshold",
                )

        _check_required_languages(
            issues=issues,
            summary=summary,
            require_languages=require_languages,
        )
        _check_false_fields(
            issues=issues,
            payload=payload,
            fields=TOP_LEVEL_FALSE_FIELDS,
            prefix="top_level",
        )
        _check_false_fields(
            issues=issues,
            payload=summary,
            fields=SUMMARY_FALSE_FIELDS,
            prefix="summary",
        )

    return {
        "accepted": not issues,
        "quality_gate_stage": VOSK_FIXTURE_QUALITY_GATE_STAGE,
        "quality_gate_version": VOSK_FIXTURE_QUALITY_GATE_VERSION,
        "summary_path": str(summary_path),
        "thresholds": {
            "min_total_items": min_total_items,
            "min_accepted_items": min_accepted_items,
            "max_failed_items": max_failed_items,
            "min_total_reports": min_total_reports,
            "min_matched_reports": min_matched_reports,
            "min_language_match_records": min_language_match_records,
            "max_language_mismatch_records": max_language_mismatch_records,
            "max_unsafe_flag_records": max_unsafe_flag_records,
            "max_elapsed_ms": max_elapsed_ms,
            "require_languages": list(require_languages),
        },
        "observed": _observed_values(payload=payload, summary=summary),
        "issues": issues,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }


def _load_summary_payload(summary_path: Path) -> tuple[dict[str, Any], list[str]]:
    if not summary_path.exists():
        return {}, ["matrix_summary_path_missing"]

    if not summary_path.is_file():
        return {}, ["matrix_summary_path_not_file"]

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {}, [f"matrix_summary_invalid_json:{error}"]

    if not isinstance(payload, dict):
        return {}, ["matrix_summary_payload_not_object"]

    return payload, []


def _observed_values(
    *,
    payload: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    elapsed = summary.get("elapsed_ms", {})
    if not isinstance(elapsed, dict):
        elapsed = {}

    return {
        "matrix_accepted": payload.get("accepted"),
        "total_items": payload.get("total_items"),
        "accepted_items": payload.get("accepted_items"),
        "failed_items": payload.get("failed_items"),
        "summary_accepted": summary.get("accepted"),
        "total_reports": summary.get("total_reports"),
        "accepted_reports": summary.get("accepted_reports"),
        "matched_reports": summary.get("matched_reports"),
        "language_match_records": summary.get("language_match_records"),
        "language_mismatch_records": summary.get("language_mismatch_records"),
        "unsafe_flag_records": summary.get("unsafe_flag_records"),
        "language_counts": summary.get("language_counts", {}),
        "intent_counts": summary.get("intent_counts", {}),
        "elapsed_ms": {
            "avg": elapsed.get("avg"),
            "min": elapsed.get("min"),
            "max": elapsed.get("max"),
        },
    }


def _check_bool_true(
    *,
    issues: list[str],
    payload: dict[str, Any],
    field: str,
    issue: str,
) -> None:
    if payload.get(field) is not True:
        issues.append(issue)


def _check_min_number(
    *,
    issues: list[str],
    payload: dict[str, Any],
    field: str,
    minimum: int | float,
    issue: str,
) -> None:
    value = payload.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool):
        issues.append(f"{issue}:{field}_missing_or_invalid")
        return
    if value < minimum:
        issues.append(f"{issue}:{field}:{value}<{minimum}")


def _check_max_number(
    *,
    issues: list[str],
    payload: dict[str, Any],
    field: str,
    maximum: int | float,
    issue: str,
) -> None:
    value = payload.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool):
        issues.append(f"{issue}:{field}_missing_or_invalid")
        return
    if value > maximum:
        issues.append(f"{issue}:{field}:{value}>{maximum}")


def _check_required_languages(
    *,
    issues: list[str],
    summary: dict[str, Any],
    require_languages: tuple[str, ...],
) -> None:
    language_counts = summary.get("language_counts", {})
    if not isinstance(language_counts, dict):
        issues.append("language_counts_missing")
        return

    for language in require_languages:
        if language not in SUPPORTED_LANGUAGES:
            issues.append(f"unsupported_required_language:{language}")
            continue
        count = language_counts.get(language, 0)
        if not isinstance(count, int) or count <= 0:
            issues.append(f"required_language_missing:{language}")


def _check_false_fields(
    *,
    issues: list[str],
    payload: dict[str, Any],
    fields: tuple[str, ...],
    prefix: str,
) -> None:
    for field in fields:
        if payload.get(field) is not False:
            issues.append(f"unsafe_flag:{prefix}:{field}")


__all__ = [
    "DEFAULT_MATRIX_SUMMARY_PATH",
    "SUMMARY_FALSE_FIELDS",
    "SUPPORTED_LANGUAGES",
    "TOP_LEVEL_FALSE_FIELDS",
    "VOSK_FIXTURE_QUALITY_GATE_STAGE",
    "VOSK_FIXTURE_QUALITY_GATE_VERSION",
    "check_vosk_fixture_matrix_quality",
]