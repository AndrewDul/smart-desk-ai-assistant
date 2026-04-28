from __future__ import annotations

import json
from pathlib import Path

from scripts.check_voice_engine_v2_vosk_fixture_matrix_quality import (
    main,
    run_vosk_fixture_quality_gate,
)


def _write_matrix_summary(
    path: Path,
    *,
    accepted: bool = True,
    failed_items: int = 0,
    matched_reports: int = 6,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accepted": accepted,
        "total_items": 6,
        "accepted_items": 6 - failed_items,
        "failed_items": failed_items,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "summary": {
            "accepted": accepted,
            "total_reports": 6,
            "accepted_reports": matched_reports,
            "matched_reports": matched_reports,
            "language_match_records": matched_reports,
            "language_mismatch_records": 0,
            "unsafe_flag_records": 0,
            "language_counts": {"en": 3, "pl": 3},
            "intent_counts": {
                "system.current_time": 2,
                "visual_shell.show_desktop": 2,
                "visual_shell.show_shell": 2,
            },
            "elapsed_ms": {
                "avg": 1100.0,
                "min": 900.0,
                "max": 1300.0,
            },
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_run_vosk_fixture_quality_gate_writes_output(tmp_path: Path) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    output_path = tmp_path / "quality_gate.json"
    _write_matrix_summary(summary_path)

    result = run_vosk_fixture_quality_gate(
        summary_path=summary_path,
        output_path=output_path,
        max_elapsed_ms=1500.0,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert result["action"] == "check_vosk_fixture_matrix_quality"
    assert result["observed"]["matched_reports"] == 6
    assert report["accepted"] is True
    assert report["runtime_integration"] is False
    assert report["command_execution_enabled"] is False
    assert report["microphone_stream_started"] is False


def test_cli_returns_zero_for_valid_quality_gate(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    output_path = tmp_path / "quality_gate.json"
    _write_matrix_summary(summary_path)

    exit_code = main(
        [
            "--summary-path",
            str(summary_path),
            "--output-path",
            str(output_path),
            "--max-elapsed-ms",
            "1500",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["output_path"] == str(output_path)
    assert output_path.exists()


def test_cli_returns_one_for_missing_summary(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "--summary-path",
            str(tmp_path / "missing.json"),
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["output_path"] == ""
    assert "matrix_summary_path_missing" in payload["issues"]


def test_cli_returns_one_for_failed_threshold(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(summary_path, accepted=False, failed_items=1)

    exit_code = main(
        [
            "--summary-path",
            str(summary_path),
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "matrix_not_accepted" in payload["issues"]
    assert "failed_items_above_maximum:failed_items:1>0" in payload["issues"]


def test_cli_accepts_custom_thresholds(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "matrix_summary.json"
    _write_matrix_summary(summary_path, matched_reports=5)

    exit_code = main(
        [
            "--summary-path",
            str(summary_path),
            "--min-matched-reports",
            "5",
            "--min-language-match-records",
            "5",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["thresholds"]["min_matched_reports"] == 5
    assert payload["thresholds"]["min_language_match_records"] == 5
    