from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.capture.reader import VisionCaptureReader
from modules.devices.vision.config import VisionRuntimeConfig


class _FakeSource:
    def __init__(self, backend_label: str, packet: FramePacket) -> None:
        self.backend_label = backend_label
        self.packet = packet
        self.open_called = False
        self.close_called = False

    def open(self) -> None:
        self.open_called = True

    def read_frame(self) -> FramePacket:
        return self.packet

    def close(self) -> None:
        self.close_called = True


class VisionCaptureReaderTests(unittest.TestCase):
    def test_uses_primary_source_when_it_opens_successfully(self) -> None:
        config = VisionRuntimeConfig.from_mapping({"enabled": True})
        primary = _FakeSource(
            backend_label="primary",
            packet=FramePacket(pixels=[[0]], width=1, height=1, channels=1, backend_label="primary"),
        )
        fallback = _FakeSource(
            backend_label="fallback",
            packet=FramePacket(pixels=[[1]], width=1, height=1, channels=1, backend_label="fallback"),
        )

        reader = VisionCaptureReader(
            config=config,
            primary_factory=lambda: primary,
            fallback_factory=lambda: fallback,
        )

        packet = reader.read_frame()

        self.assertEqual(packet.backend_label, "primary")
        self.assertTrue(primary.open_called)
        self.assertEqual(reader.active_backend, "primary")

    def test_falls_back_when_primary_factory_fails(self) -> None:
        config = VisionRuntimeConfig.from_mapping({"enabled": True})
        fallback = _FakeSource(
            backend_label="fallback",
            packet=FramePacket(pixels=[[1]], width=1, height=1, channels=1, backend_label="fallback"),
        )

        reader = VisionCaptureReader(
            config=config,
            primary_factory=lambda: (_ for _ in ()).throw(RuntimeError("primary failed")),
            fallback_factory=lambda: fallback,
        )

        packet = reader.read_frame()

        self.assertEqual(packet.backend_label, "fallback")
        self.assertTrue(fallback.open_called)
        self.assertEqual(reader.active_backend, "fallback")


if __name__ == "__main__":
    unittest.main()