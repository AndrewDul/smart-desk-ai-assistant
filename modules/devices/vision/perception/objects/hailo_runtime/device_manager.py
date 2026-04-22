# modules/devices/vision/perception/objects/hailo_runtime/device_manager.py
from __future__ import annotations

import threading
from typing import Any

from modules.shared.logging.logger import get_logger

from .errors import HailoUnavailableError

LOGGER = get_logger(__name__)

# Module-level singleton instance. Accessed only via get_hailo_device_manager().
_singleton_lock = threading.Lock()
_singleton_instance: "HailoDeviceManager | None" = None


class HailoDeviceManager:
    """
    Singleton owner of the Hailo VDevice for the NeXa vision subsystem.

    Responsibilities:
    - Open exactly one VDevice per NeXa process and hold it for the lifetime
      of the application.
    - Hand out the shared VDevice to inference runners on request.
    - Serialize all inference calls behind a single lock so that multiple
      runners (e.g. object detection + future segmentation) cannot race on
      the same device handle.
    - Release the VDevice cleanly on close().

    This class does NOT load any HEF itself — that is the job of
    HefInferenceRunner. It only manages the device handle.
    """

    def __init__(self, *, hailo_platform_module: Any | None = None) -> None:
        # hailo_platform_module injection exists for tests. Production callers
        # leave it None and the real import happens lazily in open().
        self._hailo_platform = hailo_platform_module

        self._lifecycle_lock = threading.RLock()
        self._inference_lock = threading.Lock()

        self._vdevice: Any | None = None
        self._opened = False
        self._closed = False
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self) -> None:
        """
        Open the Hailo VDevice. Safe to call multiple times — subsequent calls
        are no-ops as long as the device is already open and not closed.
        """
        with self._lifecycle_lock:
            if self._closed:
                raise HailoUnavailableError("HailoDeviceManager has already been closed.")

            if self._opened:
                return

            hp = self._resolve_hailo_platform()
            try:
                params = hp.VDevice.create_params()
                self._vdevice = hp.VDevice(params)
                self._opened = True
                self._last_error = None
                LOGGER.info("HailoDeviceManager: VDevice opened successfully.")
            except Exception as error:
                self._last_error = f"{error.__class__.__name__}: {error}"
                LOGGER.warning("HailoDeviceManager: failed to open VDevice. %s", self._last_error)
                raise HailoUnavailableError(f"Failed to open VDevice: {error}") from error

    def close(self) -> None:
        """Close the VDevice and mark the manager as closed permanently."""
        with self._lifecycle_lock:
            if self._closed:
                return

            if self._vdevice is not None:
                try:
                    release_method = getattr(self._vdevice, "release", None)
                    if callable(release_method):
                        release_method()
                    else:
                        del self._vdevice
                except Exception as error:
                    LOGGER.warning("HailoDeviceManager: error during VDevice release. %s", error)

            self._vdevice = None
            self._opened = False
            self._closed = True
            LOGGER.info("HailoDeviceManager: VDevice closed.")

    def is_ready(self) -> bool:
        with self._lifecycle_lock:
            return self._opened and not self._closed and self._vdevice is not None

    def vdevice(self) -> Any:
        """
        Return the active VDevice handle. Raises if the manager is not open.
        The caller must hold inference_lock() around any device interaction.
        """
        with self._lifecycle_lock:
            if not self.is_ready():
                raise HailoUnavailableError(
                    "HailoDeviceManager is not open. Call open() first."
                )
            return self._vdevice

    def inference_lock(self) -> threading.Lock:
        """
        Return the inference serialization lock. Inference runners must acquire
        this before calling into the device.
        """
        return self._inference_lock

    def status(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            return {
                "opened": self._opened,
                "closed": self._closed,
                "ready": self.is_ready(),
                "last_error": self._last_error,
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_hailo_platform(self) -> Any:
        if self._hailo_platform is not None:
            return self._hailo_platform

        try:
            import hailo_platform as hp
        except ImportError as error:
            raise HailoUnavailableError(
                "hailo_platform Python module is not installed."
            ) from error

        self._hailo_platform = hp
        return hp


def get_hailo_device_manager() -> HailoDeviceManager:
    """
    Return the process-wide HailoDeviceManager singleton.

    The singleton is lazily instantiated on first access. It is NOT opened
    automatically — the caller must invoke open() when appropriate
    (typically at vision pipeline boot).
    """
    global _singleton_instance
    with _singleton_lock:
        if _singleton_instance is None:
            _singleton_instance = HailoDeviceManager()
        return _singleton_instance


def _reset_hailo_device_manager_for_tests() -> None:
    """Test-only helper to reset the module-level singleton."""
    global _singleton_instance
    with _singleton_lock:
        _singleton_instance = None