from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_readiness import (
    build_vosk_shadow_readiness_report,
)


def _safe_contract() -> dict[str, object]:
    return {
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
    }


def _safe_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "metadata": {
            "vosk_live_shadow": _safe_contract(),
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


def test_readiness_accepts_safe_waiting_contract_with_command_segment() -> None:
    report = build_vosk_shadow_readiness_report([_safe_record()])

    assert report.accepted is True
    assert report.ready_for_observe_only_invocation_design is True
    assert report.reason == "ready_for_observe_only_invocation_design"
    assert report.contract_records == 1
    assert report.command_asr_bridge_records == 1
    assert report.command_asr_candidate_records == 1
    assert report.command_audio_segment_ready_records == 1
    assert report.recognition_attempted_records == 0
    assert report.recognized_records == 0
    assert report.command_matched_records == 0
    assert report.unsafe_contract_records == 0
    assert report.raw_pcm_records == 0
    assert report.blockers == ()


def test_readiness_rejects_missing_contract_records() -> None:
    report = build_vosk_shadow_readiness_report(
        [{"hook": "capture_window_pre_transcription", "metadata": {}}]
    )

    assert report.accepted is False
    assert report.ready_for_observe_only_invocation_design is False
    assert "vosk_live_shadow_contract_records_missing" in report.blockers


def test_readiness_blocks_recognition_before_invocation_stage() -> None:
    record = _safe_record()
    contract = record["metadata"]["vosk_live_shadow"]  # type: ignore[index]
    contract["recognition_attempted"] = True  # type: ignore[index]

    report = build_vosk_shadow_readiness_report([record])

    assert report.accepted is False
    assert report.ready_for_observe_only_invocation_design is False
    assert "recognition_attempted_before_recognizer_invocation_stage" in report.blockers


def test_readiness_blocks_runtime_takeover_contract() -> None:
    record = _safe_record()
    contract = record["metadata"]["vosk_live_shadow"]  # type: ignore[index]
    contract["runtime_takeover"] = True  # type: ignore[index]

    report = build_vosk_shadow_readiness_report([record])

    assert report.accepted is False
    assert report.unsafe_contract_records == 1
    assert "unsafe_contract_records_present" in report.blockers


def test_readiness_blocks_raw_pcm_in_telemetry() -> None:
    record = _safe_record()
    contract = record["metadata"]["vosk_live_shadow"]  # type: ignore[index]
    contract["raw_pcm_included"] = True  # type: ignore[index]

    report = build_vosk_shadow_readiness_report([record])

    assert report.accepted is False
    assert report.raw_pcm_records == 1
    assert "raw_pcm_included_in_telemetry" in report.blockers


def test_readiness_requires_capture_window_hook() -> None:
    record = _safe_record()
    record["hook"] = "post_capture"

    report = build_vosk_shadow_readiness_report([record])

    assert report.accepted is False
    assert report.non_capture_window_contract_records == 1
    assert "non_capture_window_contract_records_present" in report.blockers


def test_readiness_requires_ready_command_audio_segment_for_next_design() -> None:
    record = _safe_record()
    candidate = record["metadata"]["command_asr_candidate"]  # type: ignore[index]
    candidate["segment_present"] = False  # type: ignore[index]

    report = build_vosk_shadow_readiness_report([record])

    assert report.accepted is True
    assert report.ready_for_observe_only_invocation_design is False
    assert "command_audio_segment_ready_records_missing" in report.blockers