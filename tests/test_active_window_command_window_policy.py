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
_handle_no_speech_capture = _module._handle_no_speech_capture
_prime_command_window_after_wake = _module._prime_command_window_after_wake


class _StateFlags:
    def __init__(self) -> None:
        self.active_phase = "command"
        self.hide_calls = 0
        self.empty_capture_count = 0

    def set_active_phase(self, phase: str) -> None:
        self.active_phase = str(phase)

    def record_empty_capture(self) -> int:
        self.empty_capture_count += 1
        return self.empty_capture_count

    def hide_standby_banner(self) -> None:
        self.hide_calls += 1


class _VoiceSessionProbe:
    def __init__(self) -> None:
        self.listening_calls: list[dict[str, object]] = []
        self.open_calls: list[dict[str, object]] = []

    def active_window_remaining_seconds(self) -> float:
        return 1.2

    def transition_to_listening(self, *, detail: str, phase: str, input_owner: str) -> None:
        self.listening_calls.append(
            {"detail": detail, "phase": phase, "input_owner": input_owner}
        )

    def open_active_window(self, *, seconds: float, phase: str, input_owner: str, detail: str) -> None:
        self.open_calls.append(
            {
                "seconds": seconds,
                "phase": phase,
                "input_owner": input_owner,
                "detail": detail,
            }
        )


class _AssistantProbe:
    def __init__(self) -> None:
        self.voice_session = _VoiceSessionProbe()
        self.settings = {"voice_input": {}}
        self._last_command_window_policy_snapshot: dict[str, object] = {}


class ActiveWindowCommandWindowPolicyTests(unittest.TestCase):
    def test_handle_no_speech_capture_retries_when_policy_returns_retry(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        original_service = _module._COMMAND_WINDOW_POLICY_SERVICE
        original_return = _module._return_to_wake_gate

        class _Decision:
            action = "retry"
            detail = "awaiting_command_after_silence"
            reason = "empty_capture"

        class _Service:
            def decide_after_empty_capture(self, *args, **kwargs):
                return _Decision()

        def _fake_return(*args, **kwargs):
            raise AssertionError("standby path should not be called")

        try:
            _module._COMMAND_WINDOW_POLICY_SERVICE = _Service()
            _module._return_to_wake_gate = _fake_return
            result = _handle_no_speech_capture(assistant, state_flags)
        finally:
            _module._COMMAND_WINDOW_POLICY_SERVICE = original_service
            _module._return_to_wake_gate = original_return

        self.assertTrue(result)
        self.assertEqual(len(assistant.voice_session.listening_calls), 1)
        self.assertEqual(
            assistant.voice_session.listening_calls[0]["detail"],
            "awaiting_command_after_silence",
        )

    def test_prime_command_window_after_wake_uses_policy_window_decision(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        original_service = _module._COMMAND_WINDOW_POLICY_SERVICE
        original_wait = _module._wait_for_input_ready

        class _Decision:
            window_seconds = 5.8
            detail = "awaiting_command_after_wake"

        class _Service:
            def initial_window_decision(self, assistant_obj):
                return _Decision()

        def _fake_wait(*args, **kwargs):
            return None

        try:
            _module._COMMAND_WINDOW_POLICY_SERVICE = _Service()
            _module._wait_for_input_ready = _fake_wait
            _prime_command_window_after_wake(assistant, state_flags)
        finally:
            _module._COMMAND_WINDOW_POLICY_SERVICE = original_service
            _module._wait_for_input_ready = original_wait

        self.assertEqual(len(assistant.voice_session.open_calls), 1)
        self.assertEqual(assistant.voice_session.open_calls[0]["seconds"], 5.8)
        self.assertEqual(assistant.voice_session.open_calls[0]["detail"], "awaiting_command_after_wake")
        self.assertEqual(state_flags.active_phase, "command")
        self.assertEqual(state_flags.hide_calls, 1)


if __name__ == "__main__":
    unittest.main()