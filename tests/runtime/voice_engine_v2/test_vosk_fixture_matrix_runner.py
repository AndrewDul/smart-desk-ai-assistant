from __future__ import annotations

import wave
from pathlib import Path

from modules.runtime.voice_engine_v2.vosk_fixture_matrix_runner import (
    VoskFixtureMatrixItem,
    run_vosk_fixture_matrix,
)


def _create_minimal_vosk_model(model_path: Path) -> None:
    (model_path / "am").mkdir(parents=True, exist_ok=True)
    (model_path / "conf").mkdir(parents=True, exist_ok=True)
    (model_path / "am" / "final.mdl").write_text("fake model", encoding="utf-8")
    (model_path / "conf" / "model.conf").write_text("fake config", encoding="utf-8")


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)


def _matrix_items(tmp_path: Path) -> tuple[VoskFixtureMatrixItem, ...]:
    en_model = tmp_path / "models" / "vosk-model-small-en-us-0.15"
    pl_model = tmp_path / "models" / "vosk-model-small-pl-0.22"
    en_wav = tmp_path / "fixtures" / "en_show_desktop.wav"
    pl_wav = tmp_path / "fixtures" / "pl_pokaz_pulpit.wav"
    report_dir = tmp_path / "reports"

    _create_minimal_vosk_model(en_model)
    _create_minimal_vosk_model(pl_model)
    _write_wav(en_wav)
    _write_wav(pl_wav)

    return (
        VoskFixtureMatrixItem(
            fixture_id="en_show_desktop",
            language="en",
            model_path=en_model,
            wav_path=en_wav,
            output_path=report_dir / "en_show_desktop.json",
        ),
        VoskFixtureMatrixItem(
            fixture_id="pl_pokaz_pulpit",
            language="pl",
            model_path=pl_model,
            wav_path=pl_wav,
            output_path=report_dir / "pl_pokaz_pulpit.json",
        ),
    )


def test_matrix_runner_accepts_scoped_fixture_reports(tmp_path: Path) -> None:
    items = _matrix_items(tmp_path)
    result = run_vosk_fixture_matrix(
        report_dir=tmp_path / "reports",
        summary_output_path=tmp_path / "matrix_summary.json",
        items=items,
        require_languages=("en", "pl"),
        transcript_provider_by_fixture_id={
            "en_show_desktop": lambda pcm, sample_rate, vocabulary: "show desktop",
            "pl_pokaz_pulpit": lambda pcm, sample_rate, vocabulary: "pokaż pulpit",
        },
    )

    assert result["accepted"] is True
    assert result["total_items"] == 2
    assert result["accepted_items"] == 2
    assert result["failed_items"] == 0
    assert result["summary"]["accepted"] is True
    assert result["summary"]["total_reports"] == 2
    assert result["summary"]["matched_reports"] == 2
    assert result["summary"]["language_match_records"] == 2
    assert result["summary"]["unsafe_flag_records"] == 0
    assert result["runtime_integration"] is False
    assert result["command_execution_enabled"] is False
    assert result["microphone_stream_started"] is False
    assert (tmp_path / "reports" / "en_show_desktop.json").exists()
    assert (tmp_path / "reports" / "pl_pokaz_pulpit.json").exists()
    assert (tmp_path / "matrix_summary.json").exists()


def test_matrix_runner_rejects_language_mismatch(tmp_path: Path) -> None:
    items = _matrix_items(tmp_path)
    result = run_vosk_fixture_matrix(
        report_dir=tmp_path / "reports",
        summary_output_path=tmp_path / "matrix_summary.json",
        items=items[:1],
        require_languages=("en",),
        transcript_provider_by_fixture_id={
            "en_show_desktop": lambda pcm, sample_rate, vocabulary: "pokaż pulpit",
        },
    )

    assert result["accepted"] is False
    assert result["accepted_items"] == 0
    assert result["failed_items"] == 1
    assert "matrix_item_failed:en_show_desktop" in result["issues"]
    assert (
        "en_show_desktop:command_language_mismatch"
        in result["issues"]
    )
    assert result["summary"]["accepted"] is False
    assert result["summary"]["language_mismatch_records"] == 1


def test_matrix_runner_rejects_missing_required_language(tmp_path: Path) -> None:
    items = _matrix_items(tmp_path)
    result = run_vosk_fixture_matrix(
        report_dir=tmp_path / "reports",
        summary_output_path=tmp_path / "matrix_summary.json",
        items=items[:1],
        require_languages=("en", "pl"),
        transcript_provider_by_fixture_id={
            "en_show_desktop": lambda pcm, sample_rate, vocabulary: "show desktop",
        },
    )

    assert result["accepted"] is False
    assert result["accepted_items"] == 1
    assert result["failed_items"] == 0
    assert "matrix_summary_not_accepted" in result["issues"]
    assert "summary:required_language_missing:pl" in result["issues"]


def test_matrix_runner_rejects_missing_model_without_live_runtime(tmp_path: Path) -> None:
    wav_path = tmp_path / "fixture.wav"
    report_dir = tmp_path / "reports"
    _write_wav(wav_path)

    result = run_vosk_fixture_matrix(
        report_dir=report_dir,
        summary_output_path=tmp_path / "matrix_summary.json",
        items=(
            VoskFixtureMatrixItem(
                fixture_id="en_show_desktop",
                language="en",
                model_path=tmp_path / "missing-model",
                wav_path=wav_path,
                output_path=report_dir / "en_show_desktop.json",
            ),
        ),
        require_languages=("en",),
    )

    assert result["accepted"] is False
    assert result["failed_items"] == 1
    assert "en_show_desktop:model_path_missing" in result["issues"]
    assert result["runtime_integration"] is False
    assert result["command_execution_enabled"] is False
    assert result["microphone_stream_started"] is False