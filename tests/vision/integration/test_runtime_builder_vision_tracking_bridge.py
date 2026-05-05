from __future__ import annotations

import unittest

from modules.runtime.builder.vision_mixin import RuntimeBuilderVisionMixin


class _FakeVisionBackend:
    def latest_observation(self, *, force_refresh: bool = True):
        del force_refresh
        return None

    def status(self) -> dict[str, object]:
        return {"ok": True, "backend": "fake_vision"}


class _FakePanTiltBackend:
    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "backend": "fake_pan_tilt",
            "safe_limits": {
                "pan_min_degrees": -15.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 15.0,
                "tilt_min_degrees": -8.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
        }


class _FakeVisionTrackingService:
    def __init__(
        self,
        *,
        vision_backend,
        pan_tilt_backend,
        config: dict[str, object],
    ) -> None:
        self.vision_backend = vision_backend
        self.pan_tilt_backend = pan_tilt_backend
        self.config = dict(config)

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "dry_run": True,
            "movement_execution_enabled": False,
            "last_plan": None,
        }


class _VisionTrackingBuilderProbe(RuntimeBuilderVisionMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        if module_name == "modules.devices.vision.tracking" and symbol_name == "VisionTrackingService":
            return _FakeVisionTrackingService
        raise AssertionError(f"Unexpected import request: {module_name}.{symbol_name}")


class _FailingVisionTrackingBuilderProbe(RuntimeBuilderVisionMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        del module_name, symbol_name
        raise RuntimeError("tracking import failure")


class RuntimeBuilderVisionTrackingBridgeTests(unittest.TestCase):
    def test_builds_dry_run_vision_tracking_service(self) -> None:
        builder = _VisionTrackingBuilderProbe()
        vision = _FakeVisionBackend()
        pan_tilt = _FakePanTiltBackend()

        service, status = builder._build_vision_tracking(
            {
                "enabled": True,
                "policy": {
                    "dead_zone_x": 0.08,
                    "dead_zone_y": 0.10,
                },
            },
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
        )

        self.assertIsInstance(service, _FakeVisionTrackingService)
        self.assertIs(service.vision_backend, vision)
        self.assertIs(service.pan_tilt_backend, pan_tilt)
        self.assertTrue(status.ok)
        self.assertEqual(status.component, "vision_tracking")
        self.assertEqual(status.selected_backend, "vision_tracking_service")
        self.assertEqual(status.runtime_mode, "dry_run")
        self.assertIn("target_selection", status.capabilities)
        self.assertTrue(status.metadata["dry_run"])
        self.assertFalse(status.metadata["movement_execution_enabled"])

    def test_tracking_service_can_be_disabled_without_error(self) -> None:
        builder = _VisionTrackingBuilderProbe()

        service, status = builder._build_vision_tracking(
            {"enabled": False},
            vision_backend=_FakeVisionBackend(),
            pan_tilt_backend=_FakePanTiltBackend(),
        )

        self.assertIsNone(service)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "disabled_vision_tracking")
        self.assertEqual(status.runtime_mode, "disabled")

    def test_tracking_service_falls_back_when_import_fails(self) -> None:
        builder = _FailingVisionTrackingBuilderProbe()

        service, status = builder._build_vision_tracking(
            {"enabled": True},
            vision_backend=_FakeVisionBackend(),
            pan_tilt_backend=_FakePanTiltBackend(),
        )

        self.assertIsNone(service)
        self.assertFalse(status.ok)
        self.assertTrue(status.fallback_used)
        self.assertEqual(status.selected_backend, "null_vision_tracking")


if __name__ == "__main__":
    unittest.main()
