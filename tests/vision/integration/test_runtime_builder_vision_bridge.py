from __future__ import annotations

import unittest

from modules.runtime.builder.fallbacks import NullVisionBackend
from modules.runtime.builder.vision_mixin import RuntimeBuilderVisionMixin


class _FakeCameraService:
    def __init__(self, config: dict[str, object]) -> None:
        self.config = dict(config)

    def latest_observation(self, *, force_refresh: bool = True):
        del force_refresh
        return None

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "backend": "fake_camera_service",
        }

    def close(self) -> None:
        return None


class _VisionBuilderProbe(RuntimeBuilderVisionMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        if module_name == "modules.devices.vision.camera_service" and symbol_name == "CameraService":
            return _FakeCameraService
        raise AssertionError(f"Unexpected import request: {module_name}.{symbol_name}")


class _FailingVisionBuilderProbe(RuntimeBuilderVisionMixin):
    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        raise RuntimeError("vision import failure")


class RuntimeBuilderVisionMixinTests(unittest.TestCase):
    def test_builds_real_camera_service_when_vision_is_enabled(self) -> None:
        builder = _VisionBuilderProbe()

        backend, status = builder._build_vision(
            {
                "enabled": True,
                "backend": "picamera2",
                "fallback_backend": "opencv",
            }
        )

        self.assertIsInstance(backend, _FakeCameraService)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "camera_service")
        self.assertFalse(status.fallback_used)

    def test_falls_back_to_null_vision_when_backend_import_fails(self) -> None:
        builder = _FailingVisionBuilderProbe()

        backend, status = builder._build_vision(
            {
                "enabled": True,
                "backend": "picamera2",
            }
        )

        self.assertIsInstance(backend, NullVisionBackend)
        self.assertFalse(status.ok)
        self.assertTrue(status.fallback_used)
        self.assertEqual(status.selected_backend, "null_vision")

    def test_returns_null_vision_when_feature_is_disabled(self) -> None:
        builder = _VisionBuilderProbe()

        backend, status = builder._build_vision({"enabled": False})

        self.assertIsInstance(backend, NullVisionBackend)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "null_vision")


if __name__ == "__main__":
    unittest.main()