from __future__ import annotations

from typing import Any

from modules.core.flows.action_flow import ActionFlowOrchestrator
from modules.runtime.contracts import (
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
)


class _FakeVisualShellLane:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def try_handle(self, *, prepared: dict[str, Any], assistant: Any) -> bool:
        self.calls.append(dict(prepared))
        assistant._last_visual_shell_command_trace = {
            "response_emitted": True,
            "reason": "handled",
            "transport_result": "ok",
            "visual_action": "SHOW_DESKTOP",
        }
        return True


class _FakeFastCommandLane:
    def __init__(self, visual_shell_lane: _FakeVisualShellLane) -> None:
        self.visual_shell_lane = visual_shell_lane


class _FakeAssistant:
    def __init__(self, visual_shell_lane: _FakeVisualShellLane) -> None:
        self.settings = {"streaming": {"max_display_chars_per_line": 20}}
        self.fast_command_lane = _FakeFastCommandLane(visual_shell_lane)
        self.turn_benchmark_service = None
        self.delivered_plans: list[Any] = []
        self._last_visual_shell_command_trace: dict[str, Any] = {}

    @staticmethod
    def _normalize_lang(language: str) -> str:
        return "pl" if str(language).lower().startswith("pl") else "en"

    def deliver_response_plan(self, *args: Any, **kwargs: Any) -> bool:
        self.delivered_plans.append((args, kwargs))
        return True


def _route(
    *,
    raw_text: str,
    language: str,
    primary_intent: str,
    tool_name: str,
    intent_key: str,
) -> RouteDecision:
    return RouteDecision(
        turn_id="turn-visual-shell",
        raw_text=raw_text,
        normalized_text=raw_text,
        language=language,
        kind=RouteKind.ACTION,
        confidence=0.98,
        primary_intent=primary_intent,
        intents=[
            IntentMatch(
                name=primary_intent,
                confidence=0.98,
                entities=[],
                requires_clarification=False,
                metadata={
                    "voice_engine_intent_key": intent_key,
                    "matched_phrase": raw_text,
                },
            )
        ],
        conversation_topics=[],
        tool_invocations=[
            ToolInvocation(
                tool_name=tool_name,
                payload={},
                reason="unit_test",
                confidence=0.98,
                execute_immediately=True,
            )
        ],
        notes=["unit_test"],
        metadata={
            "lane": "voice_engine_v2_runtime_candidate",
            "voice_engine_intent_key": intent_key,
            "matched_phrase": raw_text,
            "llm_prevented": True,
        },
    )


def test_action_flow_delegates_show_desktop_to_visual_shell_lane() -> None:
    visual_shell_lane = _FakeVisualShellLane()
    assistant = _FakeAssistant(visual_shell_lane)
    flow = ActionFlowOrchestrator(assistant)

    handled = flow.execute(
        route=_route(
            raw_text="show desktop",
            language="en",
            primary_intent="show_desktop",
            tool_name="visual_shell.show_desktop",
            intent_key="visual_shell.show_desktop",
        ),
        language="en",
    )

    assert handled is True
    assert visual_shell_lane.calls[0]["routing_text"] == "show desktop"
    assert visual_shell_lane.calls[0]["language"] == "en"
    assert flow._last_skill_result is not None
    assert flow._last_skill_result.action == "show_desktop"
    assert flow._last_skill_result.status == "accepted"


def test_action_flow_delegates_polish_hide_desktop_to_visual_shell_lane() -> None:
    visual_shell_lane = _FakeVisualShellLane()
    assistant = _FakeAssistant(visual_shell_lane)
    flow = ActionFlowOrchestrator(assistant)

    handled = flow.execute(
        route=_route(
            raw_text="schowaj pulpit",
            language="pl",
            primary_intent="show_shell",
            tool_name="visual_shell.show_shell",
            intent_key="visual_shell.show_shell",
        ),
        language="pl",
    )

    assert handled is True
    assert visual_shell_lane.calls[0]["routing_text"] == "schowaj pulpit"
    assert visual_shell_lane.calls[0]["language"] == "pl"
    assert flow._last_skill_result is not None
    assert flow._last_skill_result.action == "show_shell"
    assert flow._last_skill_result.status == "accepted"


def test_action_flow_delegates_extended_visual_shell_actions_to_visual_shell_lane() -> None:
    cases = [
        ("show yourself", "en", "show_face_contour", "visual_shell.show_face", "visual_shell.show_face"),
        ("pokaż twarz", "pl", "show_face_contour", "visual_shell.show_face", "visual_shell.show_face"),
        ("show face", "en", "show_face_contour", "visual_shell.show_face", "visual_shell.show_face"),
        ("wróć do chmury", "pl", "return_to_idle", "visual_shell.return_to_idle", "visual_shell.return_to_idle"),
        ("show temperature", "en", "show_temperature", "visual_shell.show_temperature", "visual_shell.show_temperature"),
        ("pokaż baterię", "pl", "show_battery", "visual_shell.show_battery", "visual_shell.show_battery"),
        ("show the time", "en", "show_visual_time", "visual_shell.show_time", "visual_shell.show_time"),
        ("show the date", "en", "show_visual_date", "visual_shell.show_date", "visual_shell.show_date"),
    ]

    for raw_text, language, primary_intent, tool_name, intent_key in cases:
        visual_shell_lane = _FakeVisualShellLane()
        assistant = _FakeAssistant(visual_shell_lane)
        flow = ActionFlowOrchestrator(assistant)

        handled = flow.execute(
            route=_route(
                raw_text=raw_text,
                language=language,
                primary_intent=primary_intent,
                tool_name=tool_name,
                intent_key=intent_key,
            ),
            language=language,
        )

        assert handled is True
        assert visual_shell_lane.calls[0]["routing_text"] == raw_text
        assert visual_shell_lane.calls[0]["language"] == language
        assert flow._last_skill_result is not None
        assert flow._last_skill_result.action == primary_intent
        assert flow._last_skill_result.status == "accepted"
