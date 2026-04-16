from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _PROJECT_ROOT / "modules" / "runtime" / "main_loop" / "active_window.py"

if "modules.core.assistant" not in sys.modules:
    assistant_stub = types.ModuleType("modules.core.assistant")
    assistant_stub.CoreAssistant = object
    sys.modules["modules.core.assistant"] = assistant_stub

if "modules.runtime.main_loop" not in sys.modules:
    package = types.ModuleType("modules.runtime.main_loop")
    package.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = package

spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.active_window",
    _MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load active_window module for tests.")

_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _module
spec.loader.exec_module(_module)
_rearm_after_command = _module._rearm_after_command


class _StateFlags:
    pass


class _AssistantProbe:
    pass


class ActiveWindowResumePolicyTests(unittest.TestCase):
    def test_rearm_after_command_returns_to_wake_gate_for_standby_decision(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()
        calls: list[tuple[str, str]] = []

        original_service = _module._RESUME_POLICY_SERVICE
        original_follow_up = _module._start_follow_up_window
        original_grace = _module._start_grace_window
        original_return = _module._return_to_wake_gate

        class _Decision:
            action = "standby"
            reason = "no_delivered_response"

        class _Service:
            def decide(self, assistant_obj):
                return _Decision()

        def _fake_follow_up(*args, **kwargs):
            calls.append(("follow_up", ""))

        def _fake_grace(*args, **kwargs):
            calls.append(("grace", ""))

        def _fake_return(*args, **kwargs):
            calls.append(("standby", kwargs.get("reason", "")))

        try:
            _module._RESUME_POLICY_SERVICE = _Service()
            _module._start_follow_up_window = _fake_follow_up
            _module._start_grace_window = _fake_grace
            _module._return_to_wake_gate = _fake_return

            _rearm_after_command(assistant, state_flags)
        finally:
            _module._RESUME_POLICY_SERVICE = original_service
            _module._start_follow_up_window = original_follow_up
            _module._start_grace_window = original_grace
            _module._return_to_wake_gate = original_return

        self.assertEqual(calls, [("standby", "no_delivered_response")])


if __name__ == "__main__":
    unittest.main()