from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _PROJECT_ROOT / "modules" / "runtime" / "main_loop" / "resume_policy.py"

if "modules.runtime.main_loop" not in sys.modules:
    package = types.ModuleType("modules.runtime.main_loop")
    package.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = package

spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.resume_policy",
    _MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load resume_policy module for tests.")

_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _module
spec.loader.exec_module(_module)
ResumePolicyService = _module.ResumePolicyService


class _AssistantProbe:
    def __init__(self) -> None:
        self.shutdown_requested = False
        self.pending_confirmation = None
        self.pending_follow_up = None
        self._last_response_delivery_snapshot: dict[str, object] | None = None
        self._last_resume_policy_snapshot: dict[str, object] = {}


class ResumePolicyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ResumePolicyService()

    def test_follow_up_wins_when_pending_follow_up_exists(self) -> None:
        assistant = _AssistantProbe()
        assistant.pending_follow_up = {"topic": "timer"}
        assistant._last_response_delivery_snapshot = {
            "delivered": True,
            "full_text_chars": 24,
            "route_kind": "action",
            "source": "action_flow",
        }

        decision = self.service.decide(assistant)

        self.assertEqual(decision.action, "follow_up")
        self.assertEqual(decision.reason, "pending_follow_up")
        self.assertTrue(decision.follow_up_required)
        self.assertEqual(assistant._last_resume_policy_snapshot["action"], "follow_up")

    def test_grace_used_after_delivered_response_without_pending_follow_up(self) -> None:
        assistant = _AssistantProbe()
        assistant._last_response_delivery_snapshot = {
            "delivered": True,
            "full_text_chars": 42,
            "route_kind": "dialogue",
            "source": "dialogue_flow",
        }

        decision = self.service.decide(assistant)

        self.assertEqual(decision.action, "grace")
        self.assertEqual(decision.reason, "response_delivered")
        self.assertTrue(decision.response_delivered)
        self.assertEqual(assistant._last_resume_policy_snapshot["action"], "grace")

    def test_standby_used_after_silent_non_delivered_response(self) -> None:
        assistant = _AssistantProbe()
        assistant._last_response_delivery_snapshot = {
            "delivered": False,
            "full_text_chars": 0,
            "route_kind": "action",
            "source": "action_flow",
        }

        decision = self.service.decide(assistant)

        self.assertEqual(decision.action, "standby")
        self.assertEqual(decision.reason, "no_delivered_response")
        self.assertFalse(decision.response_delivered)
        self.assertEqual(assistant._last_resume_policy_snapshot["action"], "standby")


if __name__ == "__main__":
    unittest.main()