from __future__ import annotations

import unittest

from modules.core.assistant_impl.helpers_mixin import CoreAssistantHelpersMixin


class _ThinkingAckService:
    def __init__(self) -> None:
        self.cancel_active_calls = 0
        self.cancel_calls = 0

    def cancel_active(self) -> None:
        self.cancel_active_calls += 1

    def cancel(self) -> None:
        self.cancel_calls += 1


class _Assistant(CoreAssistantHelpersMixin):
    def __init__(self) -> None:
        self.thinking_ack_service = _ThinkingAckService()


class ThinkingAckHelperTests(unittest.TestCase):
    def test_thinking_ack_stop_prefers_cancel_active(self) -> None:
        assistant = _Assistant()

        assistant._thinking_ack_stop()

        self.assertEqual(assistant.thinking_ack_service.cancel_active_calls, 1)
        self.assertEqual(assistant.thinking_ack_service.cancel_calls, 0)


if __name__ == "__main__":
    unittest.main()
