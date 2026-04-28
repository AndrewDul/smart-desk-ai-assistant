from __future__ import annotations

import json
from pathlib import Path
import wave

from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.runtime.voice_engine_v2.vosk_fixture_recognition_probe import (
    probe_vosk_fixture_recognition,
    validate_vosk_fixture_recognition_result,
)
from scripts.probe_voice_engine_v2_vosk_fixture_recognition import (
    main,
    run_vosk_fixture_recognition_probe,
)


def _create_minimal_vosk_model(path: Path) -> None:
    (path / "am").mkdir(parents=True, exist_ok=True)
    (path / "conf").mkdir(parents=True, exist_ok=True)
    (path / "am" / "final.mdl").write_text("fake model", encoding="utf-8")
    (path / "conf" / "model.conf").write_text("fake config", encoding="utf-8")


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 1600)


def test_run_vosk_fixture_recognition_probe_writes_failure_report_for_missing_wav(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "missing.wav"
    output_path = tmp_path / "probe.json"
    _create_minimal_vosk_model(model_path)

    result = run_vosk_fixture_recognition_probe(
        model_path=model_path,
        wav_path=wav_path,
        output_path=output_path,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["accepted"] is False
    assert report["accepted"] is False
    assert "wav_path_missing" in report["issues"]
    assert report["runtime_integration"] is False
    assert report["command_execution_enabled"] is False
    assert report["faster_whisper_bypass_enabled"] is False
    assert report["microphone_stream_started"] is False
    assert report["live_command_recognition_enabled"] is False


def test_run_vosk_fixture_recognition_probe_writes_language_scope_to_report(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture.wav"
    output_path = tmp_path / "probe.json"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path)

    result = run_vosk_fixture_recognition_probe(
        model_path=model_path,
        wav_path=wav_path,
        output_path=output_path,
        language=CommandLanguage.ENGLISH,
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["result"]["expected_language"] == "en"
    assert report["result"]["expected_language"] == "en"
    assert report["runtime_integration"] is False
    assert report["microphone_stream_started"] is False
    assert report["live_command_recognition_enabled"] is False


def test_validation_payload_accepts_injected_command_match(tmp_path: Path) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture.wav"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path)

    probe_result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "hide shell",
    )
    validation = validate_vosk_fixture_recognition_result(
        result=probe_result,
        require_command_match=True,
    )

    assert validation["accepted"] is True
    assert validation["result"]["command_matched"] is True
    assert validation["result"]["command_intent_key"] == "visual_shell.show_desktop"
    assert validation["result"]["runtime_integration"] is False
    assert validation["result"]["microphone_stream_started"] is False


def test_cli_returns_one_for_missing_wav(tmp_path: Path, capsys) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    output_path = tmp_path / "probe.json"
    _create_minimal_vosk_model(model_path)

    exit_code = main(
        [
            "--model-path",
            str(model_path),
            "--wav-path",
            str(tmp_path / "missing.wav"),
            "--output-path",
            str(output_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "wav_path_missing" in payload["issues"]
    assert output_path.exists()


def test_cli_accepts_language_scope(tmp_path: Path, capsys) -> None:
    wav_path = tmp_path / "fixture.wav"
    _write_wav(wav_path)

    exit_code = main(
        [
            "--model-path",
            str(tmp_path / "missing-model"),
            "--wav-path",
            str(wav_path),
            "--language",
            "en",
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["result"]["expected_language"] == "en"
    assert "model_path_missing" in payload["issues"]


def test_cli_no_output_for_missing_model(tmp_path: Path, capsys) -> None:
    wav_path = tmp_path / "fixture.wav"
    _write_wav(wav_path)

    exit_code = main(
        [
            "--model-path",
            str(tmp_path / "missing-model"),
            "--wav-path",
            str(wav_path),
            "--no-output",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "model_path_missing" in payload["issues"]
    assert payload["output_path"] == ""