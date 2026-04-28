from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.voice_engine_v2.vosk_fixture_report_summary import (
    summarize_vosk_fixture_reports,
)


def _write_probe_report(
    path: Path,
    *,
    accepted: bool = True,
    expected_language: str = "en",
    command_language: str = "en",
    command_matched: bool = True,
    command_intent_key: str = "system.current_time",
    transcript: str = "what time is it",
    elapsed_ms: float = 100.0,
    unsafe_top_level: bool = False,
    unsafe_result: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accepted": accepted,
        "issues": [] if accepted else ["command_match_missing"],
        "runtime_integration": unsafe_top_level,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "result": {
            "fixture_recognition_attempted": True,
            "command_matched": command_matched,
            "expected_language": expected_language,
            "command_language": command_language,
            "command_intent_key": command_intent_key,
            "command_matched_phrase": transcript if command_matched else None,
            "command_status": "matched" if command_matched else "no_match",
            "transcript": transcript,
            "normalized_text": transcript,
            "elapsed_ms": elapsed_ms,
            "vocabulary_size": 25 if expected_language == "en" else 34,
            "runtime_integration": False,
            "command_execution_enabled": unsafe_result,
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


def test_summary_accepts_complete_scoped_probe_reports(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(
        report_dir / "en_show_desktop.json",
        expected_language="en",
        command_language="en",
        command_intent_key="visual_shell.show_desktop",
        transcript="show desktop",
        elapsed_ms=100.0,
    )
    _write_probe_report(
        report_dir / "en_what_time_is_it.json",
        expected_language="en",
        command_language="en",
        command_intent_key="system.current_time",
        transcript="what time is it",
        elapsed_ms=200.0,
    )
    _write_probe_report(
        report_dir / "pl_ktora_godzina.json",
        expected_language="pl",
        command_language="pl",
        command_intent_key="system.current_time",
        transcript="która godzina",
        elapsed_ms=300.0,
    )

    summary = summarize_vosk_fixture_reports(
        report_dir=report_dir,
        require_reports=True,
        require_languages=("en", "pl"),
    )

    assert summary["accepted"] is True
    assert summary["total_reports"] == 3
    assert summary["accepted_reports"] == 3
    assert summary["matched_reports"] == 3
    assert summary["language_match_records"] == 3
    assert summary["unsafe_flag_records"] == 0
    assert summary["language_counts"] == {"en": 2, "pl": 1}
    assert summary["expected_language_counts"] == {"en": 2, "pl": 1}
    assert summary["intent_counts"]["system.current_time"] == 2
    assert summary["elapsed_ms"]["avg"] == 200.0
    assert summary["elapsed_ms"]["max"] == 300.0
    assert summary["per_language"]["en"]["reports"] == 2
    assert summary["per_language"]["pl"]["reports"] == 1
    assert summary["runtime_integration"] is False
    assert summary["command_execution_enabled"] is False
    assert summary["microphone_stream_started"] is False


def test_summary_rejects_missing_required_language(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(report_dir / "en_show_desktop.json")

    summary = summarize_vosk_fixture_reports(
        report_dir=report_dir,
        require_reports=True,
        require_languages=("en", "pl"),
    )

    assert summary["accepted"] is False
    assert "required_language_missing:pl" in summary["issues"]


def test_summary_rejects_language_mismatch(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(
        report_dir / "wrong_language.json",
        expected_language="en",
        command_language="pl",
        command_intent_key="visual_shell.show_desktop",
        transcript="pokaż pulpit",
    )

    summary = summarize_vosk_fixture_reports(report_dir=report_dir)

    assert summary["accepted"] is False
    assert summary["language_mismatch_records"] == 1
    assert "command_language_mismatch:wrong_language.json" in summary["issues"]


def test_summary_rejects_unsafe_flags(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write_probe_report(
        report_dir / "unsafe.json",
        unsafe_top_level=True,
        unsafe_result=True,
    )

    summary = summarize_vosk_fixture_reports(report_dir=report_dir)

    assert summary["accepted"] is False
    assert summary["unsafe_flag_records"] == 1
    assert (
        "unsafe_flag:unsafe.json:top_level:runtime_integration"
        in summary["issues"]
    )
    assert (
        "unsafe_flag:unsafe.json:result:command_execution_enabled"
        in summary["issues"]
    )


def test_summary_rejects_invalid_json(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True)
    (report_dir / "broken.json").write_text("{", encoding="utf-8")

    summary = summarize_vosk_fixture_reports(report_dir=report_dir)

    assert summary["accepted"] is False
    assert summary["total_reports"] == 1
    assert "invalid_report_json:broken.json" in summary["issues"]


def test_summary_can_require_reports(tmp_path: Path) -> None:
    summary = summarize_vosk_fixture_reports(
        report_dir=tmp_path / "missing",
        require_reports=True,
    )

    assert summary["accepted"] is False
    assert summary["total_reports"] == 0
    assert "vosk_fixture_reports_missing" in summary["issues"]