from __future__ import annotations

import json
from pathlib import Path
import wave

from modules.runtime.voice_engine_v2.vosk_fixture_matrix_runner import (
    VoskFixtureMatrixItem,
)
from scripts.run_voice_engine_v2_vosk_fixture_matrix import (
    main,
    run_voice_engine_v2_vosk_fixture_matrix,
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


def test_run_voice_engine_v2_vosk_fixture_matrix_writes_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    en_model = tmp_path / "models" / "vosk-model-small-en-us-0.15"
    en_wav = tmp_path / "fixtures" / "en_show_desktop.wav"
    report_dir = tmp_path / "reports"
    summary_path = tmp_path / "summary.json"
    _create_minimal_vosk_model(en_model)
    _write_wav(en_wav)

    from modules.runtime.voice_engine_v2 import vosk_fixture_matrix_runner

    monkeypatch.setattr(
        vosk_fixture_matrix_runner,
        "probe_vosk_fixture_recognition",
        lambda **kwargs: _fake_probe_result(
            model_path=kwargs["model_path"],
            wav_path=kwargs["wav_path"],
        ),
    )

    result = run_voice_engine_v2_vosk_fixture_matrix(
        report_dir=report_dir,
        summary_output_path=summary_path,
        require_languages=("en",),
        items=(
            VoskFixtureMatrixItem(
                fixture_id="en_show_desktop",
                language="en",
                model_path=en_model,
                wav_path=en_wav,
                output_path=report_dir / "en_show_desktop.json",
            ),
        ),
    )

    written = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert result["total_items"] == 1
    assert result["summary"]["total_reports"] == 1
    assert written["accepted"] is True
    assert written["action"] == "run_vosk_fixture_matrix"
    assert written["runtime_integration"] is False
    assert written["command_execution_enabled"] is False
    assert written["microphone_stream_started"] is False


def test_cli_returns_one_for_missing_default_models(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--report-dir",
            "var/data/stage24ag_vosk_fixture_matrix",
            "--summary-output-path",
            "var/data/stage24ag_vosk_fixture_matrix_summary.json",
            "--require-language",
            "en",
            "--require-language",
            "pl",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["total_items"] == 6
    assert payload["failed_items"] == 6
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["microphone_stream_started"] is False


def test_cli_no_output_does_not_write_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--report-dir",
            "var/data/stage24ag_vosk_fixture_matrix",
            "--no-output",
            "--require-language",
            "en",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["summary_output_path"] == ""
    assert not Path("var/data/stage24ag_vosk_fixture_matrix_summary.json").exists()


def _fake_probe_result(*, model_path: Path, wav_path: Path):
    from modules.runtime.voice_engine_v2.vosk_fixture_recognition_probe import (
        VoskFixtureRecognitionProbeResult,
    )

    return VoskFixtureRecognitionProbeResult(
        model_path=str(model_path),
        model_exists=True,
        model_marker_status={"am/final.mdl": True, "conf/model.conf": True},
        model_structure_ready=True,
        wav_path=str(wav_path),
        wav_exists=True,
        wav_valid=True,
        wav_channels=1,
        wav_sample_width_bytes=2,
        wav_sample_rate=16000,
        wav_duration_ms=1000.0,
        wav_pcm_byte_count=32000,
        vocabulary_size=25,
        expected_language="en",
        fixture_recognition_attempted=True,
        fixture_recognition_success=True,
        transcript="show desktop",
        normalized_text="show desktop",
        command_status="matched",
        command_intent_key="visual_shell.show_desktop",
        command_language="en",
        command_matched_phrase="show desktop",
        command_confidence=1.0,
        command_alternatives=(),
        command_matched=True,
        elapsed_ms=100.0,
        reason="command_matched",
    )