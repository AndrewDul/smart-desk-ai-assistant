from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.voice_engine_v2.vosk_fixture_quality_gate import (
    check_vosk_fixture_matrix_quality,
)


def _write_matrix_summary(
    path: Path,
    *,
    accepted: bool = True,
    summary_accepted: bool = True,
    total_items: int = 6,
    accepted_items: int = 6,
    failed_items: int = 0,
    total_reports: int = 6,
    matched_reports: int = 6,
    language_match_records: int = 6,
    language_mismatch_records: int = 0,
    unsafe_flag_records: int = 0,
    max_elapsed_ms: float = 1300.0,
    language_counts: dict[str, int] | None = None,
    unsafe_top_level: bool = False,
    unsafe_summary: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accepted": accepted,
        "total_items": total_items,
        "accepted_items": accepted_items,
        "failed_items": failed_items,
        "runtime_integration": unsafe_top_level,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "summary": {
            "accepted": summary_accepted,
            "total_reports": total_reports,
            "accepted_reports": matched_reports,
            "matched_reports": matched_reports,
            "language_match_records": language_match_records,
            "language_mismatch_records": language_mismatch_records,
            "unsafe_flag_records": unsafe_flag_records,
            "language_counts": language_counts or {"en": 3, "pl": 3},
            "intent_counts": {
                "system.current_time": 2,
                "visual_shell.show_desktop": 2,
                "visual_shell.show_shell": 2,
            },
            "elapsed_ms": {
                "avg": 1100.0,
                "min": 900.0,
                "max": max_elapsed_ms,
            },
            "runtime_integration": False,
            "command_execution_enabled": unsafe_summary,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_quality_gate_accepts_valid_matrix_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(summary_path)

    result = check_vosk_fixture_matrix_quality(
        summary_path=summary_path,
        max_elapsed_ms=1500.0,
    )

    assert result["accepted"] is True
    assert result["issues"] == []
    assert result["observed"]["total_items"] == 6
    assert result["observed"]["matched_reports"] == 6
    assert result["observed"]["language_counts"] == {"en": 3, "pl": 3}
    assert result["runtime_integration"] is False
    assert result["command_execution_enabled"] is False
    assert result["microphone_stream_started"] is False


def test_quality_gate_rejects_missing_summary_file(tmp_path: Path) -> None:
    result = check_vosk_fixture_matrix_quality(
        summary_path=tmp_path / "missing.json",
    )

    assert result["accepted"] is False
    assert "matrix_summary_path_missing" in result["issues"]


def test_quality_gate_rejects_failed_items(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(
        summary_path,
        accepted=False,
        failed_items=1,
        accepted_items=5,
    )

    result = check_vosk_fixture_matrix_quality(summary_path=summary_path)

    assert result["accepted"] is False
    assert "matrix_not_accepted" in result["issues"]
    assert "accepted_items_below_minimum:accepted_items:5<6" in result["issues"]
    assert "failed_items_above_maximum:failed_items:1>0" in result["issues"]


def test_quality_gate_rejects_language_mismatch_records(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(
        summary_path,
        summary_accepted=False,
        language_match_records=5,
        language_mismatch_records=1,
    )

    result = check_vosk_fixture_matrix_quality(summary_path=summary_path)

    assert result["accepted"] is False
    assert "summary_not_accepted" in result["issues"]
    assert (
        "language_match_records_below_minimum:language_match_records:5<6"
        in result["issues"]
    )
    assert (
        "language_mismatch_records_above_maximum:language_mismatch_records:1>0"
        in result["issues"]
    )


def test_quality_gate_rejects_unsafe_flags(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(
        summary_path,
        unsafe_top_level=True,
        unsafe_summary=True,
    )

    result = check_vosk_fixture_matrix_quality(summary_path=summary_path)

    assert result["accepted"] is False
    assert "unsafe_flag:top_level:runtime_integration" in result["issues"]
    assert "unsafe_flag:summary:command_execution_enabled" in result["issues"]


def test_quality_gate_rejects_missing_required_language(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(summary_path, language_counts={"en": 6})

    result = check_vosk_fixture_matrix_quality(
        summary_path=summary_path,
        require_languages=("en", "pl"),
    )

    assert result["accepted"] is False
    assert "required_language_missing:pl" in result["issues"]


def test_quality_gate_rejects_elapsed_threshold_failure(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(summary_path, max_elapsed_ms=1800.0)

    result = check_vosk_fixture_matrix_quality(
        summary_path=summary_path,
        max_elapsed_ms=1500.0,
    )

    assert result["accepted"] is False
    assert "max_elapsed_ms_above_threshold:max:1800.0>1500.0" in result["issues"]


def test_quality_gate_rejects_invalid_json(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    summary_path.write_text("{", encoding="utf-8")

    result = check_vosk_fixture_matrix_quality(summary_path=summary_path)

    assert result["accepted"] is False
    assert any(
        issue.startswith("matrix_summary_invalid_json:")
        for issue in result["issues"]
    )