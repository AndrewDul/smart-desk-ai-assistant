from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from modules.runtime.main_loop.entrypoint import main


@dataclass
class _FakeRuntimeProduct:
    failed_reasons: list[str] = field(default_factory=list)

    def mark_failed(self, *, reason: str) -> dict[str, str]:
        self.failed_reasons.append(reason)
        return {"reason": reason}


@dataclass
class _FakeAssistant:
    runtime_product: _FakeRuntimeProduct = field(default_factory=_FakeRuntimeProduct)
    shutdown_requested: bool = False


class TestRuntimeEntrypointStartupFailure(unittest.TestCase):
    def test_main_marks_runtime_failed_when_startup_sequence_raises(self) -> None:
        assistant = _FakeAssistant()

        with patch("modules.runtime.main_loop.entrypoint.CoreAssistant", return_value=assistant):
            with patch(
                "modules.runtime.main_loop.entrypoint._run_startup_sequence",
                side_effect=RuntimeError("startup gate blocked"),
            ):
                with patch("modules.runtime.main_loop.entrypoint.append_log"):
                    with patch("builtins.print"):
                        main()

        self.assertEqual(len(assistant.runtime_product.failed_reasons), 1)
        self.assertIn("startup error: startup gate blocked", assistant.runtime_product.failed_reasons[0])


if __name__ == "__main__":
    unittest.main()