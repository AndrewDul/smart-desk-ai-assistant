from __future__ import annotations

import json
from pathlib import Path
import wave

from scripts.manage_voice_engine_v2_command_fixtures import main


def _write_wav(path: Path, *, sample_rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * 1600)


def test_cli_import_writes_fixture_and_metadata(tmp_path: Path, capsys) -> None:
    source_wav = tmp_path / "source.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav)

    exit_code = main(
        [
            "import",
            "--source-wav",
            str(source_wav),
            "--fixture-id",
            "show_desktop_en",
            "--language",
            "en",
            "--phrase",
            "show desktop",
            "--fixture-root",
            str(fixture_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert (fixture_root / "en" / "show_desktop_en.wav").exists()
    assert (fixture_root / "en" / "show_desktop_en.json").exists()
    assert payload["metadata"]["runtime_integration"] is False
    assert payload["metadata"]["command_execution_enabled"] is False


def test_cli_import_rejects_invalid_wav(tmp_path: Path, capsys) -> None:
    source_wav = tmp_path / "source_8k.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav, sample_rate=8_000)

    exit_code = main(
        [
            "import",
            "--source-wav",
            str(source_wav),
            "--fixture-id",
            "show_desktop_en",
            "--language",
            "en",
            "--phrase",
            "show desktop",
            "--fixture-root",
            str(fixture_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert payload["issues"] == ["wav_sample_rate_unsupported"]


def test_cli_inventory_reports_fixtures(tmp_path: Path, capsys) -> None:
    source_wav = tmp_path / "source.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav)

    main(
        [
            "import",
            "--source-wav",
            str(source_wav),
            "--fixture-id",
            "pokaz_pulpit_pl",
            "--language",
            "pl",
            "--phrase",
            "pokaż pulpit",
            "--fixture-root",
            str(fixture_root),
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "inventory",
            "--fixture-root",
            str(fixture_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["fixture_records"] == 1
    assert payload["language_counts"] == {"pl": 1}


def test_cli_validate_requires_records(tmp_path: Path, capsys) -> None:
    fixture_root = tmp_path / "fixtures"

    exit_code = main(
        [
            "validate",
            "--fixture-root",
            str(fixture_root),
            "--require-records",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_fixture_records_missing" in payload["issues"]


def test_cli_validate_requires_language(tmp_path: Path, capsys) -> None:
    source_wav = tmp_path / "source.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav)

    main(
        [
            "import",
            "--source-wav",
            str(source_wav),
            "--fixture-id",
            "show_desktop_en",
            "--language",
            "en",
            "--phrase",
            "show desktop",
            "--fixture-root",
            str(fixture_root),
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "validate",
            "--fixture-root",
            str(fixture_root),
            "--require-records",
            "--require-language",
            "en",
            "--require-language",
            "pl",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_fixture_language_missing:pl" in payload["issues"]