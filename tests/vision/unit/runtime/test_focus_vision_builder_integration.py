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


if __name__ == "__main__":
    unittest.main()
