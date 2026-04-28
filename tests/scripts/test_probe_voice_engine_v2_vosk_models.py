from __future__ import annotations

import json
from pathlib import Path

from scripts.probe_voice_engine_v2_vosk_models import (
    main,
    run_vosk_model_probe,
)


def _create_minimal_vosk_model(path: Path) -> None:
    (path / "am").mkdir(parents=True, exist_ok=True)
    (path / "conf").mkdir(parents=True, exist_ok=True)
    (path / "am" / "final.mdl").write_text("fake model", encoding="utf-8")
    (path / "conf" / "model.conf").write_text("fake config", encoding="utf-8")


def test_run_vosk_model_probe_writes_report_for_present_model(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    output_path = tmp_path / "probe.json"
    _create_minimal_vosk_model(model_path)

    result = run_vosk_model_probe(
        model_paths=(model_path,),
        load_model=False,
        require_model_present=True,
        output_path=output_path,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["accepted"] is True
    assert result["action"] == "probe_vosk_models"
    assert result["runtime_integration"] is False
    assert result["command_execution_enabled"] is False
    assert result["faster_whisper_bypass_enabled"] is False
    assert result["microphone_stream_started"] is False
    assert result["active_command_recognition_enabled"] is False
    assert report["accepted"] is True
    assert report["present_model_records"] == 1


def test_cli_returns_zero_for_present_model(tmp_path: Path, capsys) -> None:
    model_path = tmp_path / "vosk-model-small-pl"
    output_path = tmp_path / "probe.json"
    _create_minimal_vosk_model(model_path)

    exit_code = main(
        [
            "--model-path",
            str(model_path),
            "--require-model-present",
            "--output-path",
            str(output_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["present_model_records"] == 1
    assert payload["structure_ready_records"] == 1
    assert payload["load_attempted_records"] == 0
    assert payload["runtime_integration"] is False
    assert output_path.exists()


def test_cli_returns_one_when_required_model_missing(
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "probe.json"

    exit_code = main(
        [
            "--model-path",
            str(tmp_path / "missing"),
            "--require-model-present",
            "--output-path",
            str(output_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "vosk_model_present_records_missing" in payload["issues"]
    assert output_path.exists()


def test_cli_no_output_skips_report_file(tmp_path: Path, capsys) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    _create_minimal_vosk_model(model_path)

    exit_code = main(
        [
            "--model-path",
            str(model_path),
            "--require-model-present",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["output_path"] == ""