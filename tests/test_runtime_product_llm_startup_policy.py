from __future__ import annotations

import unittest

from modules.runtime.product import RuntimeProductService


class _FakeLocalLLM:
    def __init__(
        self,
        *,
        available: bool,
        warmup_ready: bool,
        startup_availability_requirement: str,
        startup_warmup_requirement: str,
    ) -> None:
        self._available = bool(available)
        self._warmup_ready = bool(warmup_ready)
        self._startup_availability_requirement = startup_availability_requirement
        self._startup_warmup_requirement = startup_warmup_requirement

    def describe_backend(self) -> dict[str, object]:
        return {
            "runner": "hailo-ollama",
            "capabilities": ["streaming", "healthcheck", "warmup", "auto_recovery"],
            "startup_availability_requirement": self._startup_availability_requirement,
            "startup_warmup_requirement": self._startup_warmup_requirement,
        }

    def ensure_backend_ready(self, *, auto_recover: bool = False) -> dict[str, object]:
        del auto_recover
        state = "ready" if self._available and self._warmup_ready else "degraded"
        if not self._available:
            state = "failed"

        return {
            "enabled": True,
            "runner": "hailo-ollama",
            "state": state,
            "available": self._available,
            "healthy": self._available and self._warmup_ready,
            "warmup_required": True,
            "warmup_ready": self._warmup_ready,
            "health_reason": (
                "hailo-ollama ready"
                if self._available and self._warmup_ready
                else "backend reachable but startup warmup is not complete"
                if self._available
                else "local llm backend unavailable"
            ),
            "last_error": "" if self._available else "local llm backend unavailable",
            "capabilities": ["streaming", "healthcheck", "warmup", "auto_recovery"],
            "startup_availability_requirement": self._startup_availability_requirement,
            "startup_warmup_requirement": self._startup_warmup_requirement,
            "recovery_allowed": True,
            "recovery_attempted": False,
            "recovery_ok": False,
            "recovery_error": "",
        }


class _FakeDialogue:
    def __init__(self, local_llm: _FakeLocalLLM) -> None:
        self.local_llm = local_llm


class _FakeRuntime:
    def __init__(self) -> None:
        self.backend_statuses = {}


class RuntimeProductLLMStartupPolicyTests(unittest.TestCase):
    def test_llm_unavailable_blocks_only_premium_when_policy_is_premium(self) -> None:
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
        service.bind_runtime(
            runtime=_FakeRuntime(),
            dialogue=_FakeDialogue(
                _FakeLocalLLM(
                    available=False,
                    warmup_ready=False,
                    startup_availability_requirement="premium",
                    startup_warmup_requirement="premium",
                )
            ),
        )

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertEqual(snapshot["startup_mode"], "limited")
        self.assertEqual(snapshot["blockers"], [])
        self.assertIn("llm_backend_unavailable", snapshot["premium_blockers"])
        self.assertTrue(snapshot["primary_ready"])
        self.assertFalse(snapshot["premium_ready"])

    def test_llm_unavailable_becomes_blocker_when_policy_is_required(self) -> None:
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
        service.bind_runtime(
            runtime=_FakeRuntime(),
            dialogue=_FakeDialogue(
                _FakeLocalLLM(
                    available=False,
                    warmup_ready=False,
                    startup_availability_requirement="required",
                    startup_warmup_requirement="premium",
                )
            ),
        )

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertEqual(snapshot["startup_mode"], "blocked")
        self.assertIn("llm", snapshot["blockers"])
        self.assertFalse(snapshot["primary_ready"])
        self.assertFalse(snapshot["premium_ready"])

    def test_warmup_incomplete_blocks_only_premium_when_policy_is_premium(self) -> None:
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
        service.bind_runtime(
            runtime=_FakeRuntime(),
            dialogue=_FakeDialogue(
                _FakeLocalLLM(
                    available=True,
                    warmup_ready=False,
                    startup_availability_requirement="premium",
                    startup_warmup_requirement="premium",
                )
            ),
        )

        snapshot = service.evaluate_startup(
            startup_allowed=True,
            runtime_warnings=[],
        )

        self.assertEqual(snapshot["startup_mode"], "limited")
        self.assertIn("llm_warmup_incomplete", snapshot["premium_blockers"])
        self.assertTrue(snapshot["primary_ready"])
        self.assertFalse(snapshot["premium_ready"])


if __name__ == "__main__":
    unittest.main()