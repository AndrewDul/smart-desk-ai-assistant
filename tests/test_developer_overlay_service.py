from __future__ import annotations

import unittest

from modules.presentation.developer_overlay import DeveloperOverlayService


class _FakeDisplay:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.clear_calls = 0

    def set_developer_overlay(self, title: str, lines: list[str]) -> None:
        self.calls.append(
            {
                "title": str(title),
                "lines": list(lines),
            }
        )

    def clear_developer_overlay(self) -> None:
        self.clear_calls += 1


class DeveloperOverlayServiceTests(unittest.TestCase):
    def test_refresh_builds_runtime_and_benchmark_lines(self) -> None:
        display = _FakeDisplay()
        service = DeveloperOverlayService(
            display=display,
            runtime_snapshot_provider=lambda: {
                "premium_ready": True,
                "llm_enabled": True,
                "llm_warmup_ready": True,
            },
            benchmark_snapshot_provider=lambda: {
                "overlay_lines": [
                    "turn:780ms audio:140ms",
                    "llm:95ms result:action",
                ]
            },
            enabled=True,
            title="DEV",
        )

        refreshed = service.refresh(reason="turn_finished")

        self.assertTrue(refreshed)
        self.assertEqual(len(display.calls), 1)
        payload = display.calls[0]
        self.assertEqual(payload["title"], "DEV")
        self.assertEqual(
            payload["lines"],
            [
                "rt:premium llm:ready",
                "turn:780ms audio:140ms",
                "llm:95ms result:action",
            ],
        )

    def test_refresh_honors_turn_finish_policy(self) -> None:
        display = _FakeDisplay()
        service = DeveloperOverlayService(
            display=display,
            runtime_snapshot_provider=lambda: {"premium_ready": True},
            benchmark_snapshot_provider=lambda: {"overlay_lines": ["turn:1ms"]},
            enabled=True,
            refresh_on_turn_finish=False,
        )

        refreshed = service.refresh(reason="turn_finished")

        self.assertFalse(refreshed)
        self.assertEqual(display.calls, [])
        self.assertEqual(display.clear_calls, 0)

    def test_disabled_service_clears_overlay(self) -> None:
        display = _FakeDisplay()
        service = DeveloperOverlayService(
            display=display,
            runtime_snapshot_provider=lambda: {"premium_ready": True},
            benchmark_snapshot_provider=lambda: {"overlay_lines": ["turn:1ms"]},
            enabled=False,
        )

        refreshed = service.refresh(reason="boot")

        self.assertFalse(refreshed)
        self.assertEqual(display.calls, [])
        self.assertEqual(display.clear_calls, 1)


if __name__ == "__main__":
    unittest.main()