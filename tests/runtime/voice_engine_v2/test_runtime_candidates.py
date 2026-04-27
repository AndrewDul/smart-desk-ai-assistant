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