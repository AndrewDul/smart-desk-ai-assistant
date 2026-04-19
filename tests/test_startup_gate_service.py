from __future__ import annotations

import unittest

from modules.runtime.startup_gate import StartupGateService


class TestStartupGateService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StartupGateService()

    def test_systemd_allows_premium_ready_runtime(self) -> None:
        decision = self.service.decide_startup_gate(
            snapshot={
                "startup_allowed": True,
                "primary_ready": True,
                "premium_ready": True,
                "status_message": "runtime ready in premium mode",
                "blockers": [],
                "warnings": [],
            },
            runtime_mode="systemd",
            startup_allowed_default=False,
        )

        self.assertFalse(decision.abort_startup)
        self.assertTrue(decision.primary_ready)
        self.assertTrue(decision.premium_ready)

    def test_systemd_blocks_when_required_components_are_missing(self) -> None:
        decision = self.service.decide_startup_gate(
            snapshot={
                "startup_allowed": True,
                "primary_ready": False,
                "premium_ready": False,
                "blockers": ["voice_input", "display"],
                "status_message": "required services need attention",
            },
            runtime_mode="systemd",
            startup_allowed_default=True,
        )

        self.assertTrue(decision.abort_startup)
        self.assertIn("voice_input", decision.reason)
        self.assertIn("display", decision.reason)

    def test_systemd_blocks_when_only_compatibility_mode_is_available(self) -> None:
        decision = self.service.decide_startup_gate(
            snapshot={
                "startup_allowed": True,
                "primary_ready": False,
                "premium_ready": False,
                "warnings": ["voice_input: compatibility path active"],
                "status_message": "runtime ready with compatibility path: voice_input",
            },
            runtime_mode="systemd",
            startup_allowed_default=True,
        )

        self.assertTrue(decision.abort_startup)
        self.assertIn("primary runtime stack is not ready", decision.reason)

    def test_interactive_mode_can_continue_with_degraded_runtime(self) -> None:
        decision = self.service.decide_startup_gate(
            snapshot={
                "startup_allowed": True,
                "primary_ready": False,
                "premium_ready": False,
                "warnings": ["voice_input: compatibility path active"],
                "status_message": "runtime ready with compatibility path: voice_input",
            },
            runtime_mode="interactive",
            startup_allowed_default=True,
        )

        self.assertFalse(decision.abort_startup)
        self.assertEqual(decision.runtime_mode, "interactive")

    def test_post_boot_lifecycle_prefers_degraded_when_primary_stack_ready_but_not_premium(self) -> None:
        decision = self.service.decide_post_boot_lifecycle(
            {
                "startup_allowed": True,
                "primary_ready": True,
                "premium_ready": False,
                "degraded": True,
                "status_message": "runtime core ready, local llm unavailable, premium mode blocked",
            }
        )

        self.assertEqual(decision.method_name, "mark_degraded")
        self.assertIn("premium mode blocked", decision.reason)


if __name__ == "__main__":
    unittest.main()