from __future__ import annotations

import unittest

from modules.core.flows.action_flow.orchestrator import ActionFlowOrchestrator
from modules.core.flows.action_flow.models import ResolvedAction, SkillRequest
from modules.runtime.contracts import RouteDecision, RouteKind


class _FakeAssistant:
    def __init__(self) -> None:
        self.settings = {"streaming": {"max_display_chars_per_line": 20}}

    def _normalize_lang(self, language: str) -> str:
        return str(language or "en").strip().lower() or "en"


class _RequestAwareActionFlow(ActionFlowOrchestrator):
    def _resolve_action(self, route: RouteDecision) -> ResolvedAction:
        return ResolvedAction(
            name="help",
            payload={},
            source="route.primary_intent",
            confidence=route.confidence,
            route_kind=route.kind.value,
            primary_intent=route.primary_intent,
        )

    def _handle_help(self, *, route, language: str, payload, resolved, request: SkillRequest):
        return {
            "handled": True,
            "response_delivered": False,
            "status": "request_seen",
            "metadata": {
                "request_action": request.action,
                "request_turn_id": request.turn_id,
                "request_language": request.language,
            },
        }


class ActionHandlerRequestBridgeTests(unittest.TestCase):
    def test_execute_passes_skill_request_to_request_aware_handler(self) -> None:
        flow = _RequestAwareActionFlow(_FakeAssistant())
        route = RouteDecision(
            turn_id="turn-request-aware",
            raw_text="help",
            normalized_text="help",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.91,
            primary_intent="help",
        )

        handled = flow.execute(route=route, language="en")

        self.assertTrue(handled)
        self.assertIsNotNone(flow._last_skill_result)
        self.assertEqual(flow._last_skill_result.status, "request_seen")
        self.assertEqual(flow._last_skill_result.metadata["request_action"], "help")
        self.assertEqual(flow._last_skill_result.metadata["request_turn_id"], "turn-request-aware")
        self.assertEqual(flow._last_skill_result.metadata["request_language"], "en")


if __name__ == "__main__":
    unittest.main()