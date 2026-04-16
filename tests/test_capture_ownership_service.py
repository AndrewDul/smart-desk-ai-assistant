from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_STATE_SPEAKING,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _PROJECT_ROOT / "modules" / "runtime" / "main_loop" / "capture_ownership.py"

if "modules.runtime.main_loop" not in sys.modules:
    package = types.ModuleType("modules.runtime.main_loop")
    package.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = package

spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.capture_ownership",
    _MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load capture_ownership module for tests.")

_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _module
spec.loader.exec_module(_module)
CaptureOwnershipService = _module.CaptureOwnershipService


class _FakeCloseableInput:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0
        self._stream = object()

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


class _FakeWakeGate(_FakeCloseableInput):
    def listen_for_wake_phrase(self, *args, **kwargs):
        return "nexa"


class _FakeVoiceInput(_FakeCloseableInput):
    def listen(self):
        return None


class _FakeVoiceSession:
    def __init__(self) -> None:
        self._input_owner = VOICE_INPUT_OWNER_NONE
        self.state = "standby"
        self.state_changes: list[tuple[str, str]] = []

    def set_input_owner(self, owner: str) -> None:
        self._input_owner = str(owner)

    def input_owner(self) -> str:
        return self._input_owner

    def set_state(self, state: str, *, detail: str = "") -> None:
        self.state = str(state)
        self.state_changes.append((str(state), str(detail)))


class _FakeCoordinator:
    def __init__(self, blocked_sequence: list[bool] | None = None) -> None:
        self._blocked_sequence = list(blocked_sequence or [False])
        self.listen_resume_poll_seconds = 0.001

    def input_blocked(self) -> bool:
        if len(self._blocked_sequence) > 1:
            return self._blocked_sequence.pop(0)
        if self._blocked_sequence:
            return self._blocked_sequence[0]
        return False


class _FakeVoiceOutput:
    def __init__(self, coordinator: _FakeCoordinator | None = None) -> None:
        self.audio_coordinator = coordinator


class _FakeBackendStatus:
    def __init__(self, *, ok: bool = True, selected_backend: str = "runtime.wake_gate") -> None:
        self.ok = ok
        self.selected_backend = selected_backend


class _AssistantProbe:
    def __init__(
        self,
        *,
        wake_gate=None,
        voice_in=None,
        coordinator: _FakeCoordinator | None = None,
        wake_selected_backend: str = "runtime.wake_gate",
    ) -> None:
        self.settings = {
            "audio_coordination": {
                "listen_resume_poll_seconds": 0.001,
            }
        }
        self.voice_session = _FakeVoiceSession()
        self.voice_out = _FakeVoiceOutput(coordinator=coordinator)
        self.wake_gate = wake_gate
        self.voice_in = voice_in
        self.backend_statuses = {
            "wake_gate": _FakeBackendStatus(
                ok=True,
                selected_backend=wake_selected_backend,
            )
        }
        self._last_capture_handoff: dict[str, object] = {}


class CaptureOwnershipServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CaptureOwnershipService()

    def test_prepare_for_active_capture_releases_dedicated_wake_backend(self) -> None:
        wake_gate = _FakeWakeGate()
        voice_in = _FakeVoiceInput()
        assistant = _AssistantProbe(
            wake_gate=wake_gate,
            voice_in=voice_in,
            coordinator=_FakeCoordinator([False]),
        )

        result = self.service.prepare_for_active_capture(assistant)

        self.assertEqual(result.target_owner, VOICE_INPUT_OWNER_VOICE_INPUT)
        self.assertEqual(result.applied_owner, VOICE_INPUT_OWNER_VOICE_INPUT)
        self.assertTrue(result.wake_backend_released)
        self.assertFalse(result.voice_input_released)
        self.assertEqual(result.wake_backend_label, "runtime.wake_gate")
        self.assertTrue(wake_gate.closed)
        self.assertFalse(voice_in.closed)
        self.assertEqual(assistant.voice_session.input_owner(), VOICE_INPUT_OWNER_VOICE_INPUT)
        self.assertEqual(
            assistant._last_capture_handoff["applied_owner"],
            VOICE_INPUT_OWNER_VOICE_INPUT,
        )

    def test_prepare_for_standby_capture_releases_voice_input(self) -> None:
        wake_gate = _FakeWakeGate()
        voice_in = _FakeVoiceInput()
        assistant = _AssistantProbe(
            wake_gate=wake_gate,
            voice_in=voice_in,
            coordinator=_FakeCoordinator([False]),
        )

        result = self.service.prepare_for_standby_capture(assistant)

        self.assertEqual(result.target_owner, VOICE_INPUT_OWNER_WAKE_GATE)
        self.assertEqual(result.applied_owner, VOICE_INPUT_OWNER_WAKE_GATE)
        self.assertFalse(result.wake_backend_released)
        self.assertTrue(result.voice_input_released)
        self.assertFalse(wake_gate.closed)
        self.assertTrue(voice_in.closed)
        self.assertEqual(assistant.voice_session.input_owner(), VOICE_INPUT_OWNER_WAKE_GATE)
        self.assertEqual(
            assistant._last_capture_handoff["applied_owner"],
            VOICE_INPUT_OWNER_WAKE_GATE,
        )

    def test_wait_for_input_ready_records_blocked_output(self) -> None:
        wake_gate = _FakeWakeGate()
        voice_in = _FakeVoiceInput()
        coordinator = _FakeCoordinator([True, True, False])
        assistant = _AssistantProbe(
            wake_gate=wake_gate,
            voice_in=voice_in,
            coordinator=coordinator,
        )

        result = self.service.wait_for_input_ready(assistant, max_wait_seconds=0.05)

        self.assertEqual(result.target_owner, "wait_only")
        self.assertTrue(result.blocked_observed)
        self.assertTrue(result.wait_completed)
        self.assertGreaterEqual(result.wait_elapsed_ms, 0.0)
        self.assertEqual(assistant.voice_session.state, VOICE_STATE_SPEAKING)
        self.assertEqual(
            assistant._last_capture_handoff["blocked_observed"],
            True,
        )

    def test_prepare_for_active_capture_does_not_close_shared_voice_input_backend(self) -> None:
        voice_in = _FakeVoiceInput()
        assistant = _AssistantProbe(
            wake_gate=voice_in,
            voice_in=voice_in,
            coordinator=_FakeCoordinator([False]),
            wake_selected_backend="compatibility_voice_input",
        )

        result = self.service.prepare_for_active_capture(assistant)

        self.assertFalse(result.wake_backend_released)
        self.assertFalse(voice_in.closed)
        self.assertEqual(result.applied_owner, VOICE_INPUT_OWNER_VOICE_INPUT)
        self.assertEqual(assistant.voice_session.input_owner(), VOICE_INPUT_OWNER_VOICE_INPUT)

    def test_ensure_wake_capture_released_returns_backend_label(self) -> None:
        wake_gate = _FakeWakeGate()
        voice_in = _FakeVoiceInput()
        assistant = _AssistantProbe(
            wake_gate=wake_gate,
            voice_in=voice_in,
            coordinator=_FakeCoordinator([False]),
        )

        released, label = self.service.ensure_wake_capture_released(assistant)

        self.assertTrue(released)
        self.assertEqual(label, "runtime.wake_gate")
        self.assertTrue(wake_gate.closed)

    def test_ensure_voice_capture_released_keeps_shared_backend_alive(self) -> None:
        voice_in = _FakeVoiceInput()
        assistant = _AssistantProbe(
            wake_gate=voice_in,
            voice_in=voice_in,
            coordinator=_FakeCoordinator([False]),
            wake_selected_backend="compatibility_voice_input",
        )

        released = self.service.ensure_voice_capture_released(assistant)

        self.assertFalse(released)
        self.assertFalse(voice_in.closed)


if __name__ == "__main__":
    unittest.main()