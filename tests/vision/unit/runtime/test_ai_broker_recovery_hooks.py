from __future__ import annotations

import unittest

from modules.core.assistant_impl.interaction_mixin import CoreAssistantInteractionMixin


class _Host(CoreAssistantInteractionMixin):
    def __init__(self) -> None:
        self.interrupt_controller = type("Interrupt", (), {"clear": lambda self: None})()
        self._last_interrupt_snapshot = {}
        self.tick_calls = 0

    def _tick_ai_broker(self):
        self.tick_calls += 1
        return {"mode": "idle_baseline"}

    def _start_turn_telemetry(self, cleaned):
        return {
            "input_source": "voice",
            "capture_phase": "command",
            "stt_mode": "command",
            "stt_backend": "fake",
        }

    def _prepare_command(self, cleaned, **kwargs):
        return {
            "ignore": True,
            "language": "en",
            "source": type("Source", (), {"value": "voice"})(),
            "capture_phase": "command",
            "capture_mode": "command",
            "capture_backend": "fake",
        }

    def _finish_turn_telemetry(self, telemetry):
        return None


class AiBrokerRecoveryInteractionTests(unittest.TestCase):
    def test_handle_command_ticks_ai_broker_before_processing_turn(self) -> None:
        host = _Host()

        handled = host.handle_command("hello")

        self.assertTrue(handled)
        self.assertEqual(host.tick_calls, 1)


if __name__ == "__main__":
    unittest.main()