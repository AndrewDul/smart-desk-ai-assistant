from __future__ import annotations

import json
from pathlib import Path

from scripts.summarize_voice_engine_v2_vosk_fixture_reports import (
    main,
    run_vosk_fixture_report_summary,
)


def _write_probe_report(
    path: Path,
    *,
    expected_language: str = "en",
    command_language: str = "en",
    accepted: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accepted": accepted,
        "issues": [] if accepted else ["command_match_missing"],
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "result": {
            "fixture_recognition_attempted": True,
            "command_matched": accepted,
            "expected_language": expected_language,
            "command_language": command_language,
            "command_intent_key": "system.current_time",
            "command_matched_phrase": "what time is it" if accepted else None,
            "command_status": "matched" if accepted else "no_match",
            "transcript": "what time is it" if accepted else "",
            "normalized_text": "what time is it" if accepted else "",
            "elapsed_ms": 123.0,
            "vocabulary_size": 25,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "live_command_recognition_enabled": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_run_vosk_fixture_report_summary_writes_output(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    output_path = tmp_path / "summary.json"
    _write_probe_report(report_dir / "en_what_time_is_it.json")

    result = run_vosk_fixture_report_summary(
        report_dir=report_dir,
        output_path=output_path,
        require_reports=True,
        require_languages=("en",),
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert result["total_reports"] == 1
    assert result["matched_reports"] == 1
    assert result["language_counts"] == {"en": 1}
    assert report["accepted"] is True
    assert report["action"] == "summarize_vosk_fixture_reports"
    assert report["runtime_integration"] is False
    assert report["command_execution_enabled"] is False
    assert report["microphone_stream_started"] is False


def test_cli_returns_zero_for_valid_reports(tmp_path: Path, capsys) -> None:
    report_dir = tmp_path / "reports"
    output_path = tmp_path / "summary.json"
    _write_probe_report(report_dir / "en_what_time_is_it.json")

    exit_code = main(
        [
            "--report-dir",
            str(report_dir),
            "--output-path",
            str(output_path),
            "--require-reports",
            "--require-language",
            "en",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["total_reports"] == 1
    assert output_path.exists()


def test_cli_returns_one_when_reports_are_missing(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "--report-dir",
            str(tmp_path / "missing"),
            "--require-reports",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["output_path"] == ""
    assert "vosk_fixture_reports_missing" in payload["issues"]


def test_cli_returns_one_when_required_language_is_missing(
    tmp_path: Path,
    capsys,
) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(report_dir / "en_what_time_is_it.json")

    exit_code = main(
        [
            "--report-dir",
            str(report_dir),
            "--require-reports",
            "--require-language",
            "en",
            "--require-language",
            "pl",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "required_language_missing:pl" in payload["issues"]


def test_cli_returns_one_for_rejected_probe_report(tmp_path: Path, capsys) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(
        report_dir / "en_what_time_is_it.json",
        accepted=False,
    )

    exit_code = main(
        [
            "--report-dir",
            str(report_dir),
            "--require-reports",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "report_not_accepted:en_what_time_is_it.json" in payload["issues"]
    assert "command_match_missing:en_what_time_is_it.json" in payload["issues"]