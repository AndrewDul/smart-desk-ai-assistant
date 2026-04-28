from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vad_shadow_log import (
    main,
    validate_vad_shadow_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(vad_shadow: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-04-28T00:00:00Z",
        "legacy_runtime_primary": True,
        "action_executed": False,
        "full_stt_prevented": False,
        "metadata": {
            "vad_shadow": vad_shadow,
        },
    }


def _safe_vad_shadow(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "observed": True,
        "reason": "vad_shadow_observed_audio",
        "audio_bus_present": True,
        "source": "runtime.metadata.realtime_audio_bus",
        "frames_processed": 4,
        "decisions_processed": 4,
        "events_emitted": 1,
        "latest_frame_sequence": 3,
        "latest_event_type": "speech_started",
        "in_speech": True,
        "speech_started_count": 1,
        "speech_ended_count": 0,
        "speech_frame_count": 4,
        "silence_frame_count": 0,
        "speech_score_count": 4,
        "speech_score_min": 0.9,
        "speech_score_max": 1.0,
        "speech_score_avg": 0.95,
        "speech_score_over_threshold_count": 4,
        "latest_score": 1.0,
        "event_emission_reason": "events_emitted",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "events": [
            {
                "event_type": "speech_started",
                "frame_sequence": 1,
                "score": 1.0,
            }
        ],
        "error": "",
    }
    payload.update(overrides)
    return payload


def test_validate_vad_shadow_log_accepts_safe_records(tmp_path: Path) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [_record(_safe_vad_shadow())])

    result = validate_vad_shadow_log(
        log_path=log_path,
        require_enabled=True,
        require_observed=True,
        require_audio_bus_present=True,
        require_frames=True,
        require_score_diagnostics=True,
    )

    assert result["accepted"] is True
    assert result["vad_shadow_records"] == 1
    assert result["enabled_records"] == 1
    assert result["observed_records"] == 1
    assert result["audio_bus_present_records"] == 1
    assert result["frames_processed_records"] == 1
    assert result["total_frames_processed"] == 4
    assert result["diagnostics_records"] == 1
    assert result["speech_score_records"] == 1
    assert result["speech_frame_records"] == 1
    assert result["silence_frame_records"] == 0
    assert result["max_speech_score"] == 1.0
    assert result["max_speech_frame_count"] == 4
    assert result["max_silence_frame_count"] == 0
    assert result["event_emission_reasons"] == {"events_emitted": 1}
    assert result["event_types"] == {"speech_started": 1}
    assert result["issues"] == []


def test_validate_vad_shadow_log_fails_when_required_shadow_is_missing(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [{"metadata": {}}])

    result = validate_vad_shadow_log(
        log_path=log_path,
        require_enabled=True,
        require_observed=True,
        require_audio_bus_present=True,
        require_frames=True,
    )

    assert result["accepted"] is False
    assert "vad_shadow_enabled_records_missing" in result["issues"]
    assert "vad_shadow_observed_records_missing" in result["issues"]
    assert "vad_shadow_audio_bus_present_records_missing" in result["issues"]
    assert "vad_shadow_frames_processed_records_missing" in result["issues"]


def test_validate_vad_shadow_log_rejects_unsafe_action_execution(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _safe_vad_shadow(
                    action_executed=True,
                    full_stt_prevented=True,
                    runtime_takeover=True,
                )
            )
        ],
    )

    result = validate_vad_shadow_log(log_path=log_path)

    assert result["accepted"] is False
    assert result["unsafe_action_records"] == 1
    assert result["unsafe_full_stt_records"] == 1
    assert result["unsafe_takeover_records"] == 1
    assert "line_1:vad_shadow_action_executed" in result["issues"]
    assert "line_1:vad_shadow_full_stt_prevented" in result["issues"]
    assert "line_1:vad_shadow_runtime_takeover" in result["issues"]


def test_validate_vad_shadow_log_accepts_top_level_vad_shadow_key(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [{"vad_shadow": _safe_vad_shadow()}])

    result = validate_vad_shadow_log(
        log_path=log_path,
        require_enabled=True,
        require_observed=True,
        require_audio_bus_present=True,
        require_frames=True,
    )

    assert result["accepted"] is True
    assert result["vad_shadow_records"] == 1


def test_cli_returns_zero_for_valid_log(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [_record(_safe_vad_shadow())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-enabled",
            "--require-observed",
            "--require-audio-bus-present",
            "--require-frames",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True


def test_cli_returns_one_for_invalid_log(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [{"metadata": {}}])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-enabled",
            "--require-observed",
            "--require-audio-bus-present",
            "--require-frames",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False



def test_validate_vad_shadow_log_can_require_score_diagnostics(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    vad_shadow = _safe_vad_shadow()
    for key in [
        "speech_score_count",
        "speech_frame_count",
        "silence_frame_count",
        "speech_score_over_threshold_count",
        "event_emission_reason",
    ]:
        vad_shadow.pop(key)

    _write_jsonl(log_path, [_record(vad_shadow)])

    result = validate_vad_shadow_log(
        log_path=log_path,
        require_score_diagnostics=True,
    )

    assert result["accepted"] is False
    assert "vad_shadow_score_diagnostics_records_missing" in result["issues"]


def test_cli_accepts_score_diagnostics_requirement(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad.jsonl"
    _write_jsonl(log_path, [_record(_safe_vad_shadow())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-score-diagnostics",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["required_score_diagnostics"] is True