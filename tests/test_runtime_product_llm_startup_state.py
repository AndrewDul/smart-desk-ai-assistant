from __future__ import annotations

import unittest

from modules.runtime.product import RuntimeProductService


class _FakeLocalLLM:
    def __init__(self, *, warmup_ready: bool) -> None:
        self._warmup_ready = bool(warmup_ready)

    def describe_backend(self) -> dict[str, object]:
        return {
            "runner": "hailo-ollama",
            "capabilities": ["streaming", "healthcheck", "warmup", "auto_recovery"],
            "server_model_name": "qwen2:1.5b",
        }

    def ensure_backend_ready(self, *, auto_recover: bool = False) -> dict[str, object]:
        return {
            "enabled": True,
            "runner": "hailo-ollama",
            "state": "ready" if self._warmup_ready else "degraded",
            "available": True,
            "healthy": bool(self._warmup_ready),
            "warmup_required": True,
            "warmup_ready": bool(self._warmup_ready),
            "health_reason": (
                "hailo-ollama ready"
                if self._warmup_ready
                else "backend reachable but startup warmup is not complete"
            ),
            "last_error": "",
            "capabilities": ["streaming", "healthcheck", "warmup", "auto_recovery"],
            "recovery_allowed": True,
            "recovery_attempted": bool(auto_recover),
            "recovery_ok": False,
            "recovery_error": "",
        }


class _FakeDialogue:
    def __init__(self, *, warmup_ready: bool) -> None:
        self.local_llm = _FakeLocalLLM(warmup_ready=warmup_ready)


class _FakeRuntime:
    def __init__(self) -> None:
        self.backend_statuses = {}


class RuntimeProductLLMStartupStateTests(unittest.TestCase):
    def test_snapshot_exposes_reachable_but_not_warmed_llm(self) -> None:
        service = RuntimeProductService(
            settings={
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                }
            },
            persist_enabled=False,
            required_ready_components=(),
        )
        service.bind_runtime(runtime=_FakeRuntime(), dialogue=_FakeDialogue(warmup_ready=False))

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertTrue(snapshot["llm_enabled"])
        self.assertEqual(snapshot["llm_runner"], "hailo-ollama")
        self.assertEqual(snapshot["llm_state"], "degraded")
        self.assertTrue(snapshot["llm_available"])
        self.assertTrue(snapshot["llm_warmup_required"])
        self.assertFalse(snapshot["llm_warmup_ready"])
        self.assertFalse(snapshot["llm_primary_ready"])
        self.assertFalse(snapshot["premium_ready"])
        self.assertIn("startup warmup incomplete", snapshot["status_message"])

    def test_snapshot_exposes_premium_llm_ready_after_warmup(self) -> None:
        service = RuntimeProductService(
            settings={
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                }
            },
            persist_enabled=False,
            required_ready_components=(),
        )
        service.bind_runtime(runtime=_FakeRuntime(), dialogue=_FakeDialogue(warmup_ready=True))

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertEqual(snapshot["llm_state"], "ready")
        self.assertTrue(snapshot["llm_available"])
        self.assertTrue(snapshot["llm_warmup_ready"])
        self.assertTrue(snapshot["llm_primary_ready"])
        self.assertTrue(snapshot["premium_ready"])
        self.assertEqual(snapshot["status_message"], "runtime ready in premium mode")


if __name__ == "__main__":
    unittest.main()
    