from __future__ import annotations

import unittest

from modules.runtime.builder.core import RuntimeBuilder
from modules.runtime.contracts import RuntimeBackendStatus


class _FakeVisionBackend:
    def __init__(self) -> None:
        self.current_cadence_hz = 2.0

    def set_object_detection_cadence_hz(self, hz: float) -> bool:
        self.current_cadence_hz = float(hz)
        return True


class _StubRuntimeBuilder(RuntimeBuilder):
    def _build_parser(self):
        return object()

    def _build_router(self, parser):
        del parser
        return object()

    def _build_dialogue(self):
        return object()

    def _build_memory(self):
        return object()

    def _build_reminders(self):
        return object()

    def _build_timer(self, **kwargs):
        del kwargs
        return object()

    def _build_audio_coordinator(self):
        return object()

    def _attach_audio_coordinator(self, backend, audio_coordinator):
        del backend, audio_coordinator
        return None

    def _build_voice_input(self, config):
        del config
        return object(), RuntimeBackendStatus(
            component="voice_input",
            ok=True,
            selected_backend="fake_voice_input",
            detail="ok",
        )

    def _build_wake_gate(self, config, **kwargs):
        del config, kwargs
        return object(), RuntimeBackendStatus(
            component="wake_gate",
            ok=True,
            selected_backend="fake_wake_gate",
            detail="ok",
        )

    def _build_voice_output(self, config):
        del config
        return object(), RuntimeBackendStatus(
            component="voice_output",
            ok=True,
            selected_backend="fake_voice_output",
            detail="ok",
        )

    def _build_display(self, config):
        del config
        return object(), RuntimeBackendStatus(
            component="display",
            ok=True,
            selected_backend="fake_display",
            detail="ok",
        )

    def _build_vision(self, config):
        del config
        return _FakeVisionBackend(), RuntimeBackendStatus(
            component="vision",
            ok=True,
            selected_backend="camera_service",
            detail="ok",
        )

    def _build_pan_tilt(self, config):
        del config
        return object(), RuntimeBackendStatus(
            component="pan_tilt",
            ok=True,
            selected_backend="fake_pan_tilt",
            detail="ok",
        )

    def _build_mobility(self, config):
        del config
        return object(), RuntimeBackendStatus(
            component="mobility",
            ok=True,
            selected_backend="fake_mobility",
            detail="ok",
        )


class AiBrokerBuilderIntegrationTests(unittest.TestCase):
    def test_runtime_builder_exposes_ai_broker_in_runtime_metadata(self) -> None:
        runtime = _StubRuntimeBuilder(settings={}).build()

        self.assertIn("ai_broker", runtime.metadata)
        broker = runtime.metadata["ai_broker"]

        snapshot = broker.snapshot()
        self.assertEqual(snapshot["mode"], "idle_baseline")
        self.assertTrue(snapshot["vision_control_available"])

        status = runtime.backend_status("ai_broker")
        self.assertIsNotNone(status)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "ai_broker")

        inventory = runtime.provider_inventory()
        self.assertIn("ai_broker", inventory)


if __name__ == "__main__":
    unittest.main()