from __future__ import annotations

import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from modules.runtime.main_loop.startup import _run_startup_sequence


@dataclass
class _FakeRuntimeProduct:
    failed_reasons: list[str] = field(default_factory=list)

    def begin_boot(self, *, startup_allowed: bool, warnings: list[str] | None = None) -> dict[str, object]:
        return {
            "startup_allowed": startup_allowed,
            "warnings": list(warnings or []),
        }

    def evaluate_startup(
        self,
        *,
        startup_allowed: bool,
        runtime_warnings: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "startup_allowed": startup_allowed,
            "ready": False,
            "primary_ready": False,
            "premium_ready": False,
            "startup_mode": "limited",
            "status_message": "runtime ready with compatibility path: voice_input",
            "blockers": [],
            "warnings": list(runtime_warnings or []),
        }

    def mark_failed(self, *, reason: str) -> dict[str, str]:
        self.failed_reasons.append(reason)
        return {"reason": reason}


@dataclass
class _FakeAssistant:
    settings: dict[str, object] = field(default_factory=dict)
    backend_statuses: dict[str, object] = field(default_factory=dict)
    runtime_product: _FakeRuntimeProduct = field(default_factory=_FakeRuntimeProduct)
    boot_called: bool = False
    _runtime_startup_allowed: bool = False
    _runtime_startup_runtime_warnings: list[str] = field(default_factory=list)
    _runtime_startup_snapshot: dict[str, object] = field(default_factory=dict)
    _runtime_startup_gate: dict[str, object] = field(default_factory=dict)
    _boot_report_ok: bool = False

    def boot(self) -> None:
        self.boot_called = True


class TestRuntimeStartupGate(unittest.TestCase):
    def test_systemd_startup_aborts_when_primary_runtime_is_not_ready(self) -> None:
        assistant = _FakeAssistant()

        with patch.dict(os.environ, {"NEXA_RUNTIME_MODE": "systemd"}, clear=False):
            with patch("modules.runtime.main_loop.startup.RuntimeHealthChecker") as checker_cls:
                checker = checker_cls.return_value
                checker.run.return_value.startup_allowed = True
                checker.run.return_value.items = []

                with self.assertRaises(RuntimeError) as raised:
                    _run_startup_sequence(assistant)

        self.assertIn("primary runtime stack is not ready", str(raised.exception))
        self.assertFalse(assistant.boot_called)
        self.assertEqual(len(assistant.runtime_product.failed_reasons), 1)
        self.assertIn("primary runtime stack is not ready", assistant.runtime_product.failed_reasons[0])
        self.assertTrue(assistant._runtime_startup_gate.get("abort_startup", False))


if __name__ == "__main__":
    unittest.main()