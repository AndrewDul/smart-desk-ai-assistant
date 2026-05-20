from modules.core.voice_engine import VoiceTurnInput
from modules.core.flows.action_flow.memory_actions_mixin import ActionMemoryActionsMixin
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
    "memory.recall",
    "memory.forget",
    "mobile_base.drive_mode",
    "system.current_time",
    "system.current_date",
    "system.temperature",
    "system.battery",
    "system.status",
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

ENGLISH_PEOPLE_RECALL_ALIASES = [
    "who do you know",
    "who you know",
    "who do you remember",
    "who can you remember",
    "who is in your memory",
    "show people you know",
    "show known people",
    "list known people",
    "list people you know",
    "tell me who you know",
    "what people do you know",
    "which people do you know",
    "known people",
]

ENGLISH_OBJECT_RECALL_ALIASES = [
    "what objects do you know",
    "what object do you know",
    "what objects do you need",
    "what object do you need",
    "what objects you know",
    "what object you know",
    "what objects",
    "what object",
    "what objects do you remember",
    "what object do you remember",
    "what items do you know",
    "what item do you know",
    "what items do you remember",
    "what item do you remember",
    "what things do you know",
    "what thing do you know",
    "what things do you remember",
    "what thing do you remember",
    "which objects do you know",
    "which items do you know",
    "which things do you know",
    "show objects you know",
    "show known objects",
    "show my objects",
    "show remembered objects",
    "show items you know",
    "show known items",
    "show things you know",
    "list objects",
    "list known objects",
    "list my objects",
    "list remembered objects",
    "list items",
    "list known items",
    "list things",
    "known objects",
    "known items",
    "remembered objects",
    "remembered items",
    "objects you know",
    "items you know",
    "things you know",
    "what object now",
]

POLISH_PEOPLE_RECALL_ALIASES = [
    "kogo znasz",
    "kogo znas",
    "kogo z nasz",
    "kogo z nas",
    "jakie osoby znasz",
    "jakie osoby pamiętasz",
    "jakie osoby pamietasz",
    "kogo pamiętasz",
    "kogo pamietasz",
    "pokaż osoby które znasz",
    "pokaz osoby ktore znasz",
    "pokaż znane osoby",
    "pokaz znane osoby",
    "lista osób",
    "lista osob",
    "lista znanych osób",
    "lista znanych osob",
    "osoby które znasz",
    "osoby ktore znasz",
    "znane osoby",
]

POLISH_OBJECT_RECALL_ALIASES = [
    "jakie obiekty znasz",
    "jakie obiektyznaz",
    "jakie obiekty z nasz",
    "jakie rzeczy znasz",
    "jakie przedmioty znasz",
    "jakie obiekty pamiętasz",
    "jakie obiekty pamietasz",
    "jakie rzeczy pamiętasz",
    "jakie rzeczy pamietasz",
    "jakie przedmioty pamiętasz",
    "jakie przedmioty pamietasz",
    "pokaż obiekty",
    "pokaz obiekty",
    "pokaż znane obiekty",
    "pokaz znane obiekty",
    "pokaż moje obiekty",
    "pokaz moje obiekty",
    "pokaż rzeczy które znasz",
    "pokaz rzeczy ktore znasz",
    "pokaż przedmioty które znasz",
    "pokaz przedmioty ktore znasz",
    "lista obiektów",
    "lista obiektow",
    "lista rzeczy",
    "lista przedmiotów",
    "lista przedmiotow",
    "znane obiekty",
    "znane rzeczy",
    "znane przedmioty",
    "obiekty które znasz",
    "obiekty ktore znasz",
    "rzeczy które znasz",
    "rzeczy ktore znasz",
    "przedmioty które znasz",
    "przedmioty ktore znasz",
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


def _assert_memory_recall_aliases(
    aliases: list[str],
    *,
    language: CommandLanguage,
    gallery_kind: str,
) -> None:
    grammar = build_default_command_grammar()
    builder = RuntimeCandidateExecutionPlanBuilder()

    for alias in aliases:
        result = grammar.match(alias)
        assert result.is_match, alias
        assert result.intent_key == "memory.recall", alias
        assert result.language == language, alias

        plan = builder.build_plan_from_intent(
            turn_id=f"turn-{alias.replace(' ', '-')}",
            intent_key=result.intent_key or "",
            transcript=alias,
            language=result.language.value,
            confidence=result.confidence,
            matched_phrase=result.matched_phrase,
        )

        assert plan is not None, alias
        assert plan.route_decision.kind == RouteKind.ACTION, alias
        assert plan.route_decision.language == language.value, alias
        assert plan.route_decision.primary_intent == "memory_recall", alias
        assert plan.route_decision.metadata["llm_prevented"] is True, alias
        invocation = plan.route_decision.tool_invocations[0]
        assert invocation.tool_name == "memory.recall", alias
        assert invocation.payload["key"] == alias, alias
        assert (
            ActionMemoryActionsMixin._memory_gallery_kind_from_query(alias)
            == gallery_kind
        ), alias


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
        "memory.forget",
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
        "system.status",
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
    turn = _turn_result("show me the time", language=CommandLanguage.ENGLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="show me the time",
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


def test_runtime_candidate_executor_builds_object_memory_enrollment_payload() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("zapamiętaj ten telefon", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="zapamiętaj ten telefon",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_store"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.guided_start"
    assert plan.route_decision.tool_invocations[0].payload == {
        "guided": True,
        "object_enrollment": True,
        "object_hint": "telefon",
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
        ("open diagnostics", CommandLanguage.ENGLISH, "feedback.on", "feedback_on"),
        ("show system status", CommandLanguage.ENGLISH, "feedback.on", "feedback_on"),
        ("system status", CommandLanguage.ENGLISH, "feedback.on", "feedback_on"),
        ("show llm status", CommandLanguage.ENGLISH, "feedback.on", "feedback_on"),
        ("feedback off", CommandLanguage.ENGLISH, "feedback.off", "feedback_off"),
        ("status", CommandLanguage.ENGLISH, "system.status", "status"),
        ("uruchom feedback", CommandLanguage.POLISH, "feedback.on", "feedback_on"),
        ("pokaż diagnostykę", CommandLanguage.POLISH, "feedback.on", "feedback_on"),
        ("pokaż status systemu", CommandLanguage.POLISH, "feedback.on", "feedback_on"),
        ("pokaż logi", CommandLanguage.POLISH, "feedback.on", "feedback_on"),
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


def test_runtime_candidate_executor_routes_known_objects_query_to_memory_recall() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("jakie obiekty znasz", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="jakie obiekty znasz",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_recall"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.recall"
    assert plan.route_decision.tool_invocations[0].payload["key"] == "jakie obiekty znasz"
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_english_people_recall_aliases_route_to_memory_recall() -> None:
    _assert_memory_recall_aliases(
        ENGLISH_PEOPLE_RECALL_ALIASES,
        language=CommandLanguage.ENGLISH,
        gallery_kind="people",
    )


def test_english_object_recall_aliases_route_to_memory_recall() -> None:
    _assert_memory_recall_aliases(
        ENGLISH_OBJECT_RECALL_ALIASES,
        language=CommandLanguage.ENGLISH,
        gallery_kind="objects",
    )


def test_polish_people_recall_aliases_route_to_memory_recall() -> None:
    _assert_memory_recall_aliases(
        POLISH_PEOPLE_RECALL_ALIASES,
        language=CommandLanguage.POLISH,
        gallery_kind="people",
    )


def test_polish_object_recall_aliases_route_to_memory_recall() -> None:
    _assert_memory_recall_aliases(
        POLISH_OBJECT_RECALL_ALIASES,
        language=CommandLanguage.POLISH,
        gallery_kind="objects",
    )


def test_runtime_candidate_executor_routes_forget_person_with_payload() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("zapomnij osobę Tomek", language=CommandLanguage.POLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="zapomnij osobę Tomek",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.kind == RouteKind.ACTION
    assert plan.route_decision.language == "pl"
    assert plan.route_decision.primary_intent == "memory_forget"
    assert plan.route_decision.tool_invocations[0].tool_name == "memory.forget"
    assert plan.route_decision.tool_invocations[0].payload == {
        "key": "tomek",
        "query": "tomek",
        "entity_type": "person",
    }
    assert plan.route_decision.metadata["llm_prevented"] is True


def test_runtime_candidate_executor_routes_forget_object_with_payload() -> None:
    builder = RuntimeCandidateExecutionPlanBuilder()
    turn = _turn_result("forget object Vape", language=CommandLanguage.ENGLISH)

    plan = builder.build_plan(
        turn_result=turn,
        transcript="forget object Vape",
        metadata={"source": "unit_test"},
    )

    assert plan is not None
    assert plan.route_decision.language == "en"
    assert plan.route_decision.primary_intent == "memory_forget"
    assert plan.route_decision.tool_invocations[0].payload == {
        "key": "vape",
        "query": "vape",
        "entity_type": "object",
    }
    assert plan.route_decision.metadata["llm_prevented"] is True
