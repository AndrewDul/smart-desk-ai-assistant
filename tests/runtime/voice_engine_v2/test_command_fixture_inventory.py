from __future__ import annotations

from pathlib import Path
import wave

import pytest

from modules.runtime.voice_engine_v2.command_fixture_inventory import (
    CommandFixtureMetadata,
    import_command_fixture,
    inventory_command_fixtures,
    validate_command_fixture_inventory,
    validate_wav_fixture,
)


def _write_wav(
    path: Path,
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
    sample_width_bytes: int = 2,
    frame_count: int = 1600,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width_bytes)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count * channels)


def test_validate_wav_fixture_accepts_16k_mono_pcm16(tmp_path: Path) -> None:
    wav_path = tmp_path / "show_desktop.wav"
    _write_wav(wav_path)

    result = validate_wav_fixture(wav_path=wav_path)
    payload = result.to_json_dict()

    assert payload["valid"] is True
    assert payload["reason"] == "wav_fixture_ready"
    assert payload["sample_rate"] == 16_000
    assert payload["channels"] == 1
    assert payload["sample_width_bytes"] == 2
    assert payload["raw_pcm_included"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False


def test_validate_wav_fixture_rejects_wrong_sample_rate(tmp_path: Path) -> None:
    wav_path = tmp_path / "wrong_rate.wav"
    _write_wav(wav_path, sample_rate=8_000)

    result = validate_wav_fixture(wav_path=wav_path)

    assert result.valid is False
    assert result.reason == "wav_sample_rate_unsupported"


def test_validate_wav_fixture_rejects_stereo(tmp_path: Path) -> None:
    wav_path = tmp_path / "stereo.wav"
    _write_wav(wav_path, channels=2)

    result = validate_wav_fixture(wav_path=wav_path)

    assert result.valid is False
    assert result.reason == "wav_not_mono"


def test_import_command_fixture_copies_wav_and_writes_metadata(
    tmp_path: Path,
) -> None:
    source_wav = tmp_path / "source.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav)

    result = import_command_fixture(
        source_wav_path=source_wav,
        fixture_id="show_desktop_en",
        language="en",
        phrase="show desktop",
        fixture_root=fixture_root,
    )

    assert result["accepted"] is True
    assert result["issues"] == []

    metadata = result["metadata"]
    target_wav = fixture_root / "en" / "show_desktop_en.wav"
    target_metadata = fixture_root / "en" / "show_desktop_en.json"

    assert target_wav.exists()
    assert target_metadata.exists()
    assert metadata["fixture_id"] == "show_desktop_en"
    assert metadata["language"] == "en"
    assert metadata["phrase"] == "show desktop"
    assert metadata["sample_rate"] == 16_000
    assert metadata["channels"] == 1
    assert metadata["sample_width_bytes"] == 2
    assert metadata["raw_pcm_included"] is False
    assert metadata["microphone_stream_started"] is False
    assert metadata["runtime_integration"] is False
    assert metadata["command_execution_enabled"] is False
    assert metadata["faster_whisper_bypass_enabled"] is False
    assert metadata["live_command_recognition_enabled"] is False


def test_import_command_fixture_rejects_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    source_wav = tmp_path / "source.wav"
    fixture_root = tmp_path / "fixtures"
    _write_wav(source_wav)

    first = import_command_fixture(
        source_wav_path=source_wav,
        fixture_id="show_desktop_en",
        language="en",
        phrase="show desktop",
        fixture_root=fixture_root,
    )
    second = import_command_fixture(
        source_wav_path=source_wav,
        fixture_id="show_desktop_en",
        language="en",
        phrase="show desktop",
        fixture_root=fixture_root,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["issues"] == ["fixture_already_exists"]


def test_inventory_command_fixtures_reports_language_counts(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    source_en = tmp_path / "source_en.wav"
    source_pl = tmp_path / "source_pl.wav"
    _write_wav(source_en)
    _write_wav(source_pl)

    import_command_fixture(
        source_wav_path=source_en,
        fixture_id="show_desktop_en",
        language="en",
        phrase="show desktop",
        fixture_root=fixture_root,
    )
    import_command_fixture(
        source_wav_path=source_pl,
        fixture_id="pokaz_pulpit_pl",
        language="pl",
        phrase="pokaż pulpit",
        fixture_root=fixture_root,
    )

    inventory = inventory_command_fixtures(fixture_root=fixture_root)

    assert inventory["accepted"] is True
    assert inventory["fixture_records"] == 2
    assert inventory["language_counts"] == {"en": 1, "pl": 1}
    assert inventory["issues"] == []


def test_validate_command_fixture_inventory_requires_languages(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "fixtures"
    source_en = tmp_path / "source_en.wav"
    _write_wav(source_en)

    import_command_fixture(
        source_wav_path=source_en,
        fixture_id="show_desktop_en",
        language="en",
        phrase="show desktop",
        fixture_root=fixture_root,
    )

    result = validate_command_fixture_inventory(
        fixture_root=fixture_root,
        require_records=True,
        require_languages=("en", "pl"),
    )

    assert result["accepted"] is False
    assert "command_fixture_language_missing:pl" in result["issues"]


def test_command_fixture_metadata_rejects_unsafe_runtime_integration() -> None:
    with pytest.raises(ValueError, match="must not integrate runtime"):
        CommandFixtureMetadata(
            fixture_id="show_desktop_en",
            language="en",
            phrase="show desktop",
            wav_path="fixture.wav",
            metadata_path="fixture.json",
            sample_rate=16_000,
            channels=1,
            sample_width_bytes=2,
            frame_count=1600,
            duration_ms=100.0,
            pcm_byte_count=3200,
            runtime_integration=True,
        )