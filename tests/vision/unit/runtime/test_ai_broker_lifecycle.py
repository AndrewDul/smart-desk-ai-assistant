from __future__ import annotations

import unittest

from modules.core.assistant_impl.lifecycle_mixin import CoreAssistantLifecycleMixin


class _FakeBroker:
    def __init__(self) -> None:
        self.enter_calls: list[str] = []
        self.closed = False

    def enter_idle_baseline(self, *, reason: str = "") -> dict[str, object]:
        self.enter_calls.append(reason)
        return {
            "mode": "idle_baseline",
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 2.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
        }

    def close(self) -> None:
        self.closed = True


class _LifecycleHost(CoreAssistantLifecycleMixin):
    def __init__(self) -> None:
        self.ai_broker = _FakeBroker()


class AiBrokerLifecycleTests(unittest.TestCase):
    def test_apply_ai_broker_boot_baseline_calls_idle_baseline(self) -> None:
        host = _LifecycleHost()

        host._apply_ai_broker_boot_baseline()

        self.assertEqual(host.ai_broker.enter_calls, ["assistant_boot_idle_baseline"])

    def test_close_ai_broker_calls_close(self) -> None:
        host = _LifecycleHost()

        host._close_ai_broker()

        self.assertTrue(host.ai_broker.closed)


if __name__ == "__main__":
    unittest.main()