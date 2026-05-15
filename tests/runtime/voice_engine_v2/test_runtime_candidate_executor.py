from modules.core.voice_engine import VoiceTurnInput
from modules.devices.audio.command_asr.command_grammar import build_default_command_grammar
from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.contracts import RouteKind
from modules.runtime.voice_engine_v2 import (
    RuntimeCandidateExecutionPlanBuilder,
    build_voice_engine_v2_runtime,
)


_RUNTIME_CANDIDATE_ALLOWLIST = [
    "assistant.identity",
    "memory.guided_start",
    "memory.list",
    "mobile_base.drive_mode",
    "system.current_time",
    "system.current_date",
    "system.temperature",
    "system.battery",
    "visual_shell.show_desktop",
    "visual_shell.show_shell",
    "visual_shell.show_self",
    "visual_shell.show_eyes",
    "visual_shell.show_face",
    "visual_shell.look_at_user",
    "visual_shell.start_scanning",
    "visual_shell.return_to_idle",
    "visual_shell.show_temperature",
    "visual_shell.show_battery",
    "visual_shell.show_time",
    "visual_shell.show_date",
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


def _first_transcript_for_intent(
    intent_key: str,
    language: CommandLanguage,
) -> str:
    grammar = build_default_command_grammar()

    for phrase in grammar.phrases:
        if phrase.intent_key == intent_key and phrase.language == language:
            return phrase.phrase

    raise AssertionError(f"No {language.value} phrase found for {intent_key}")


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


def test_runtime_candidate_executor_builds_system_fast_line_routes() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()

    cases = [
        (
            "what is your battery",
            CommandLanguage.ENGLISH,
            "system.battery",
            "show_battery",
            "system.battery",
        ),
        (
            "tell me the cpu temperature",
            CommandLanguage.ENGLISH,
            "system.temperature",
            "show_temperature",
            "system.temperature",
        ),
        (
            "what is today's date",
            CommandLanguage.ENGLISH,
            "system.current_date",
            "show_date",
            "clock.date",
        ),
    ]

    for transcript, language, intent_key, legacy_action, tool_name in cases:
        turn = _turn_result(transcript, language=language)

        plan = builder.build_plan(
            turn_result=turn,
            transcript=transcript,
            metadata={"source": "unit_test"},
        )

        assert plan is not None
        assert plan.route_decision.kind == RouteKind.ACTION
        assert plan.route_decision.primary_intent == legacy_action
        assert plan.route_decision.tool_invocations[0].tool_name == tool_name
        assert plan.route_decision.metadata["voice_engine_intent_key"] == intent_key
        assert plan.route_decision.metadata["legacy_action"] == legacy_action
        assert plan.route_decision.metadata["llm_prevented"] is True


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


def test_runtime_candidate_executor_builds_calculator_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("ile to jest dwa plus dwa", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="ile to jest dwa plus dwa",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "calculate"
    assert plan.route_decision.tool_invocations[0].tool_name == "system.calculate"
    assert plan.route_decision.tool_invocations[0].payload == {
        "expression": "2 + 2",
        "result": "4",
        "source_text": "ile to jest dwa plus dwa",
    }
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "system.calculate"


def test_runtime_candidate_executor_builds_exit_action_flow_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("exit.")

    plan = builder.build_plan(
        turn_result=turn,
        transcript="exit.",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "exit"
    assert plan.route_decision.tool_invocations[0].tool_name == "system.exit"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "system.exit"

    assert builder.supported_intents == (
        "assistant.help",
        "assistant.identity",
        "break.start",
        "break.stop",
        "feedback.off",
        "feedback.on",
        "focus.offer",
        "focus.start",
        "focus.stop",
        "memory.guided_start",
        "memory.list",
        "memory.recall",
        "mobile_base.drive_mode",
        "mobile_base.stop",
        "reminder.guided_start",
        "reminder.time_answer",
        "system.battery",
        "system.calculate",
        "system.current_date",
        "system.current_time",
        "system.exit",
        "system.temperature",
        "visual_shell.look_at_user",
        "visual_shell.return_to_idle",
        "visual_shell.show_battery",
        "visual_shell.show_date",
        "visual_shell.show_desktop",
        "visual_shell.show_eyes",
        "visual_shell.show_face",
        "visual_shell.show_self",
        "visual_shell.show_shell",
        "visual_shell.show_temperature",
        "visual_shell.show_time",
        "visual_shell.start_scanning",
    )


def test_runtime_candidate_plan_maps_assistant_help_to_system_help_action() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn_result = _turn_result("help")

    plan = builder.build_plan(turn_result=turn_result, transcript="help")

    assert plan is not None
    assert plan.spec.voice_engine_intent_key == "assistant.help"
    assert plan.spec.legacy_action == "help"
    assert plan.spec.tool_name == "system.help"
    assert plan.route_decision.primary_intent == "help"
    assert plan.route_decision.tool_invocations[0].tool_name == "system.help"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "assistant.help"
    assert plan.route_decision.metadata["legacy_action"] == "help"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_extended_visual_shell_action_routes() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    cases = [
        ("show yourself", CommandLanguage.ENGLISH, "visual_shell.show_self", "show_self"),
        ("pokaż oczy", CommandLanguage.POLISH, "visual_shell.show_eyes", "show_eyes"),
        ("show face", CommandLanguage.ENGLISH, "visual_shell.show_face", "show_face_contour"),
        ("spójrz na mnie", CommandLanguage.POLISH, "visual_shell.look_at_user", "look_at_user"),
        ("scan room", CommandLanguage.ENGLISH, "visual_shell.start_scanning", "start_scanning"),
        ("wróć do chmury", CommandLanguage.POLISH, "visual_shell.return_to_idle", "return_to_idle"),
        ("show cpu temperature", CommandLanguage.ENGLISH, "visual_shell.show_temperature", "show_temperature"),
        ("pokaż baterię", CommandLanguage.POLISH, "visual_shell.show_battery", "show_battery"),
    ]

    for transcript, language, intent_key, legacy_action in cases:
        turn = _turn_result(transcript, language=language)

        plan = builder.build_plan(
            turn_result=turn,
            transcript=transcript,
            metadata={"source": "unit_test"},
        )

        assert plan is not None
        assert plan.route_decision.kind == RouteKind.ACTION
        assert plan.route_decision.primary_intent == legacy_action
        assert plan.route_decision.tool_invocations[0].tool_name == intent_key
        assert plan.route_decision.metadata["voice_engine_intent_key"] == intent_key
        assert plan.route_decision.metadata["legacy_action"] == legacy_action
        assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_visual_shell_show_time_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("show the time", language=CommandLanguage.ENGLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="show the time",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "show_visual_time"
    assert plan.route_decision.tool_invocations[0].tool_name == "visual_shell.show_time"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "visual_shell.show_time"
    assert plan.route_decision.metadata["legacy_action"] == "show_visual_time"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_visual_shell_show_date_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("show the date", language=CommandLanguage.ENGLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="show the date",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "show_visual_date"
    assert plan.route_decision.tool_invocations[0].tool_name == "visual_shell.show_date"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "visual_shell.show_date"
    assert plan.route_decision.metadata["legacy_action"] == "show_visual_date"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_memory_guided_start_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("zapamiętaj coś", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="zapamiętaj coś",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_store"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.guided_start"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "memory.guided_start"
    assert plan.route_decision.metadata["legacy_action"] == "memory_store"
    assert plan.route_decision.metadata["llm_prevented"] is True



def test_runtime_candidate_executor_builds_person_memory_enrollment_payload() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("zapamiętaj mnie", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="zapamiętaj mnie",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_store"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.guided_start"
    assert plan.route_decision.tool_invocations[0].payload == {
        "guided": True,
        "person_enrollment": True,
    }
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_memory_list_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("what do you remember", language=CommandLanguage.ENGLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="what do you remember",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "en"
    assert plan.route_decision.primary_intent == "memory_list"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.list"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "memory.list"
    assert plan.route_decision.metadata["legacy_action"] == "memory_list"
    assert plan.route_decision.metadata["llm_prevented"] is True

def test_runtime_candidate_executor_builds_feedback_mode_routes() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    cases = [
        ("feedback on", CommandLanguage.ENGLISH, "feedback.on", "feedback_on"),
        ("feedback off", CommandLanguage.ENGLISH, "feedback.off", "feedback_off"),
        ("uruchom feedback", CommandLanguage.POLISH, "feedback.on", "feedback_on"),
        ("zamknij feedback", CommandLanguage.POLISH, "feedback.off", "feedback_off"),
    ]

    for transcript, language, intent_key, legacy_action in cases:
        turn = _turn_result(transcript, language=language)

        plan = builder.build_plan(
            turn_result=turn,
            transcript=transcript,
            metadata={"source": "unit_test"},
        )

        assert plan is not None
        assert plan.route_decision.primary_intent == legacy_action
        assert plan.route_decision.tool_invocations[0].tool_name == intent_key
        assert plan.route_decision.metadata["voice_engine_intent_key"] == intent_key
        assert plan.route_decision.metadata["legacy_action"] == legacy_action
        assert plan.route_decision.metadata["llm_prevented"] is True



def test_runtime_candidate_executor_builds_mobile_base_drive_mode_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("drive mode", language=CommandLanguage.ENGLISH)
    plan = builder.build_plan(turn_result=turn, transcript="drive mode", metadata={"source": "unit_test"})
    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.primary_intent == "drive_mode_start"
    assert plan.route_decision.tool_invocations[0].tool_name == "mobile_base.drive_mode"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "mobile_base.drive_mode"
    assert plan.route_decision.metadata["legacy_action"] == "drive_mode_start"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_builds_polish_mobile_base_drive_mode_route() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("tryb sterowania", language=CommandLanguage.POLISH)
    plan = builder.build_plan(turn_result=turn, transcript="tryb sterowania", metadata={"source": "unit_test"})
    assert plan is not None
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "drive_mode_start"
    assert plan.route_decision.tool_invocations[0].tool_name == "mobile_base.drive_mode"
    assert plan.route_decision.metadata["voice_engine_intent_key"] == "mobile_base.drive_mode"


def test_runtime_candidate_executor_routes_known_people_query_to_memory_recall() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("kogo znasz", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="kogo znasz",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_recall"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.recall"
    assert plan.route_decision.tool_invocations[0].payload["key"] == "kogo znasz"
    assert plan.route_decision.metadata["llm_prevented"] is True
