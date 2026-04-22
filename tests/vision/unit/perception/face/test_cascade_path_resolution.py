from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.devices.vision.perception.face.opencv_haar_detector import OpenCvHaarFaceDetector


class OpenCvHaarCascadePathTests(unittest.TestCase):
    def test_candidate_paths_do_not_require_cv2_data_attribute(self) -> None:
        fake_cv2 = types.SimpleNamespace(__file__="/opt/fakecv2/cv2/__init__.py")
        detector = OpenCvHaarFaceDetector()

        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            paths = detector._candidate_cascade_paths()

        self.assertTrue(paths)
        self.assertTrue(all(isinstance(path, Path) for path in paths))
        self.assertIn(
            Path("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
            paths,
        )


if __name__ == "__main__":
    unittest.main()