from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.devices.vision.camera_service import CameraService


def main() -> None:
    service = CameraService(
        config={
            "enabled": True,
            "backend": "picamera2",
            "fallback_backend": "opencv",
            "camera_index": 0,
            "frame_width": 1280,
            "frame_height": 720,
            "lazy_start": True,
            "people_detection_enabled": True,
            "people_detector_backend": "opencv_hog",
            "people_detector_min_confidence": 0.45,
            "people_detector_min_area_ratio": 0.025,
        }
    )

    try:
        observation = service.latest_observation(force_refresh=True)
        print("Vision people detection smoke OK")
        print(json.dumps(service.status(), indent=2, default=str))

        if observation is None:
            print("No observation captured.")
            return

        perception = observation.metadata.get("perception", {})
        print(
            json.dumps(
                {
                    "labels": observation.labels,
                    "user_present": observation.user_present,
                    "desk_active": observation.desk_active,
                    "people_count": perception.get("people_count"),
                    "people": perception.get("people"),
                    "behavior": observation.metadata.get("behavior", {}),
                    "sessions": observation.metadata.get("sessions", {}),
                },
                indent=2,
                default=str,
            )
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()