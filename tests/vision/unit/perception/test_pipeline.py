from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception import PerceptionPipeline


class PerceptionPipelineTests(unittest.TestCase):
    def test_pipeline_returns_empty_snapshot_with_default_null_detectors(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        snapshot = PerceptionPipeline().analyze(packet)

        self.assertEqual(snapshot.frame_width, 1280)
        self.assertEqual(snapshot.frame_height, 720)
        self.assertEqual(len(snapshot.people), 0)
        self.assertEqual(len(snapshot.faces), 0)
        self.assertEqual(len(snapshot.objects), 0)
        self.assertEqual(snapshot.scene.desk_zone_people_count, 0)
        self.assertEqual(snapshot.scene.screen_candidate_count, 0)
        self.assertEqual(snapshot.scene.handheld_candidate_count, 0)


if __name__ == "__main__":
    unittest.main()