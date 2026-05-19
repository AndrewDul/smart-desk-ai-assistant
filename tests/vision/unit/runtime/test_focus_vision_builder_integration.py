from __future__ import annotations

import unittest

from modules.runtime.builder.features_mixin import RuntimeBuilderFeaturesMixin


class _FakeVisionBackend:
    def latest_observation(self, *, force_refresh: bool = True):
        del force_refresh
        return None


class _FocusVisionBuilderProbe(RuntimeBuilderFeaturesMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        if module_name == "modules.features.focus_vision":
            from modules.features import focus_vision

            return getattr(focus_vision, symbol_name)
        raise AssertionError(f"Unexpected import request: {module_name}.{symbol_name}")


class _FailingFocusVisionBuilderProbe(RuntimeBuilderFeaturesMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        del module_name, symbol_name
        raise RuntimeError("focus vision import failure")


class FocusVisionBuilderIntegrationTests(unittest.TestCase):
    def test_builds_disabled_focus_vision_service_safely(self) -> None:
        builder = _FocusVisionBuilderProbe()

        service, status = builder._build_focus_vision(
            {"enabled": False, "dry_run": True},
            vision_backend=_FakeVisionBackend(),
        )

        self.assertIsNotNone(service)
        self.assertTrue(status.ok)
        self.assertEqual(status.component, "focus_vision")
        self.assertEqual(status.selected_backend, "disabled_focus_vision_sentinel")
        self.assertEqual(status.runtime_mode, "disabled")
        self.assertIn("focus_mode_lifecycle_hook", status.capabilities)
        self.assertFalse(status.metadata["enabled"])
        self.assertFalse(service.start(language="en"))

    def test_builds_enabled_focus_vision_service_in_dry_run_mode(self) -> None:
        builder = _FocusVisionBuilderProbe()

        service, status = builder._build_focus_vision(
            {"enabled": True, "dry_run": True, "voice_warnings_enabled": False},
            vision_backend=_FakeVisionBackend(),
        )

        self.assertIsNotNone(service)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "focus_vision_sentinel_service")
        self.assertEqual(status.runtime_mode, "dry_run")
        self.assertIn("desk_presence_decision", status.capabilities)
        self.assertIn("phone_distraction_decision", status.capabilities)
        self.assertTrue(status.metadata["enabled"])

    def test_focus_vision_falls_back_when_import_fails(self) -> None:
        builder = _FailingFocusVisionBuilderProbe()

        service, status = builder._build_focus_vision(
            {"enabled": True},
            vision_backend=_FakeVisionBackend(),
        )

        self.assertIsNone(service)
        self.assertFalse(status.ok)
        self.assertTrue(status.fallback_used)
        self.assertEqual(status.selected_backend, "null_focus_vision")

    def test_builder_wires_pan_tilt_backend_to_focus_vision_service(self) -> None:
        builder = _FocusVisionBuilderProbe()
        sentinel = object()

        service, status = builder._build_focus_vision(
            {"enabled": True, "dry_run": True},
            vision_backend=_FakeVisionBackend(),
            pan_tilt_backend=sentinel,
        )

        self.assertIsNotNone(service)
        self.assertTrue(status.ok)
        self.assertIs(service.pan_tilt_backend, sentinel)

    def test_scan_disabled_means_no_move_delta_call(self) -> None:
        from unittest.mock import MagicMock

        from modules.features.focus_vision import (
            FocusVisionConfig,
            FocusVisionSentinelService,
            FocusVisionState,
            FocusVisionStateSnapshot,
        )
        from modules.features.focus_vision.models import FocusVisionDecision, FocusVisionEvidence

        pan_tilt = MagicMock()
        config = FocusVisionConfig(
            enabled=True,
            dry_run=False,
            pan_tilt_scan_enabled=False,
            absence_pending_scan_after_seconds=5.0,
            startup_grace_seconds=0.0,
        )
        service = FocusVisionSentinelService(
            vision_backend=MagicMock(),
            config=config,
            pan_tilt_backend=pan_tilt,
        )
        now = 100.0
        snapshot = FocusVisionStateSnapshot(
            current_state=FocusVisionState.ABSENT,
            stable_seconds=15.0,
            state_started_at=now - 15.0,
            updated_at=now,
            decision=FocusVisionDecision(
                state=FocusVisionState.ABSENT,
                confidence=0.8,
                reasons=("test",),
                observed_at=now,
                evidence=FocusVisionEvidence(),
            ),
        )
        service._apply_derived_presence_states(snapshot, now)
        pan_tilt.move_delta.assert_not_called()

    def test_movement_not_executed_keeps_state_away_pending_not_confirmed(self) -> None:
        from unittest.mock import MagicMock

        from modules.features.focus_vision import (
            FocusVisionConfig,
            FocusVisionSentinelService,
            FocusVisionState,
            FocusVisionStateSnapshot,
        )
        from modules.features.focus_vision.models import FocusVisionDecision, FocusVisionEvidence

        pan_tilt = MagicMock()
        pan_tilt.move_delta.return_value = {"movement_executed": False, "ok": False}
        pan_tilt.center.return_value = {"ok": True}

        vision_backend = MagicMock()
        vision_backend.latest_observation.return_value = None

        config = FocusVisionConfig(
            enabled=True,
            dry_run=False,
            pan_tilt_scan_enabled=True,
            absence_pending_scan_after_seconds=5.0,
            startup_grace_seconds=0.0,
        )
        service = FocusVisionSentinelService(
            vision_backend=vision_backend,
            config=config,
            pan_tilt_backend=pan_tilt,
        )
        service._run_micro_scan()
        self.assertEqual(service._micro_scan_result, "blocked",
                         "movement_executed=False must produce 'blocked', never 'not_found'")

        now = 200.0
        service._micro_scan_state = service._micro_scan_result
        snapshot = FocusVisionStateSnapshot(
            current_state=FocusVisionState.ABSENT,
            stable_seconds=20.0,
            state_started_at=now - 20.0,
            updated_at=now,
            decision=FocusVisionDecision(
                state=FocusVisionState.ABSENT,
                confidence=0.8,
                reasons=("test",),
                observed_at=now,
                evidence=FocusVisionEvidence(),
            ),
        )
        result = service._apply_derived_presence_states(snapshot, now)
        self.assertNotEqual(result.current_state, FocusVisionState.AWAY_CONFIRMED,
                            "blocked scan must never become AWAY_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
