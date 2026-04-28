from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_observation import (
    main,
    validate_observation_config,
    validate_vosk_shadow_observation,
)


def _settings_payload(*, restored: bool = True) -> dict[str, object]:
    observation_value = not restored
    return {
        "voice_engine": {
            "enabled": False,
            "mode": "legacy",
            "command_first_enabled": False,
            "fallback_to_legacy_enabled": True,
            "runtime_candidates_enabled": False,
            "pre_stt_shadow_enabled": observation_value,
            "faster_whisper_audio_bus_tap_enabled": observation_value,
            "vad_shadow_enabled": observation_value,
            "vad_timing_bridge_enabled": observation_value,
            "command_asr_shadow_bridge_enabled": observation_value,
            "vosk_live_shadow_contract_enabled": observation_value,
            "vosk_shadow_invocation_plan_enabled": observation_value,
            "vosk_shadow_pcm_reference_enabled": observation_value,
            "vosk_shadow_asr_result_enabled": observation_value,
        }
    }


def _write_settings(path: Path, *, restored: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_settings_payload(restored=restored), indent=2) + "\n",
        encoding="utf-8",
    )


def _live_shadow() -> dict[str, object]:
    return {
        "contract_stage": "vosk_live_shadow_contract",
        "contract_version": "vosk_live_shadow_contract_v1",
        "enabled": True,
        "observed": False,
        "reason": "vosk_live_shadow_result_missing",
        "metadata_key": "vosk_live_shadow",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "input_source": "existing_command_audio_segment",
        "recognizer_name": "vosk_command_asr_shadow",
        "recognizer_enabled": False,
        "recognition_attempted": False,
        "recognized": False,
        "transcript": "",
        "normalized_text": "",
        "language": None,
        "confidence": None,
        "alternatives": [],
        "command_matched": False,
        "command_intent_key": None,
        "command_language": None,
        "command_matched_phrase": None,
        "command_confidence": None,
        "command_alternatives": [],
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _invocation_plan() -> dict[str, object]:
    return {
        "plan_stage": "vosk_shadow_invocation_plan",
        "plan_version": "vosk_shadow_invocation_plan_v1",
        "enabled": True,
        "plan_ready": True,
        "reason": "observe_only_invocation_boundary_ready",
        "metadata_key": "vosk_shadow_invocation_plan",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "input_source": "existing_command_audio_segment_metadata_only",
        "recognizer_name": "vosk_command_asr",
        "command_asr_bridge_present": True,
        "command_asr_candidate_present": True,
        "vosk_live_shadow_contract_present": True,
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
        "pcm_retrieval_allowed": False,
        "pcm_retrieval_performed": False,
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _pcm_reference() -> dict[str, object]:
    return {
        "reference_stage": "vosk_shadow_pcm_reference",
        "reference_version": "vosk_shadow_pcm_reference_v1",
        "enabled": True,
        "reference_ready": True,
        "reason": "existing_capture_window_pcm_reference_ready",
        "metadata_key": "vosk_shadow_pcm_reference",
        "hook": "capture_window_pre_transcription",
        "retrieval_strategy": "existing_capture_window_audio_bus_snapshot",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "pcm_encoding": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bytes": 2,
        "audio_sample_count": 32000,
        "audio_duration_ms": 1800.0,
        "published_frame_count": 32,
        "published_byte_count": 64000,
        "segment_present": True,
        "invocation_plan_present": True,
        "invocation_plan_ready": True,
        "command_asr_candidate_present": True,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _asr_result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "result_stage": "vosk_shadow_asr_result",
        "result_version": "vosk_shadow_asr_result_v1",
        "enabled": True,
        "result_present": False,
        "reason": "vosk_shadow_asr_not_attempted",
        "metadata_key": "vosk_shadow_asr_result",
        "recognizer_name": "disabled_command_asr",
        "recognizer_enabled": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "transcript": "",
        "normalized_text": "",
        "language": None,
        "confidence": None,
        "alternatives": [],
        "turn_id": "turn-vosk-shadow-observation",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
        "pcm_retrieval_performed": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }
    payload.update(overrides)
    return payload


def _record(*, include_asr_result: bool = True) -> dict[str, object]:
    metadata: dict[str, object] = {
        "vosk_live_shadow": _live_shadow(),
        "vosk_shadow_invocation_plan": _invocation_plan(),
        "vosk_shadow_pcm_reference": _pcm_reference(),
    }
    if include_asr_result:
        metadata["vosk_shadow_asr_result"] = _asr_result()

    return {
        "hook": "capture_window_pre_transcription",
        "metadata": metadata,
    }


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_observation_config_accepts_restored_safe_config(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, restored=True)

    result = validate_observation_config(
        settings_path=settings_path,
        require_restored=True,
    )

    assert result["accepted"] is True
    assert result["issues"] == []


def test_observation_config_rejects_active_flags_when_restored_required(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, restored=False)

    result = validate_observation_config(
        settings_path=settings_path,
        require_restored=True,
    )

    assert result["accepted"] is False
    assert "voice_engine.vosk_shadow_asr_result_enabled_must_be_false_after_observation" in result["issues"]


def test_vosk_shadow_observation_accepts_full_safe_chain(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, restored=True)
    _write_log(log_path, [_record(include_asr_result=True)])

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_invocation_plan_attached=True,
        require_invocation_plan_ready=True,
        require_pcm_reference_attached=True,
        require_pcm_reference_ready=True,
        require_asr_result_attached=True,
        require_asr_result_not_attempted=True,
        require_restored_config=True,
        allow_recognition_attempt=False,
    )

    assert result["accepted"] is True
    assert result["config"]["accepted"] is True
    assert result["telemetry"]["accepted"] is True
    assert result["invocation_plan"]["accepted"] is True
    assert result["pcm_reference"]["accepted"] is True
    assert result["asr_result"]["accepted"] is True
    assert result["issues"] == []


def test_vosk_shadow_observation_rejects_missing_asr_result_when_required(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, restored=True)
    _write_log(log_path, [_record(include_asr_result=False)])

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_invocation_plan_attached=True,
        require_invocation_plan_ready=True,
        require_pcm_reference_attached=True,
        require_pcm_reference_ready=True,
        require_asr_result_attached=True,
        require_asr_result_not_attempted=True,
        require_restored_config=True,
        allow_recognition_attempt=False,
    )

    assert result["accepted"] is False
    assert "asr_result:vosk_shadow_asr_result_records_missing" in result["issues"]
    assert "asr_result:not_attempted_vosk_shadow_asr_result_records_missing" in result["issues"]


def test_vosk_shadow_observation_rejects_asr_recognition_attempt_by_default(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, restored=True)

    record = _record(include_asr_result=True)
    metadata = record["metadata"]
    assert isinstance(metadata, dict)
    metadata["vosk_shadow_asr_result"] = _asr_result(
        result_present=True,
        reason="vosk_shadow_asr_recognized",
        recognizer_name="vosk_command_asr",
        recognizer_enabled=True,
        recognition_invocation_performed=True,
        recognition_attempted=True,
        recognized=True,
        command_matched=True,
        transcript="show desktop",
        normalized_text="show desktop",
        language="en",
        confidence=0.9,
        pcm_retrieval_performed=True,
    )
    _write_log(log_path, [record])

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_invocation_plan_attached=True,
        require_invocation_plan_ready=True,
        require_pcm_reference_attached=True,
        require_pcm_reference_ready=True,
        require_asr_result_attached=True,
        require_asr_result_not_attempted=False,
        require_restored_config=True,
        allow_recognition_attempt=False,
    )

    assert result["accepted"] is False
    assert "asr_result:line_1:recognition_attempt_not_allowed" in result["issues"]
    assert "asr_result:result_present_records_not_allowed" in result["issues"]
    assert "asr_result:recognition_attempt_records_not_allowed" in result["issues"]


def test_cli_accepts_full_safe_chain(tmp_path: Path, capsys) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, restored=True)
    _write_log(log_path, [_record(include_asr_result=True)])

    exit_code = main(
        [
            "--settings",
            str(settings_path),
            "--log-path",
            str(log_path),
            "--require-contract-attached",
            "--require-invocation-plan-attached",
            "--require-invocation-plan-ready",
            "--require-pcm-reference-attached",
            "--require-pcm-reference-ready",
            "--require-asr-result-attached",
            "--require-asr-result-not-attempted",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["asr_result"]["accepted"] is True