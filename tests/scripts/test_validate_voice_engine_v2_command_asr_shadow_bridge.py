from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.voice_engine_v2.command_asr_shadow_bridge import (
    CommandAsrShadowBridgeSettings,
    enrich_record_with_command_asr_shadow,
)
from scripts.validate_voice_engine_v2_command_asr_shadow_bridge import (
    main,
    validate_command_asr_shadow_bridge_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _candidate(**overrides: object) -> dict[str, object]:
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
        "capture_finished_to_publish_start_ms": 2.5,
    }
    payload.update(overrides)
    return payload


def _record(
    *,
    candidate: dict[str, object] | None = None,
    capture_window: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "capture_window_shadow_tap": (
            _capture_window() if capture_window is None else capture_window
        )
    }
    if candidate is not None:
        metadata["endpointing_candidate"] = candidate

    return {
        "turn_id": "turn-command-asr-shadow-validator",
        "hook": "capture_window_pre_transcription",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "metadata": metadata,
    }


def test_validate_command_asr_shadow_bridge_log_accepts_disabled_bridge(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
    )
    _write_jsonl(log_path, [enriched])

    result = validate_command_asr_shadow_bridge_log(
        log_path=log_path,
        require_records=True,
        require_disabled_only=True,
    )

    assert result["accepted"] is True
    assert result["bridge_records"] == 1
    assert result["enabled_records"] == 0
    assert result["disabled_records"] == 1
    assert result["observed_records"] == 0
    assert result["candidate_attached_records"] == 0
    assert result["command_asr_candidate_present_records"] == 0
    assert result["recognizer_enabled_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["issues"] == []


def test_validate_command_asr_shadow_bridge_log_accepts_attached_disabled_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )
    _write_jsonl(log_path, [enriched])

    result = validate_command_asr_shadow_bridge_log(
        log_path=log_path,
        require_records=True,
        require_candidate_attached=True,
        require_disabled_only=True,
    )

    assert result["accepted"] is True
    assert result["bridge_records"] == 1
    assert result["enabled_records"] == 1
    assert result["disabled_records"] == 0
    assert result["observed_records"] == 1
    assert result["candidate_attached_records"] == 1
    assert result["command_asr_candidate_present_records"] == 0
    assert result["recognizer_enabled_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["recognizer_name_counts"] == {"disabled_command_asr": 1}
    assert result["issues"] == []


def test_validate_command_asr_shadow_bridge_log_fails_when_candidate_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
    )
    _write_jsonl(log_path, [enriched])

    result = validate_command_asr_shadow_bridge_log(
        log_path=log_path,
        require_records=True,
        require_candidate_attached=True,
    )

    assert result["accepted"] is False
    assert (
        "command_asr_shadow_bridge_candidate_attached_records_missing"
        in result["issues"]
    )


def test_validate_command_asr_shadow_bridge_log_fails_on_raw_pcm_flag(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )
    enriched["metadata"]["command_asr_candidate"]["raw_pcm_included"] = True
    _write_jsonl(log_path, [enriched])

    result = validate_command_asr_shadow_bridge_log(log_path=log_path)

    assert result["accepted"] is False
    assert "line_1:candidate_raw_pcm_included" in result["issues"]


def test_cli_returns_zero_for_attached_disabled_candidate(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )
    _write_jsonl(log_path, [enriched])

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
    assert payload["candidate_attached_records"] == 1


def test_cli_returns_one_when_records_missing(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "command_asr_shadow_bridge.jsonl"
    _write_jsonl(log_path, [_record(candidate=_candidate())])

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