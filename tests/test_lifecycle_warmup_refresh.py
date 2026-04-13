from __future__ import annotations

import unittest

from modules.core.assistant_impl.lifecycle_mixin import CoreAssistantLifecycleMixin


class _FakeRuntimeProduct:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def evaluate_startup(
        self,
        *,
        startup_allowed: bool,
        runtime_warnings: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "startup_allowed": startup_allowed,
                "runtime_warnings": list(runtime_warnings or []),
            }
        )
        return {
            "ready": True,
            "primary_ready": True,
            "premium_ready": True,
            "llm_state": "ready",
            "llm_available": True,
            "llm_warmup_ready": True,
        }


class _LifecycleProbe(CoreAssistantLifecycleMixin):
    def __init__(self) -> None:
        self.runtime_product = _FakeRuntimeProduct()
        self._runtime_startup_allowed = True
        self._runtime_startup_runtime_warnings = ["wake_gate: compatibility path active"]
        self._runtime_startup_snapshot = {}
        self._boot_report_ok = False


class LifecycleWarmupRefreshTests(unittest.TestCase):
    def test_refresh_runtime_snapshot_after_llm_warmup_uses_startup_baseline(self) -> None:
        probe = _LifecycleProbe()

        probe._refresh_runtime_startup_snapshot_after_llm_warmup(
            warmup_result={
                "attempted": True,
                "ok": True,
                "snapshot": {
                    "state": "ready",
                    "available": True,
                    "warmup_ready": True,
                    "health_reason": "hailo-ollama ready",
                },
            }
        )

        self.assertEqual(len(probe.runtime_product.calls), 1)
        call = probe.runtime_product.calls[0]
        self.assertTrue(call["startup_allowed"])
        self.assertEqual(
            call["runtime_warnings"],
            ["wake_gate: compatibility path active"],
        )
        self.assertTrue(probe._boot_report_ok)
        self.assertTrue(probe._runtime_startup_snapshot["premium_ready"])


if __name__ == "__main__":
    unittest.main()