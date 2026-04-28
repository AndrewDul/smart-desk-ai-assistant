from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.voice_engine_v2.command_asr_shadow_bridge import (
    CommandAsrShadowBridgeSettings,
    enrich_record_with_command_asr_shadow,
)
from scripts.validate_voice_engine_v2_vad_timing_command_asr_shadow import (
    main,
    validate_vad_timing_command_asr_shadow_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _endpointing_candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "capture_window_pre_transcription",
        "candidate_present": True,
        "endpoint_detected": True,
        "reason": "endpoint_detected",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "frames_processed": 47,
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _capture_window(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "sample_rate": 16_000,
        "channels": 1,
        "audio_sample_count": 32_000,
        "audio_duration_seconds": 2.0,
        "published_frame_count": 32,
        "published_byte_count": 64_000,
        "capture_finished_to_publish_start_ms": 10.0,
    }
    payload.update(overrides)
    return payload


def _vad_timing_record(
    *,
    candidate: dict[str, object] | None = None,
    capture_window: dict[str, object] | None = None,
    hook: str = "capture_window_pre_transcription",
    legacy_runtime_primary: bool = True,
    action_executed: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "capture_window_shadow_tap": (
            _capture_window() if capture_window is None else capture_window
        )
    }
    if candidate is not None:
        metadata["endpointing_candidate"] = candidate

    return {
        "timestamp_utc": "2026-04-28T00:00:00+00:00",
        "timestamp_monotonic": 1000.0,
        "enabled": True,
        "observed": True,
        "reason": "vad_timing_bridge_pre_transcription_observed_audio",
        "hook": hook,
        "turn_id": "turn-vad-timing-command-asr-shadow-validator",
        "phase": "command",
        "capture_mode": "wake_command",
        "legacy_runtime_primary": legacy_runtime_primary,
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "transcript_present": False,
        "vad_shadow": {},
        "metadata": metadata,
    }


def _enriched_vad_timing_record() -> dict[str, object]:
    return enrich_record_with_command_asr_shadow(
        record=_vad_timing_record(candidate=_endpointing_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )


def test_validate_vad_timing_command_asr_shadow_log_accepts_attached_disabled_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_enriched_vad_timing_record()])

    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=True,
        require_candidate_attached=True,
        require_disabled_only=True,
    )

    assert result["accepted"] is True
    assert result["validator"] == "vad_timing_command_asr_shadow"
    assert result["bridge_records"] == 1
    assert result["capture_window_hook_records"] == 1
    assert result["non_capture_window_hook_records"] == 0
    assert result["legacy_runtime_primary_records"] == 1
    assert result["non_legacy_runtime_primary_records"] == 0
    assert result["candidate_attached_records"] == 1
    assert result["command_asr_candidate_present_records"] == 0
    assert result["recognizer_enabled_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["top_level_unsafe_action_records"] == 0
    assert result["top_level_unsafe_full_stt_records"] == 0
    assert result["top_level_unsafe_takeover_records"] == 0
    assert result["candidate_source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 1
    }
    assert result["candidate_publish_stage_counts"] == {"before_transcription": 1}
    assert result["issues"] == []


def test_validate_vad_timing_command_asr_shadow_log_fails_when_records_missing(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [_vad_timing_record(candidate=_endpointing_candidate())],
    )

    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=True,
    )

    assert result["accepted"] is False
    assert "command_asr_shadow_bridge_records_missing" in result["issues"]


def test_validate_vad_timing_command_asr_shadow_log_fails_on_wrong_hook(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    record = _enriched_vad_timing_record()
    record["hook"] = "after_transcription"

    _write_jsonl(log_path, [record])

    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=True,
        require_candidate_attached=True,
        require_disabled_only=True,
    )

    assert result["accepted"] is False
    assert "line_1:unexpected_hook:after_transcription" in result["issues"]


def test_validate_vad_timing_command_asr_shadow_log_fails_on_non_legacy_primary(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    record = _enriched_vad_timing_record()
    record["legacy_runtime_primary"] = False

    _write_jsonl(log_path, [record])

    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=True,
    )

    assert result["accepted"] is False
    assert "line_1:legacy_runtime_primary_not_true" in result["issues"]


def test_validate_vad_timing_command_asr_shadow_log_fails_on_top_level_action(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    record = _enriched_vad_timing_record()
    record["action_executed"] = True

    _write_jsonl(log_path, [record])

    result = validate_vad_timing_command_asr_shadow_log(
        log_path=log_path,
        require_records=True,
    )

    assert result["accepted"] is False
    assert "line_1:top_level_action_executed" in result["issues"]


def test_cli_returns_zero_for_vad_timing_shadow_records(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_enriched_vad_timing_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-candidate-attached",
            "--require-disabled-only",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["bridge_records"] == 1
    assert payload["candidate_attached_records"] == 1


def test_cli_returns_one_when_vad_timing_shadow_records_missing(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [_vad_timing_record(candidate=_endpointing_candidate())],
    )

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_asr_shadow_bridge_records_missing" in payload["issues"]