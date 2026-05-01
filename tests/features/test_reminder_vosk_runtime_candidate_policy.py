from __future__ import annotations

from pathlib import Path


def test_vosk_pre_whisper_exports_command_intent_metadata() -> None:
    source = Path("modules/runtime/voice_engine_v2/vosk_pre_whisper_candidate.py").read_text()

    assert '"intent_key": str(getattr(asr_result, "intent_key", "") or "")' in source
    assert '"matched_phrase": str(getattr(asr_result, "matched_phrase", "") or "")' in source


def test_runtime_candidates_allow_only_guided_reminder_fast_path_intents() -> None:
    source = Path("modules/runtime/voice_engine_v2/runtime_candidates.py").read_text()

    assert "_vosk_shadow_result_has_allowed_reminder_intent" in source
    assert "reminder.guided_start" in source
    assert "reminder.time_answer" in source
    assert "reminder.message" not in source


def test_runtime_candidate_reminder_override_is_used_inside_vosk_shadow_processing() -> None:
    source = Path("modules/runtime/voice_engine_v2/runtime_candidates.py").read_text()

    start = source.index("    def process_vosk_shadow_result(")
    end = source.index("    def process_request(", start)
    process_block = source[start:end]

    assert "self._vosk_shadow_result_allowed_reminder_intent_key(" in process_block
    assert '"route": "guided_reminder"' in process_block
    assert '"faster_whisper_prevented": True' in process_block
    assert "rejection_reason = None" in process_block


def test_runtime_candidate_reminder_override_keeps_safety_guards() -> None:
    source = Path("modules/runtime/voice_engine_v2/runtime_candidates.py").read_text()

    assert "action_executed" in source
    assert "full_stt_prevented" in source
    assert "runtime_takeover" in source
    assert "command_execution_enabled" in source
    assert "faster_whisper_bypass_enabled" in source
    assert "independent_microphone_stream_started" in source
    assert "live_command_recognition_enabled" in source
