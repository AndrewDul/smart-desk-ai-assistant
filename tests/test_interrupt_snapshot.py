from __future__ import annotations

import unittest

from modules.core.assistant_impl.interaction_mixin import CoreAssistantInteractionMixin
from modules.core.session.interrupt_controller import InteractionInterruptController


class _VoiceSessionProbe:
    def __init__(self) -> None:
        self.details: list[str] = []

    def mark_interrupt_requested(self, *, detail: str = "interrupt_requested") -> None:
        self.details.append(str(detail))


class _BenchmarkProbe:
    def __init__(self) -> None:
        self.interrupt_snapshots: list[dict[str, object]] = []

    def annotate_last_completed_turn(
        self,
        *,
        interrupt_snapshot=None,
        resume_policy=None,
        command_window_policy=None,
    ) -> bool:
        del resume_policy, command_window_policy
        self.interrupt_snapshots.append(dict(interrupt_snapshot or {}))
        return True


class _AssistantProbe(CoreAssistantInteractionMixin):
    def __init__(self) -> None:
        self.interrupt_controller = InteractionInterruptController()
        self.voice_session = _VoiceSessionProbe()
        self.turn_benchmark_service = _BenchmarkProbe()
        self._last_interrupt_snapshot = {}


class InterruptSnapshotTests(unittest.TestCase):
    def test_request_interrupt_stores_structured_snapshot_and_annotates_benchmark(self) -> None:
        assistant = _AssistantProbe()

        assistant.request_interrupt(
            reason="wake_barge_in",
            source="wake_gate",
            metadata={"interrupt_kind": "barge_in", "backend": "runtime.wake_gate"},
        )

        snapshot = assistant._last_interrupt_snapshot
        self.assertTrue(snapshot["requested"])
        self.assertGreaterEqual(int(snapshot["generation"]), 1)
        self.assertEqual(snapshot["reason"], "wake_barge_in")
        self.assertEqual(snapshot["source"], "wake_gate")
        self.assertEqual(snapshot["kind"], "barge_in")
        self.assertEqual(snapshot["metadata"]["backend"], "runtime.wake_gate")
        self.assertEqual(assistant.voice_session.details[-1], "wake_barge_in")
        self.assertEqual(assistant.turn_benchmark_service.interrupt_snapshots[-1]["kind"], "barge_in")


if __name__ == "__main__":
    unittest.main()