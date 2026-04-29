from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_latency_acceptance_gate import (
    BOTTLENECK_LEGACY_STT_PATH,
    BOTTLENECK_STALE_AUDIO_BACKLOG,
    BOTTLENECK_STT_TRANSCRIPTION,
    main,
    validate_latency_acceptance_gate,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _pre_transcription_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "latest_speech_end_to_observe_ms": 481.084,
            "observation_duration_ms": 63.99,
            "stale_audio_observed": False,
        },
        "metadata": {
            "capture_window_shadow_tap": {
                "capture_finished_to_publish_start_ms": 1.457,
            },
            "endpointing_candidate": {
                "capture_finished_to_vad_observed_ms": 65.751,
                "capture_window_publish_to_vad_observed_ms": 64.293,
            },
            "vosk_shadow_invocation_attempt": {
                "recognition_invocation_performed": False,
                "recognition_attempted": False,
                "result_present": False,
                "raw_pcm_included": False,
                "action_executed": False,
                "runtime_takeover": False,
            },
        },
    }


def _post_capture_record(
    *,
    transcription_ms: float = 2866.558,
    capture_to_transcription_ms: float = 2983.774,
    stale_audio_observed: bool = True,
) -> dict[str, object]:
    return {
        "hook": "post_capture",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "latest_speech_end_to_observe_ms": 3335.492,
            "observation_duration_ms": 75.549,
            "stale_audio_observed": stale_audio_observed,
        },
        "metadata": {
            "transcript_metadata": {
                "transcription_elapsed_seconds": transcription_ms / 1000.0,
                "realtime_audio_bus_capture_window_shadow_tap": {
                    "capture_finished_to_publish_start_ms": 1.457,
                    "capture_window_publish_to_transcription_finished_ms": (
                        capture_to_transcription_ms
                    ),
                },
            }
        },
    }


def test_acceptance_gate_accepts_safe_observation_but_classifies_slow_path(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    result = validate_latency_acceptance_gate(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is True
    assert result["profile_accepted"] is True
    assert result["target_passed"] is False
    assert BOTTLENECK_LEGACY_STT_PATH in result["bottlenecks"]
    assert BOTTLENECK_STT_TRANSCRIPTION in result["bottlenecks"]
    assert BOTTLENECK_STALE_AUDIO_BACKLOG in result["bottlenecks"]
    assert result["classification"]["capture_publish"] == "ok"
    assert result["classification"]["vad_observe"] == "ok"
    assert result["classification"]["capture_to_transcription"] == "slow"
    assert result["classification"]["stale_audio"] == "high"
    assert (
        result["decision"]
        == "investigate_stale_audio_backlog_before_recognition_takeover"
    )


def test_acceptance_gate_can_fail_on_target_miss(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    result = validate_latency_acceptance_gate(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
        fail_on_target_miss=True,
    )

    assert result["accepted"] is False
    assert result["target_passed"] is False
    assert "latency_targets_missed" in result["issues"]


def test_acceptance_gate_passes_fast_clean_log(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _pre_transcription_record(),
            _post_capture_record(
                transcription_ms=420.0,
                capture_to_transcription_ms=520.0,
                stale_audio_observed=False,
            ),
        ],
    )

    result = validate_latency_acceptance_gate(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
        fail_on_target_miss=True,
    )

    assert result["accepted"] is True
    assert result["target_passed"] is True
    assert result["bottlenecks"] == []
    assert result["classification"]["capture_publish"] == "ok"
    assert result["classification"]["vad_observe"] == "ok"
    assert result["classification"]["stt_transcription"] == "ok"
    assert result["classification"]["capture_to_transcription"] == "ok"
    assert result["classification"]["stale_audio"] == "ok"
    assert result["decision"] == "latency_profile_within_current_gate"


def test_acceptance_gate_rejects_invalid_profile(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    unsafe = _pre_transcription_record()
    unsafe["action_executed"] = True
    _write_log(log_path, [unsafe])

    result = validate_latency_acceptance_gate(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is False
    assert result["profile_accepted"] is False
    assert "latency_profile_not_accepted" in result["issues"]
    assert (
        "profile:unsafe_observe_only_fields_present"
        in result["issues"]
    )
    assert result["decision"] == "fix_observation_log_before_runtime_changes"


def test_acceptance_gate_cli_accepts_slow_safe_log_without_hard_fail(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-capture-window-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["target_passed"] is False
    assert BOTTLENECK_LEGACY_STT_PATH in payload["bottlenecks"]


def test_acceptance_gate_cli_rejects_slow_log_with_hard_fail(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-capture-window-records",
            "--fail-on-target-miss",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "latency_targets_missed" in payload["issues"]
