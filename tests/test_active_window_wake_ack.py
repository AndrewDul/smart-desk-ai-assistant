from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from tests.support.fakes import FakeVoiceOutput

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
_acknowledge_wake = _module._acknowledge_wake


class _FakeVoiceSession:
    def __init__(self) -> None:
        self.transition_calls: list[str] = []
        self.builder_calls = 0

    def transition_to_wake_detected(self, *, detail: str) -> None:
        self.transition_calls.append(str(detail))

    def build_wake_acknowledgement(self) -> str:
        self.builder_calls += 1
        return "I'm listening."


class _FakeWakeAckService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def speak(self, *, language: str | None = None):
        self.calls.append(str(language))

        class _Result:
            text = "Yes?"
            spoken = True

        return _Result()


class _AssistantProbe:
    def __init__(self) -> None:
        self.voice_session = _FakeVoiceSession()
        self.voice_out = FakeVoiceOutput()
        self.wake_ack_service = _FakeWakeAckService()
        self.last_language = "en"


class ActiveWindowWakeAcknowledgementTests(unittest.TestCase):
    def test_acknowledge_wake_prefers_wake_ack_service(self) -> None:
        assistant = _AssistantProbe()

        _acknowledge_wake(assistant)

        self.assertEqual(assistant.voice_session.transition_calls, ["wake_phrase_detected"])
        self.assertEqual(assistant.wake_ack_service.calls, ["en"])
        self.assertEqual(assistant.voice_out.speak_calls, [])
        self.assertEqual(assistant.voice_session.builder_calls, 0)


if __name__ == "__main__":
    unittest.main()