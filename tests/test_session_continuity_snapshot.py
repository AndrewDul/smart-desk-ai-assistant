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

_start_follow_up_window = _module._start_follow_up_window
_start_grace_window = _module._start_grace_window
_return_to_wake_gate = _module._return_to_wake_gate
_prime_command_window_after_wake = _module._prime_command_window_after_wake


class _StateFlags:
    def __init__(self) -> None:
        self.active_phase = "command"
        self.hide_calls = 0
        self.prefetched_cleared = 0
        self.rearm_seconds = 0.0

    def set_active_phase(self, phase: str) -> None:
        self.active_phase = str(phase)

    def hide_standby_banner(self) -> None:
        self.hide_calls += 1

    def clear_prefetched_command(self) -> None:
        self.prefetched_cleared += 1

    def arm_wake_rearm(self, seconds: float) -> None:
        self.rearm_seconds = float(seconds)


class _VoiceSessionProbe:
    def __init__(self) -> None:
        self.open_calls: list[dict[str, object]] = []
        self.standby_calls: list[dict[str, object]] = []

    def open_active_window(self, *, seconds: float, phase: str, input_owner: str, detail: str) -> None:
        self.open_calls.append(
            {
                "seconds": seconds,
                "phase": phase,
                "input_owner": input_owner,
                "detail": detail,
            }
        )

    def transition_to_standby(self, *, detail: str, phase: str, input_owner: str, close_active_window: bool) -> None:
        self.standby_calls.append(
            {
                "detail": detail,
                "phase": phase,
                "input_owner": input_owner,
                "close_active_window": close_active_window,
            }
        )


class _AssistantProbe:
    def __init__(self) -> None:
        self.voice_session = _VoiceSessionProbe()
        self.settings = {"voice_input": {}}
        self._last_resume_policy_snapshot = {
            "action": "follow_up",
            "reason": "pending_follow_up",
            "pending_kind": "follow_up",
            "pending_type": "capture_name",
            "pending_language": "en",
        }
        self._last_command_window_policy_snapshot = {
            "action": "open_initial",
            "reason": "wake_accepted",
        }
        self._last_session_continuity_snapshot: dict[str, object] = {}


class SessionContinuitySnapshotTests(unittest.TestCase):
    def test_follow_up_window_stores_structured_continuity_snapshot(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        _start_follow_up_window(assistant, state_flags)

        snapshot = assistant._last_session_continuity_snapshot
        self.assertEqual(snapshot["action"], "follow_up")
        self.assertEqual(snapshot["phase"], "follow_up")
        self.assertEqual(snapshot["reason"], "pending_follow_up")
        self.assertEqual(snapshot["pending_kind"], "follow_up")
        self.assertEqual(snapshot["pending_type"], "capture_name")
        self.assertGreater(float(snapshot["window_seconds"]), 0.0)

    def test_grace_window_stores_structured_continuity_snapshot(self) -> None:
        assistant = _AssistantProbe()
        assistant._last_resume_policy_snapshot = {
            "action": "grace",
            "reason": "response_delivered",
        }
        state_flags = _StateFlags()

        _start_grace_window(assistant, state_flags)

        snapshot = assistant._last_session_continuity_snapshot
        self.assertEqual(snapshot["action"], "grace")
        self.assertEqual(snapshot["phase"], "grace")
        self.assertEqual(snapshot["reason"], "response_delivered")
        self.assertGreater(float(snapshot["window_seconds"]), 0.0)

    def test_return_to_wake_gate_stores_standby_continuity_snapshot(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        original_prepare = _module._prepare_for_standby_capture
        try:
            _module._prepare_for_standby_capture = lambda *args, **kwargs: None
            _return_to_wake_gate(assistant, state_flags, reason="no_delivered_response")
        finally:
            _module._prepare_for_standby_capture = original_prepare

        snapshot = assistant._last_session_continuity_snapshot
        self.assertEqual(snapshot["action"], "standby")
        self.assertEqual(snapshot["phase"], "wake_gate")
        self.assertEqual(snapshot["reason"], "no_delivered_response")
        self.assertEqual(float(snapshot["window_seconds"]), 0.0)

    def test_prime_command_window_after_wake_stores_command_window_continuity_snapshot(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        original_service = _module._COMMAND_WINDOW_POLICY_SERVICE
        original_prepare = _module._prepare_for_active_capture

        class _Decision:
            action = "open_initial"
            reason = "wake_accepted"
            window_seconds = 5.8
            detail = "awaiting_command_after_wake"

        class _Service:
            def initial_window_decision(self, assistant_obj):
                return _Decision()

        try:
            _module._COMMAND_WINDOW_POLICY_SERVICE = _Service()
            _module._prepare_for_active_capture = lambda *args, **kwargs: None
            _prime_command_window_after_wake(assistant, state_flags)
        finally:
            _module._COMMAND_WINDOW_POLICY_SERVICE = original_service
            _module._prepare_for_active_capture = original_prepare

        snapshot = assistant._last_session_continuity_snapshot
        self.assertEqual(snapshot["action"], "command_window_open")
        self.assertEqual(snapshot["phase"], "command")
        self.assertEqual(snapshot["reason"], "wake_accepted")
        self.assertEqual(float(snapshot["window_seconds"]), 5.8)


if __name__ == "__main__":
    unittest.main()