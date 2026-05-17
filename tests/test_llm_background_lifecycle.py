from __future__ import annotations

import threading
import time
import unittest

from modules.core.assistant_impl.lifecycle_mixin import CoreAssistantLifecycleMixin


class _LifecycleHarness(CoreAssistantLifecycleMixin):
    def __init__(self) -> None:
        self.settings = {
            "llm": {
                "enabled": True,
                "background_lifecycle_enabled": True,
            }
        }
        self.started = threading.Event()
        self.release = threading.Event()
        self.run_count = 0

    def _run_llm_backend_lifecycle(self) -> None:
        self.run_count += 1
        self.started.set()
        self.release.wait(timeout=1.0)


class LLMBackgroundLifecycleTests(unittest.TestCase):
    def test_llm_background_lifecycle_starts_without_blocking(self) -> None:
        harness = _LifecycleHarness()

        started_at = time.perf_counter()
        scheduled = harness._start_llm_backend_lifecycle_background()
        elapsed = time.perf_counter() - started_at

        self.assertTrue(scheduled)
        self.assertLess(elapsed, 0.1)
        self.assertTrue(harness.started.wait(timeout=0.5))

        duplicate = harness._start_llm_backend_lifecycle_background()

        self.assertFalse(duplicate)
        self.assertEqual(harness.run_count, 1)

        harness.release.set()
        harness._llm_background_lifecycle_thread.join(timeout=1.0)

    def test_llm_background_lifecycle_skips_when_llm_disabled(self) -> None:
        harness = _LifecycleHarness()
        harness.settings["llm"]["enabled"] = False

        scheduled = harness._start_llm_backend_lifecycle_background()

        self.assertFalse(scheduled)
        self.assertFalse(hasattr(harness, "_llm_background_lifecycle_thread"))


if __name__ == "__main__":
    unittest.main()
