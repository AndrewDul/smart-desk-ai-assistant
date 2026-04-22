# tests/vision/unit/perception/objects/hailo_runtime/test_device_manager.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from modules.devices.vision.perception.objects.hailo_runtime.device_manager import (
    HailoDeviceManager,
    _reset_hailo_device_manager_for_tests,
    get_hailo_device_manager,
)
from modules.devices.vision.perception.objects.hailo_runtime.errors import (
    HailoUnavailableError,
)


def _make_fake_hailo_platform(raise_on_create: bool = False) -> MagicMock:
    fake = MagicMock(name="hailo_platform_fake")
    fake_params = MagicMock(name="vdevice_params")
    fake.VDevice.create_params.return_value = fake_params

    if raise_on_create:
        fake.VDevice.side_effect = RuntimeError("simulated device open failure")
    else:
        fake_vdevice = MagicMock(name="vdevice_instance")
        fake.VDevice.return_value = fake_vdevice

    return fake


class HailoDeviceManagerTests(unittest.TestCase):

    def setUp(self) -> None:
        _reset_hailo_device_manager_for_tests()

    def tearDown(self) -> None:
        _reset_hailo_device_manager_for_tests()

    # ------------------------------------------------------------------
    # Open / close lifecycle
    # ------------------------------------------------------------------

    def test_is_ready_false_before_open(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)
        self.assertFalse(mgr.is_ready())

    def test_open_creates_vdevice_and_marks_ready(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)

        mgr.open()

        self.assertTrue(mgr.is_ready())
        fake_hp.VDevice.create_params.assert_called_once()
        fake_hp.VDevice.assert_called_once()

    def test_open_is_idempotent(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)

        mgr.open()
        mgr.open()

        fake_hp.VDevice.assert_called_once()

    def test_open_raises_unavailable_on_device_failure(self) -> None:
        fake_hp = _make_fake_hailo_platform(raise_on_create=True)
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)

        with self.assertRaises(HailoUnavailableError):
            mgr.open()

        self.assertFalse(mgr.is_ready())

    def test_close_releases_vdevice(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)
        mgr.open()

        mgr.close()

        self.assertFalse(mgr.is_ready())
        status = mgr.status()
        self.assertFalse(status["opened"])
        self.assertTrue(status["closed"])

    def test_close_is_idempotent(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)
        mgr.open()

        mgr.close()
        mgr.close()  # Must not raise

        self.assertTrue(mgr.status()["closed"])

    def test_reopen_after_close_raises(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)
        mgr.open()
        mgr.close()

        with self.assertRaises(HailoUnavailableError):
            mgr.open()

    # ------------------------------------------------------------------
    # vdevice() access
    # ------------------------------------------------------------------

    def test_vdevice_raises_when_not_open(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)

        with self.assertRaises(HailoUnavailableError):
            mgr.vdevice()

    def test_vdevice_returns_handle_when_open(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)
        mgr.open()

        handle = mgr.vdevice()
        self.assertIsNotNone(handle)

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    def test_inference_lock_returns_same_lock_instance(self) -> None:
        fake_hp = _make_fake_hailo_platform()
        mgr = HailoDeviceManager(hailo_platform_module=fake_hp)

        lock_a = mgr.inference_lock()
        lock_b = mgr.inference_lock()
        self.assertIs(lock_a, lock_b)

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def test_get_hailo_device_manager_returns_same_instance(self) -> None:
        first = get_hailo_device_manager()
        second = get_hailo_device_manager()
        self.assertIs(first, second)

    def test_missing_hailo_platform_raises_unavailable(self) -> None:
        class _MissingModuleManager(HailoDeviceManager):
            def _resolve_hailo_platform(self):
                raise HailoUnavailableError("hailo_platform not installed")

        mgr = _MissingModuleManager()
        with self.assertRaises(HailoUnavailableError):
            mgr.open()


if __name__ == "__main__":
    unittest.main()