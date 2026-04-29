from modules.core.voice_engine import VoiceTurnInput
from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.contracts import RouteKind
from modules.runtime.voice_engine_v2 import (
    RuntimeCandidateExecutionPlanBuilder,
    build_voice_engine_v2_runtime,
)


_RUNTIME_CANDIDATE_ALLOWLIST = [
    "assistant.identity",
    "system.current_time",
    "visual_shell.show_desktop",
    "visual_shell.show_shell",
]


def _turn_result(
    transcript: str,
    *,
    language: CommandLanguage = CommandLanguage.ENGLISH,
):
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "runtime_candidates_enabled": True,
                "runtime_candidate_intent_allowlist": list(_RUNTIME_CANDIDATE_ALLOWLIST),
            }
        }
    )
    return bundle.engine.process_shadow_turn(
        VoiceTurnInput(
            turn_id=f"turn-{transcript.replace(' ', '-')}",
            transcript=transcript,
            language_hint=language,
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
        )
    )


def test_runtime_candidate_executor_builds_identity_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("what is your name")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="what is your name",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "introduce_self"
    assert plan.route_decision.tool_invocations[0].tool_name == "assistant.introduce"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "assistant.identity"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_current_time_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("what time is it")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="what time is it",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "ask_time"
    assert plan.route_decision.tool_invocations[0].tool_name == "clock.time"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "system.current_time"


def test_runtime_candidate_executor_builds_show_desktop_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("show desktop")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="show desktop",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "show_desktop"
    assert plan.route_decision.tool_invocations[0].tool_name == "visual_shell.show_desktop"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert plan.route_decision.metadata["legacy_action"] == "show_desktop"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_hide_desktop_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("hide desktop")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="hide desktop",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "show_shell"
    assert plan.route_decision.tool_invocations[0].tool_name == "visual_shell.show_shell"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "visual_shell.show_shell"
    assert plan.route_decision.metadata["legacy_action"] == "show_shell"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_polish_hide_desktop_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("schowaj pulpit", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="schowaj pulpit",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "show_shell"
    assert plan.route_decision.tool_invocations[0].tool_name == "visual_shell.show_shell"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "visual_shell.show_shell"


def test_runtime_candidate_executor_rejects_exit_even_if_recognized() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("exit.")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="exit.",
        metadata={"source": "unit_test"},
    )

    assert plan is None
    assert builder.supported_intents == (
        "assistant.identity",
        "system.current_time",
        "visual_shell.show_desktop",
        "visual_shell.show_shell",
    )
