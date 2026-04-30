from dataclasses import dataclass, field
from typing import Any

from modules.core.session.fast_command_lane import FastCommandLane
from modules.core.session.visual_shell_command_lane import VisualShellCommandLane
from modules.presentation.visual_shell.controller import VisualShellController
from modules.presentation.visual_shell.transport import InMemoryVisualShellTransport


class FailingVisualShellTransport:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []

    def send(self, message: dict[str, object]) -> bool:
        self.sent_messages.append(dict(message))
        return False


@dataclass(slots=True)
class FakeVoiceSession:
    states: list[dict[str, str]] = field(default_factory=list)

    def set_state(self, state: str, *, detail: str = "") -> None:
        self.states.append({"state": state, "detail": detail})


@dataclass(slots=True)
class FakeActionFlow:
    calls: int = 0

    def execute(self, *args: Any, **kwargs: Any) -> bool:
        self.calls += 1
        return True


@dataclass(slots=True)
class FakeAssistant:
    voice_session: FakeVoiceSession = field(default_factory=FakeVoiceSession)
    action_flow: FakeActionFlow = field(default_factory=FakeActionFlow)
    last_language: str = "pl"
    pending_confirmation: object | None = object()
    pending_follow_up: object | None = object()
    committed_languages: list[str] = field(default_factory=list)
    delivered_responses: list[dict[str, Any]] = field(default_factory=list)
    cleared_context: bool = False
    _last_fast_lane_route_snapshot: dict[str, Any] = field(default_factory=dict)
    _last_visual_shell_command_trace: dict[str, Any] = field(default_factory=dict)

    def _normalize_lang(self, language: str | None) -> str:
        return str(language or "en").strip().lower() or "en"

    def _commit_language(self, language: str) -> str:
        normalized = self._normalize_lang(language)
        self.committed_languages.append(normalized)
        self.last_language = normalized
        return normalized

    def _clear_interaction_context(self, *, close_active_window: bool = False) -> None:
        self.cleared_context = True
        self.pending_confirmation = None
        self.pending_follow_up = None

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind: object,
        source: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        self.delivered_responses.append(
            {
                "text": text,
                "language": language,
                "route_kind": route_kind,
                "source": source,
                "metadata": dict(metadata or {}),
            }
        )
        return True


def _prepared(text: str, *, language: str = "pl") -> dict[str, object]:
    return {
        "raw_text": text,
        "routing_text": text,
        "normalized_text": text.lower(),
        "language": language,
    }


def test_visual_shell_runtime_lane_handles_desktop_command_without_action_flow() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)
    lane = VisualShellCommandLane(controller=controller)
    assistant = FakeAssistant()

    result = lane.try_handle(
        prepared=_prepared("gdzie mój pulpit"),
        assistant=assistant,
    )

    assert result is True
    assert assistant.cleared_context is True
    assert assistant.action_flow.calls == 0
    assert assistant.voice_session.states == [
        {"state": "routing", "detail": "visual_shell_lane:show_desktop"}
    ]
    assert assistant._last_fast_lane_route_snapshot["route_kind"] == "action"
    assert assistant._last_fast_lane_route_snapshot["primary_intent"] == (
        "visual_shell.show_desktop"
    )
    assert assistant._last_fast_lane_route_snapshot["route_metadata"]["lane"] == (
        "visual_shell_command"
    )
    assert assistant._last_fast_lane_route_snapshot["route_metadata"]["llm_prevented"] is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        }
    ]

    trace = assistant._last_visual_shell_command_trace
    assert trace["heard_text"] == "gdzie mój pulpit"
    assert trace["normalized_text"] == "gdzie moj pulpit"
    assert trace["router_match"] is True
    assert trace["matched_rule"] == "show_desktop"
    assert trace["visual_action"] == "SHOW_DESKTOP"
    assert trace["transport_result"] == "ok"
    assert trace["llm_prevented"] is True
    assert trace["response_emitted"] is True
    assert trace["language"] == "pl"
    assert trace["reason"] == "handled"
    assert trace["router_match_ms"] >= 0.0
    assert trace["controller_ms"] >= 0.0
    assert trace["response_ms"] >= 0.0
    assert trace["non_response_ms"] >= 0.0
    assert trace["elapsed_ms"] >= trace["response_ms"]

    assert assistant.delivered_responses
    assert assistant.delivered_responses[0]["source"] == "visual_shell_command_lane"
    assert assistant.delivered_responses[0]["metadata"]["action"] == "SHOW_DESKTOP"
    assert assistant.delivered_responses[0]["metadata"]["matched_rule"] == "show_desktop"
    assert assistant.delivered_responses[0]["metadata"]["llm_prevented"] is True


def test_visual_shell_runtime_lane_returns_none_for_non_visual_command() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)
    lane = VisualShellCommandLane(controller=controller)
    assistant = FakeAssistant()

    result = lane.try_handle(
        prepared=_prepared("opowiedz mi o czarnych dziurach"),
        assistant=assistant,
    )

    assert result is None
    assert transport.sent_messages == []
    assert assistant.action_flow.calls == 0

    trace = assistant._last_visual_shell_command_trace
    assert trace["heard_text"] == "opowiedz mi o czarnych dziurach"
    assert trace["normalized_text"] == "opowiedz mi o czarnych dziurach"
    assert trace["router_match"] is False
    assert trace["matched_rule"] == ""
    assert trace["visual_action"] == ""
    assert trace["transport_result"] == "not_attempted"
    assert trace["llm_prevented"] is False
    assert trace["response_emitted"] is False
    assert trace["reason"] == "no_visual_match"
    assert trace["router_match_ms"] >= 0.0
    assert trace["controller_ms"] == 0.0
    assert trace["response_ms"] == 0.0
    assert trace["non_response_ms"] >= 0.0


def test_visual_shell_runtime_lane_does_not_fall_through_when_renderer_is_unavailable() -> None:
    transport = FailingVisualShellTransport()
    controller = VisualShellController(transport=transport)
    lane = VisualShellCommandLane(controller=controller)
    assistant = FakeAssistant()

    result = lane.try_handle(
        prepared=_prepared("pokaż twarz"),
        assistant=assistant,
    )

    assert result is True
    assert assistant.action_flow.calls == 0
    assert len(transport.sent_messages) == 2
    assert transport.sent_messages[0]["command"] == "HIDE_DESKTOP"
    assert transport.sent_messages[1]["command"] == "SHOW_FACE_CONTOUR"
    assert assistant.delivered_responses
    assert assistant.delivered_responses[0]["source"] == "visual_shell_command_lane"
    assert assistant.delivered_responses[0]["metadata"]["action"] == "SHOW_FACE_CONTOUR"

    trace = assistant._last_visual_shell_command_trace
    assert trace["router_match"] is True
    assert trace["matched_rule"] == "show_face"
    assert trace["visual_action"] == "SHOW_FACE_CONTOUR"
    assert trace["transport_result"] == "failed"
    assert trace["llm_prevented"] is True
    assert trace["response_emitted"] is True
    assert trace["reason"] == "renderer_unavailable"
    assert trace["router_match_ms"] >= 0.0
    assert trace["controller_ms"] >= 0.0
    assert trace["response_ms"] >= 0.0
    assert trace["non_response_ms"] >= 0.0


def test_fast_command_lane_runs_visual_shell_lane_before_existing_action_flow() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)
    visual_lane = VisualShellCommandLane(controller=controller)
    fast_lane = FastCommandLane(visual_shell_lane=visual_lane)
    assistant = FakeAssistant()

    result = fast_lane.try_handle(
        prepared=_prepared("pokaż twarz"),
        assistant=assistant,
    )

    assert result is True
    assert assistant.action_flow.calls == 0
    assert assistant._last_fast_lane_route_snapshot["primary_intent"] == (
        "visual_shell.show_face_contour"
    )
    assert transport.sent_messages == [
        {
            "command": "HIDE_DESKTOP",
            "payload": {},
            "source": "nexa-voice-builtins",
        },
        {
            "command": "SHOW_FACE_CONTOUR",
            "payload": {},
            "source": "nexa-voice-builtins",
        },
    ]

    trace = assistant._last_visual_shell_command_trace
    assert trace["router_match"] is True
    assert trace["matched_rule"] == "show_face"
    assert trace["visual_action"] == "SHOW_FACE_CONTOUR"
    assert trace["transport_result"] == "ok"
    assert trace["llm_prevented"] is True
    assert trace["response_emitted"] is True
    assert trace["reason"] == "handled"


def test_visual_shell_runtime_lane_records_trace_when_acknowledgements_are_disabled() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)
    lane = VisualShellCommandLane(
        controller=controller,
        speak_acknowledgements_enabled=False,
    )
    assistant = FakeAssistant()

    result = lane.try_handle(
        prepared=_prepared("pokaż pulpit"),
        assistant=assistant,
    )

    assert result is True
    assert assistant.delivered_responses == []

    trace = assistant._last_visual_shell_command_trace
    assert trace["router_match"] is True
    assert trace["matched_rule"] == "show_desktop"
    assert trace["visual_action"] == "SHOW_DESKTOP"
    assert trace["transport_result"] == "ok"
    assert trace["llm_prevented"] is True
    assert trace["response_emitted"] is False
    assert trace["reason"] == "handled"