from __future__ import annotations

import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from modules.devices.vision.camera_service import CameraService


def _max_people_confidence(observation) -> float:
    perception = observation.metadata.get("perception", {})
    people = perception.get("people", [])
    if not people:
        return 0.0
    return max(float(person.get("confidence", 0.0)) for person in people)


def _max_face_confidence(observation) -> float:
    perception = observation.metadata.get("perception", {})
    faces = perception.get("faces", [])
    if not faces:
        return 0.0
    return max(float(face.get("confidence", 0.0)) for face in faces)


def _score_observation(observation) -> tuple[int, int, int, int, float, float]:
    perception = observation.metadata.get("perception", {})
    people_count = int(perception.get("people_count", 0))
    face_count = int(perception.get("face_count", 0))
    engagement_face_count = int(perception.get("engagement_face_count", 0))
    user_present = 1 if observation.user_present else 0
    return (
        int(observation.desk_active),
        user_present,
        engagement_face_count,
        face_count,
        _max_face_confidence(observation),
        _max_people_confidence(observation),
    )


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
            "people_detector_min_confidence": 0.40,
            "people_detector_min_area_ratio": 0.02,
            "people_detector_min_height_ratio": 0.15,
            "people_detector_max_width_ratio": 0.85,
            "people_detector_use_clahe": True,
            "people_detector_upscale_factor": 1.5,
            "people_detector_desk_roi_enabled": True,
            "people_detector_roi_x_min": 0.10,
            "people_detector_roi_y_min": 0.08,
            "people_detector_roi_x_max": 0.90,
            "people_detector_roi_y_max": 0.98,
            "face_detection_enabled": True,
            "face_detector_backend": "opencv_haar",
            "face_detector_min_area_ratio": 0.002,
            "face_detector_use_clahe": True,
            "face_detector_roi_enabled": True,
        }
    )

    try:
        observations = []
        for _ in range(6):
            observation = service.latest_observation(force_refresh=True)
            if observation is not None:
                observations.append(observation)

            time.sleep(0.25)

        print("Vision people detection smoke OK")
        print(json.dumps(service.status(), indent=2, default=str))

        if not observations:
            print("No observations captured.")
            return

        best = max(observations, key=_score_observation)

        frame_summaries = []
        for idx, observation in enumerate(observations, start=1):
            perception = observation.metadata.get("perception", {})
            frame_summaries.append(
                {
                    "frame": idx,
                    "people_count": perception.get("people_count"),
                    "face_count": perception.get("face_count"),
                    "engagement_face_count": perception.get("engagement_face_count"),
                    "user_present": observation.user_present,
                    "desk_active": observation.desk_active,
                    "max_people_confidence": _max_people_confidence(observation),
                    "max_face_confidence": _max_face_confidence(observation),
                    "labels": observation.labels,
                }
            )

        best_perception = best.metadata.get("perception", {})
        print(
            json.dumps(
                {
                    "best_labels": best.labels,
                    "best_user_present": best.user_present,
                    "best_desk_active": best.desk_active,
                    "best_people_count": best_perception.get("people_count"),
                    "best_face_count": best_perception.get("face_count"),
                    "best_engagement_face_count": best_perception.get("engagement_face_count"),
                    "best_people": best_perception.get("people"),
                    "best_faces": best_perception.get("faces"),
                    "best_behavior": best.metadata.get("behavior", {}),
                    "best_sessions": best.metadata.get("sessions", {}),
                    "frames": frame_summaries,
                },
                indent=2,
                default=str,
            )
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()