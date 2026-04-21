from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.fusion import build_camera_only_observation


class SnapshotBuilderTests(unittest.TestCase):
    def test_builds_camera_observation_with_runtime_contract_fields(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
            metadata={"camera_index": 0},
        )

        observation = build_camera_only_observation(packet)

        self.assertTrue(observation.detected)
        self.assertEqual(observation.labels, ["camera_online", "capture_backend:picamera2"])
        self.assertEqual(observation.metadata["frame_width"], 1280)
        self.assertEqual(observation.metadata["frame_height"], 720)
        self.assertEqual(observation.metadata["capture_backend"], "picamera2")


if __name__ == "__main__":
    unittest.main()