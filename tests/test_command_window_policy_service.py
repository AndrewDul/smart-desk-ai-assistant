from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _PROJECT_ROOT / "modules" / "runtime" / "main_loop" / "command_window_policy.py"

if "modules.runtime.main_loop" not in sys.modules:
    package = types.ModuleType("modules.runtime.main_loop")
    package.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = package

spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.command_window_policy",
    _MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load command_window_policy module for tests.")

_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _module
spec.loader.exec_module(_module)
CommandWindowPolicyService = _module.CommandWindowPolicyService


class _VoiceSessionProbe:
    active_listen_window_seconds = 7.5


class _AssistantProbe:
    def __init__(self) -> None:
        self.settings = {"voice_input": {"active_window_retry_min_remaining_seconds": 0.35}}
        self.voice_session = _VoiceSessionProbe()
        self._last_command_window_policy_snapshot: dict[str, object] = {}


class CommandWindowPolicyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CommandWindowPolicyService()

    def test_initial_window_decision_uses_capped_active_window(self) -> None:
        assistant = _AssistantProbe()

        decision = self.service.initial_window_decision(assistant)

        self.assertEqual(decision.action, "open_initial")
        self.assertEqual(decision.reason, "wake_accepted")
        self.assertEqual(decision.window_seconds, 6.5)
        self.assertEqual(assistant._last_command_window_policy_snapshot["action"], "open_initial")

    def test_empty_capture_retry_allowed_when_time_and_attempt_budget_remain(self) -> None:
        assistant = _AssistantProbe()

        decision = self.service.decide_after_empty_capture(
            assistant,
            phase="follow_up",
            attempt_number=2,
            remaining_seconds=1.2,
        )

        self.assertEqual(decision.action, "retry")
        self.assertEqual(decision.detail, "awaiting_followup_after_silence")
        self.assertEqual(decision.retry_limit, 3)

    def test_ignored_transcript_standby_when_attempt_budget_is_exceeded(self) -> None:
        assistant = _AssistantProbe()

        decision = self.service.decide_after_ignored_transcript(
            assistant,
            phase="grace",
            attempt_number=2,
            remaining_seconds=1.0,
        )

        self.assertEqual(decision.action, "standby")
        self.assertEqual(decision.reason, "grace_ignored_transcript")
        self.assertEqual(decision.retry_limit, 1)


if __name__ == "__main__":
    unittest.main()