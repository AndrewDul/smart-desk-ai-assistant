from __future__ import annotations

import types
import unittest

from modules.core.flows.pending_flow.orchestrator import PendingFlowOrchestrator


class _AssistantStub:
    def __init__(self) -> None:
        self.pending_confirmation = None
        self.pending_follow_up = {"type": "capture_name", "lang": "en"}
        self._last_pending_flow_snapshot = {}

    def _commit_language(self, language: str) -> str:
        return str(language or "en").strip().lower() or "en"


class _PendingFlowProbe(PendingFlowOrchestrator):
    def _handle_capture_name(self, *, text: str, language: str) -> bool:
        self.assistant.pending_follow_up = None
        return True


class PendingFlowSnapshotTests(unittest.TestCase):
    def test_process_stores_structured_pending_follow_up_snapshot(self) -> None:
        assistant = _AssistantStub()
        flow = _PendingFlowProbe(assistant)

        handled = flow.process(
            prepared={"routing_text": "Andrew"},
            language="en",
        )

        self.assertTrue(handled)
        snapshot = assistant._last_pending_flow_snapshot
        self.assertEqual(snapshot["consumed_by"], "follow_up:capture_name")
        self.assertEqual(snapshot["pending_kind"], "follow_up")
        self.assertEqual(snapshot["pending_type"], "capture_name")
        self.assertEqual(snapshot["language"], "en")
        self.assertFalse(snapshot["keeps_pending_state"])
        self.assertFalse(snapshot["metadata"]["pending_follow_up_active"])


if __name__ == "__main__":
    unittest.main()