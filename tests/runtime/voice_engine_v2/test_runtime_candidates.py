from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.contracts import RouteKind
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _bundle(
    *,
    runtime_candidates_enabled: bool,
    allowlist: list[str] | None = None,
    enabled: bool = False,
    mode: str = "legacy",
    command_first_enabled: bool = False,
):
    return build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": enabled,
                "version": "v2",
                "mode": mode,
                "command_first_enabled": command_first_enabled,
                "fallback_to_legacy_enabled": True,
                "runtime_candidates_enabled": runtime_candidates_enabled,
                "runtime_candidate_intent_allowlist": allowlist
                if allowlist is not None
                else ["assistant.identity", "system.current_time"],
            }
        }
    )


def _safe_vosk_shadow_result(
    *,
    transcript: str,
    normalized_text: str,
    language: str,
    confidence: float = 1.0,
    command_matched: bool = True,
    recognized: bool = True,
    action_executed: bool = False,
    runtime_takeover: bool = False,
) -> dict[str, object]:
    return {
        "result_stage": "vosk_shadow_asr_result",
        "result_version": "vosk_shadow_asr_result_v1",
        "reason": "vosk_shadow_asr_recognized" if recognized else "vosk_shadow_asr_not_recognized",
        "recognizer_name": "vosk_command_asr",
        "recognizer_enabled": True,
        "recognition_invocation_performed": True,
        "recognition_attempted": True,
        "recognized": recognized,
        "command_matched": command_matched,
        "transcript": transcript,
        "normalized_text": normalized_text,
        "language": language,
        "confidence": confidence,
        "raw_pcm_included": False,
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": runtime_takeover,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }


def test_runtime_candidate_adapter_refuses_when_disabled() -> None:
    bundle = _bundle(runtime_candidates_enabled=False)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-disabled",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "runtime_candidates_disabled"
    assert result.route_decision is None
    assert bundle.settings.command_pipeline_can_run is False


def test_runtime_candidate_adapter_accepts_allowlisted_time_command() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-time",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.reason == "accepted"
    assert result.intent_key == "system.current_time"
    assert result.legacy_runtime_primary is True
    assert result.route_decision is not None
    assert result.route_decision.kind == RouteKind.ACTION
    assert result.route_decision.primary_intent == "ask_time"
    assert result.route_decision.metadata["lane"] == "voice_engine_v2_runtime_candidate"
    assert result.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_adapter_accepts_allowlisted_identity_command() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-identity",
        transcript="what is your name",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.intent_key == "assistant.identity"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "introduce_self"


def test_runtime_candidate_adapter_rejects_non_allowlisted_exit_by_default() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-exit-not-allowlisted",
        transcript="exit.",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "intent_not_allowlisted:system.exit"
    assert result.intent_key == "system.exit"
    assert result.route_decision is None


def test_runtime_candidate_adapter_rejects_exit_even_when_requested_by_override() -> None:
    bundle = _bundle(
        runtime_candidates_enabled=True,
        allowlist=["assistant.identity", "system.current_time", "system.exit"],
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-exit-override",
        transcript="exit.",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "intent_not_allowlisted:system.exit"
    assert result.intent_key == "system.exit"
    assert result.route_decision is None


def test_runtime_candidate_adapter_falls_back_for_ambiguous_show_shell_outputs() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-ambiguous-show",
        transcript="So shall.",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "fallback_required:no_match"
    assert result.route_decision is None


def test_runtime_candidate_adapter_refuses_when_full_v2_pipeline_is_active() -> None:
    bundle = _bundle(
        runtime_candidates_enabled=True,
        enabled=True,
        mode="v2",
        command_first_enabled=True,
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-full-v2-active",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "runtime_candidates_not_safe"
    assert bundle.settings.command_pipeline_can_run is True


def test_runtime_candidate_adapter_accepts_safe_polish_vosk_shadow_result() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-polish-time",
        result_metadata=_safe_vosk_shadow_result(
            transcript="która jest godzina",
            normalized_text="ktora jest godzina",
            language="pl",
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
        metadata={"source": "unit_test"},
    )

    assert result.accepted is True
    assert result.intent_key == "system.current_time"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "ask_time"
    assert result.metadata["candidate_source"] == "vosk_shadow_asr_result"
    assert result.metadata["runtime_candidate"] is True
    assert result.metadata["vosk_shadow_result"]["raw_pcm_included"] is False


def test_runtime_candidate_adapter_accepts_safe_english_vosk_shadow_result() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-english-identity",
        result_metadata=_safe_vosk_shadow_result(
            transcript="what is your name",
            normalized_text="what is your name",
            language="en",
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.intent_key == "assistant.identity"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "introduce_self"


def test_runtime_candidate_adapter_rejects_unmatched_vosk_shadow_result() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-unmatched",
        result_metadata=_safe_vosk_shadow_result(
            transcript="is | czas",
            normalized_text="is czas",
            language="unknown",
            recognized=False,
            command_matched=False,
            confidence=0.0,
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "vosk_shadow_result_not_recognized"
    assert result.route_decision is None
    assert result.metadata["runtime_candidate_source_safe"] is False


def test_runtime_candidate_adapter_rejects_unsafe_vosk_shadow_result() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-unsafe",
        result_metadata=_safe_vosk_shadow_result(
            transcript="what time is it",
            normalized_text="what time is it",
            language="en",
            action_executed=True,
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "unsafe_vosk_shadow_result:action_executed"
    assert result.route_decision is None


def test_runtime_candidate_adapter_keeps_allowlist_for_vosk_shadow_exit() -> None:
    bundle = _bundle(runtime_candidates_enabled=True)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-exit-not-allowlisted",
        result_metadata=_safe_vosk_shadow_result(
            transcript="exit",
            normalized_text="exit",
            language="en",
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "intent_not_allowlisted:system.exit"
    assert result.intent_key == "system.exit"
    assert result.route_decision is None

def test_runtime_candidate_adapter_accepts_allowlisted_help_command() -> None:
    bundle = _bundle(
        runtime_candidates_enabled=True,
        allowlist=[
            "assistant.identity",
            "system.current_time",
            "visual_shell.show_desktop",
            "visual_shell.show_shell",
            "assistant.help",
        ],
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-help",
        transcript="help",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.intent_key == "assistant.help"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "help"
    assert result.route_decision.tool_invocations[0].tool_name == "system.help"
    assert result.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_adapter_accepts_memory_guided_start_transcript_override() -> None:
    bundle = _bundle(
        runtime_candidates_enabled=True,
        allowlist=["memory.guided_start", "memory.list"],
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-memory-guided-start",
        transcript="remember something",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.reason == "accepted"
    assert result.intent_key == "memory.guided_start"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "memory_store"
    assert result.route_decision.tool_invocations[0].tool_name == "memory.guided_start"
    assert result.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_adapter_accepts_memory_list_transcript_override() -> None:
    bundle = _bundle(
        runtime_candidates_enabled=True,
        allowlist=["memory.guided_start", "memory.list"],
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-candidate-memory-list",
        transcript="co zapamiętałaś",
        language_hint=CommandLanguage.POLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.reason == "accepted"
    assert result.intent_key == "memory.list"
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "memory_list"
    assert result.route_decision.tool_invocations[0].tool_name == "memory.list"
    assert result.route_decision.metadata["llm_prevented"] is True
