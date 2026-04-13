from __future__ import annotations

import unittest

from modules.runtime.product import RuntimeProductService


class _FakeLocalLLM:
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
            "state": "degraded",
            "available": True,
            "healthy": False,
            "warmup_required": True,
            "warmup_ready": False,
            "health_reason": "backend reachable but startup warmup is not complete",
            "last_error": "",
            "capabilities": ["streaming", "healthcheck", "warmup", "auto_recovery"],
            "recovery_allowed": True,
            "recovery_attempted": bool(auto_recover),
            "recovery_ok": False,
            "recovery_error": "",
        }


class _FakeDialogue:
    def __init__(self) -> None:
        self.local_llm = _FakeLocalLLM()


class _FakeRuntime:
    def __init__(self) -> None:
        self.backend_statuses = {}


class RuntimeProductLLMHealthTests(unittest.TestCase):
    def test_evaluate_startup_marks_llm_as_degraded_when_warmup_is_missing(self) -> None:
        service = RuntimeProductService(
            settings={
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                }
            },
            persist_enabled=False,
        )
        service.bind_runtime(runtime=_FakeRuntime(), dialogue=_FakeDialogue())

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertIn("llm", snapshot["services"])
        self.assertEqual(snapshot["services"]["llm"]["state"], "degraded")
        self.assertIn("llm: degraded", snapshot["warnings"])


if __name__ == "__main__":
    unittest.main()