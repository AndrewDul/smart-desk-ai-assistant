from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_observation import (
    main,
    validate_vosk_shadow_observation,
)


def _write_settings(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "voice_engine": {
                    "enabled": False,
                    "mode": "legacy",
                    "command_first_enabled": False,
                    "fallback_to_legacy_enabled": True,
                    "runtime_candidates_enabled": False,
                    "pre_stt_shadow_enabled": False,
                    "faster_whisper_audio_bus_tap_enabled": False,
                    "vad_shadow_enabled": False,
                    "vad_timing_bridge_enabled": False,
                    "command_asr_shadow_bridge_enabled": False,
                    "vosk_live_shadow_contract_enabled": False,
                    "vosk_shadow_invocation_plan_enabled": False,
                    "vosk_shadow_pcm_reference_enabled": False,
                    "vosk_shadow_asr_result_enabled": False,
                    "vosk_shadow_recognition_preflight_enabled": False,
                    "vosk_shadow_invocation_attempt_enabled": False,
                }
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _safe_false_fields() -> dict[str, object]:
    return {
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "result_present": False,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
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


def _metadata_chain() -> dict[str, object]:
    safe = _safe_false_fields()

    return {
        "vosk_live_shadow": {
            "contract_stage": "vosk_live_shadow_contract",
            "contract_version": "vosk_live_shadow_contract_v1",
            "enabled": True,
            "observed": False,
            "reason": "vosk_live_shadow_result_missing",
            "metadata_key": "vosk_live_shadow",
            "input_source": "existing_command_audio_segment",
            "recognizer_name": "vosk_command_asr_shadow",
            "recognizer_enabled": False,
            "transcript": "",
            "normalized_text": "",
            "language": None,
            "confidence": None,
            "alternatives": [],
            **safe,
        },
        "vosk_shadow_invocation_plan": {
            "plan_stage": "vosk_shadow_invocation_plan",
            "plan_version": "vosk_shadow_invocation_plan_v1",
            "enabled": True,
            "plan_ready": True,
            "reason": "observe_only_invocation_boundary_ready",
            "metadata_key": "vosk_shadow_invocation_plan",
            "hook": "capture_window_pre_transcription",
            "input_source": "existing_command_audio_segment_metadata_only",
            "recognizer_name": "vosk_command_asr",
            "command_asr_bridge_present": True,
            "command_asr_candidate_present": True,
            "vosk_live_shadow_contract_present": True,
            "segment_present": True,
            "segment_reason": "segment_ready_for_command_recognizer",
            "segment_audio_duration_ms": 852.0,
            "segment_audio_sample_count": 13632,
            "segment_published_byte_count": 27264,
            "segment_sample_rate": 16000,
            "segment_pcm_encoding": "pcm_s16le",
            **safe,
        },
        "vosk_shadow_pcm_reference": {
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
            "audio_sample_count": 13632,
            "audio_duration_ms": 852.0,
            "published_frame_count": 14,
            "published_byte_count": 27264,
            "segment_present": True,
            "invocation_plan_present": True,
            "invocation_plan_ready": True,
            "command_asr_candidate_present": True,
            "pcm_retrieval_allowed": False,
            **safe,
        },
        "vosk_shadow_asr_result": {
            "result_stage": "vosk_shadow_asr_result",
            "result_version": "vosk_shadow_asr_result_v1",
            "enabled": True,
            "result_present": False,
            "reason": "vosk_shadow_asr_not_attempted",
            "metadata_key": "vosk_shadow_asr_result",
            "recognizer_name": "disabled_command_asr",
            "recognizer_enabled": False,
            "transcript": "",
            "normalized_text": "",
            "language": None,
            "confidence": None,
            "alternatives": [],
            "turn_id": "turn-policy",
            "hook": "capture_window_pre_transcription",
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "segment_present": True,
            "segment_reason": "segment_ready_for_command_recognizer",
            "segment_audio_duration_ms": 852.0,
            "segment_audio_sample_count": 13632,
            "segment_published_byte_count": 27264,
            "segment_sample_rate": 16000,
            "segment_pcm_encoding": "pcm_s16le",
            **safe,
        },
        "vosk_shadow_recognition_preflight": {
            "preflight_stage": "vosk_shadow_recognition_preflight",
            "preflight_version": "vosk_shadow_recognition_preflight_v1",
            "enabled": True,
            "preflight_ready": True,
            "recognition_allowed": False,
            "recognition_blocked": True,
            "reason": "recognition_invocation_blocked_by_stage_policy",
            "metadata_key": "vosk_shadow_recognition_preflight",
            "hook": "capture_window_pre_transcription",
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "recognizer_name": "vosk_command_asr",
            "live_shadow_present": True,
            "invocation_plan_present": True,
            "invocation_plan_ready": True,
            "pcm_reference_present": True,
            "pcm_reference_ready": True,
            "asr_result_present": True,
            "asr_result_not_attempted": True,
            "audio_sample_count": 13632,
            "published_byte_count": 27264,
            "sample_rate": 16000,
            "pcm_encoding": "pcm_s16le",
            "pcm_retrieval_allowed": False,
            "recognition_invocation_allowed": False,
            **safe,
        },
        "vosk_shadow_invocation_attempt": {
            "attempt_stage": "vosk_shadow_invocation_attempt",
            "attempt_version": "vosk_shadow_invocation_attempt_v1",
            "enabled": True,
            "attempt_ready": True,
            "invocation_allowed": False,
            "invocation_blocked": True,
            "reason": "recognition_invocation_blocked_by_stage_policy",
            "metadata_key": "vosk_shadow_invocation_attempt",
            "hook": "capture_window_pre_transcription",
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "recognizer_name": "vosk_command_asr",
            "preflight_present": True,
            "preflight_ready": True,
            "preflight_recognition_blocked": True,
            "preflight_reason": "recognition_invocation_blocked_by_stage_policy",
            "audio_sample_count": 13632,
            "published_byte_count": 27264,
            "sample_rate": 16000,
            "pcm_encoding": "pcm_s16le",
            "pcm_retrieval_allowed": False,
            "recognition_allowed": False,
            "recognition_invocation_allowed": False,
            **safe,
        },
    }


def _capture_window_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-policy",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": False,
            "cadence_diagnostic_reason": "fresh_audio_backlog_observed",
            "pcm_profile_signal_level": "high",
            "frame_source_counts": {
                "faster_whisper_callback_shadow_tap": 21,
                "faster_whisper_capture_window_shadow_tap": 26,
            },
        },
        "metadata": _metadata_chain(),
    }


def test_vosk_shadow_observation_accepts_cursor_policy_gate(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_log(log_path, [_capture_window_record()])

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
        require_recognition_preflight_attached=True,
        require_recognition_preflight_ready=True,
        require_invocation_attempt_attached=True,
        require_invocation_attempt_ready=True,
        require_capture_window_readiness=True,
        reject_post_capture_readiness=True,
        require_restored_config=True,
        allow_recognition_attempt=False,
    )

    assert result["accepted"] is True
    assert result["cursor_policy"]["accepted"] is True
    assert result["cursor_policy"]["accepted_readiness_records"] == 1
    assert result["cursor_policy"]["non_capture_window_readiness_records"] == 0
    assert result["cursor_policy"]["capture_window_stale_readiness_records"] == 0
    assert result["issues"] == []


def test_vosk_shadow_observation_cli_accepts_cursor_policy_gate(
    tmp_path: Path,
    capsys,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_log(log_path, [_capture_window_record()])

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
            "--require-recognition-preflight-attached",
            "--require-recognition-preflight-ready",
            "--require-invocation-attempt-attached",
            "--require-invocation-attempt-ready",
            "--require-capture-window-readiness",
            "--reject-post-capture-readiness",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["cursor_policy"]["accepted"] is True
    assert payload["cursor_policy"]["accepted_readiness_records"] == 1
