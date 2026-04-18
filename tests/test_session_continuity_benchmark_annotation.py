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


class _BenchmarkProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def annotate_last_completed_turn(
        self,
        *,
        resume_policy=None,
        command_window_policy=None,
        interrupt_snapshot=None,
        continuity_snapshot=None,
    ) -> bool:
        del resume_policy, command_window_policy, interrupt_snapshot
        self.calls.append(dict(continuity_snapshot or {}))
        return True


class _StateFlags:
    def __init__(self) -> None:
        self.active_phase = "command"

    def set_active_phase(self, phase: str) -> None:
        self.active_phase = str(phase)

    def hide_standby_banner(self) -> None:
        return None

    def clear_prefetched_command(self) -> None:
        return None

    def arm_wake_rearm(self, seconds: float) -> None:
        return None


class _VoiceSessionProbe:
    def open_active_window(self, *, seconds: float, phase: str, input_owner: str, detail: str) -> None:
        return None


class _AssistantProbe:
    def __init__(self) -> None:
        self.voice_session = _VoiceSessionProbe()
        self.turn_benchmark_service = _BenchmarkProbe()
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
        self._last_session_continuity_snapshot = {}


class SessionContinuityBenchmarkAnnotationTests(unittest.TestCase):
    def test_follow_up_window_annotates_last_completed_turn_with_continuity_snapshot(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        _start_follow_up_window(assistant, state_flags)

        self.assertTrue(assistant.turn_benchmark_service.calls)
        continuity = assistant.turn_benchmark_service.calls[-1]
        self.assertEqual(continuity["action"], "follow_up")
        self.assertEqual(continuity["phase"], "follow_up")
        self.assertEqual(continuity["reason"], "pending_follow_up")
        self.assertEqual(continuity["pending_type"], "capture_name")


if __name__ == "__main__":
    unittest.main()