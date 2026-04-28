from __future__ import annotations

import json
from pathlib import Path

from scripts.inspect_voice_engine_v2_vosk_shadow_readiness import main


def _safe_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "metadata": {
            "vosk_live_shadow": {
                "enabled": True,
                "observed": False,
                "reason": "vosk_live_shadow_result_missing",
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
            },
            "command_asr_shadow_bridge": {
                "enabled": True,
                "observed": True,
                "reason": "command_asr_shadow_bridge_observed",
                "command_asr_reason": "command_asr_candidate_missing",
                "asr_reason": "command_asr_disabled",
                "recognizer_enabled": False,
                "recognition_attempted": False,
                "recognized": False,
                "raw_pcm_included": False,
                "action_executed": False,
                "full_stt_prevented": False,
                "runtime_takeover": False,
            },
            "command_asr_candidate": {
                "segment_present": True,
                "reason": "command_asr_candidate_missing",
                "asr_reason": "command_asr_disabled",
                "raw_pcm_included": False,
                "action_executed": False,
                "full_stt_prevented": False,
                "runtime_takeover": False,
            },
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_cli_accepts_safe_readiness_log(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_safe_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-ready-for-design",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_readiness"
    assert payload["ready_for_observe_only_invocation_design"] is True
    assert payload["contract_records"] == 1
    assert payload["command_audio_segment_ready_records"] == 1


def test_cli_rejects_missing_ready_design_when_required(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _safe_record()
    record["metadata"]["command_asr_candidate"]["segment_present"] = False  # type: ignore[index]
    _write_jsonl(log_path, [record])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-ready-for-design",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "ready_for_design_required" in payload["blockers"]


def test_cli_rejects_missing_records_when_required(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "missing.jsonl"

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "records_required" in payload["blockers"]