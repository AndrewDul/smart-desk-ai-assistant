from __future__ import annotations

from pathlib import Path
import wave

import pytest

from modules.runtime.voice_engine_v2.vosk_fixture_recognition_probe import (
    VoskFixtureRecognitionProbeResult,
    probe_vosk_fixture_recognition,
    validate_vosk_fixture_recognition_result,
)


def _create_minimal_vosk_model(path: Path) -> None:
    (path / "am").mkdir(parents=True, exist_ok=True)
    (path / "conf").mkdir(parents=True, exist_ok=True)
    (path / "am" / "final.mdl").write_text("fake model", encoding="utf-8")
    (path / "conf" / "model.conf").write_text("fake config", encoding="utf-8")


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


def test_probe_rejects_missing_model_before_wav_processing(tmp_path: Path) -> None:
    wav_path = tmp_path / "fixture.wav"
    _write_wav(wav_path)

    result = probe_vosk_fixture_recognition(
        model_path=tmp_path / "missing-model",
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "show desktop",
    )

    validation = validate_vosk_fixture_recognition_result(result=result)

    assert validation["accepted"] is False
    assert "model_path_missing" in validation["issues"]
    assert result.reason == "model_path_missing"
    assert result.fixture_recognition_attempted is False
    assert result.microphone_stream_started is False
    assert result.live_command_recognition_enabled is False


def test_probe_matches_command_with_injected_transcript_provider(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture.wav"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path)

    result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "show desktop",
    )

    validation = validate_vosk_fixture_recognition_result(
        result=result,
        require_command_match=True,
    )
    payload = result.to_json_dict()

    assert validation["accepted"] is True
    assert payload["model_structure_ready"] is True
    assert payload["wav_valid"] is True
    assert payload["wav_sample_rate"] == 16_000
    assert payload["wav_channels"] == 1
    assert payload["wav_sample_width_bytes"] == 2
    assert payload["fixture_recognition_attempted"] is True
    assert payload["fixture_recognition_success"] is True
    assert payload["transcript"] == "show desktop"
    assert payload["normalized_text"] == "show desktop"
    assert payload["command_matched"] is True
    assert payload["command_status"] == "matched"
    assert payload["command_language"] == "en"
    assert payload["command_intent_key"] == "visual_shell.show_desktop"
    assert payload["command_matched_phrase"] == "show desktop"
    assert payload["reason"] == "command_matched"
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["faster_whisper_bypass_enabled"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False
    assert payload["raw_pcm_included"] is False


def test_probe_reports_no_match_without_failing_when_not_required(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture.wav"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path)

    result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "random speech",
    )

    validation = validate_vosk_fixture_recognition_result(result=result)
    strict_validation = validate_vosk_fixture_recognition_result(
        result=result,
        require_command_match=True,
    )

    assert validation["accepted"] is True
    assert strict_validation["accepted"] is False
    assert "command_match_missing" in strict_validation["issues"]
    assert result.fixture_recognition_attempted is True
    assert result.command_matched is False
    assert result.command_status == "no_match"
    assert result.reason == "command_not_matched"


def test_probe_rejects_wrong_sample_rate(tmp_path: Path) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture-8k.wav"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path, sample_rate=8_000)

    result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "show desktop",
    )

    validation = validate_vosk_fixture_recognition_result(result=result)

    assert validation["accepted"] is False
    assert "wav_not_valid_for_fixture_probe" in validation["issues"]
    assert result.reason == "wav_sample_rate_unsupported"
    assert result.wav_valid is False
    assert result.fixture_recognition_attempted is False


def test_probe_rejects_stereo_wav(tmp_path: Path) -> None:
    model_path = tmp_path / "vosk-model-small-en"
    wav_path = tmp_path / "fixture-stereo.wav"
    _create_minimal_vosk_model(model_path)
    _write_wav(wav_path, channels=2)

    result = probe_vosk_fixture_recognition(
        model_path=model_path,
        wav_path=wav_path,
        transcript_provider=lambda pcm, sample_rate, vocabulary: "show desktop",
    )

    validation = validate_vosk_fixture_recognition_result(result=result)

    assert validation["accepted"] is False
    assert "wav_not_valid_for_fixture_probe" in validation["issues"]
    assert result.reason == "wav_not_mono"
    assert result.wav_valid is False


def test_probe_result_rejects_runtime_integration() -> None:
    with pytest.raises(ValueError, match="must never integrate with runtime"):
        VoskFixtureRecognitionProbeResult(
            model_path="model",
            wav_path="fixture.wav",
            model_exists=True,
            model_structure_ready=True,
            model_marker_status={},
            wav_exists=True,
            wav_valid=True,
            wav_sample_rate=16_000,
            wav_channels=1,
            wav_sample_width_bytes=2,
            wav_duration_ms=100.0,
            wav_pcm_byte_count=3200,
            vocabulary_size=10,
            fixture_recognition_attempted=False,
            fixture_recognition_success=False,
            transcript="",
            normalized_text="",
            command_matched=False,
            command_status="not_attempted",
            command_language="unknown",
            command_confidence=0.0,
            command_intent_key=None,
            command_matched_phrase=None,
            command_alternatives=(),
            elapsed_ms=None,
            reason="invalid",
            runtime_integration=True,
        )