from __future__ import annotations

from dataclasses import dataclass, field

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.face import FaceDetector, NullFaceDetector
from modules.devices.vision.perception.factory import build_face_detector, build_object_detector, build_people_detector
from modules.devices.vision.perception.models import PerceptionSnapshot
from modules.devices.vision.perception.objects import NullObjectDetector, ObjectDetector
from modules.devices.vision.perception.people import NullPeopleDetector, PeopleDetector
from modules.devices.vision.perception.scene import NullSceneAnalyzer, SceneAnalyzer


@dataclass(slots=True)
class PerceptionPipeline:
    people_detector: PeopleDetector = field(default_factory=NullPeopleDetector)
    face_detector: FaceDetector = field(default_factory=NullFaceDetector)
    object_detector: ObjectDetector = field(default_factory=NullObjectDetector)
    scene_analyzer: SceneAnalyzer = field(default_factory=NullSceneAnalyzer)

    @classmethod
    def from_config(cls, config: VisionRuntimeConfig) -> "PerceptionPipeline":
        return cls(
            people_detector=build_people_detector(config),
            face_detector=build_face_detector(config),
            object_detector=build_object_detector(config),
            scene_analyzer=NullSceneAnalyzer(),
        )

    def detector_status(self) -> dict[str, str]:
        return {
            "people": str(getattr(self.people_detector, "backend_label", type(self.people_detector).__name__.lower())),
            "face": str(getattr(self.face_detector, "backend_label", type(self.face_detector).__name__.lower())),
            "objects": str(getattr(self.object_detector, "backend_label", type(self.object_detector).__name__.lower())),
            "scene": str(getattr(self.scene_analyzer, "backend_label", type(self.scene_analyzer).__name__.lower())),
        }

    def analyze(self, packet: FramePacket) -> PerceptionSnapshot:
        people = tuple(self.people_detector.detect_people(packet))
        faces = tuple(self.face_detector.detect_faces(packet))
        objects = tuple(self.object_detector.detect_objects(packet))
        scene = self.scene_analyzer.analyze_scene(packet, people, faces, objects)

        return PerceptionSnapshot(
            frame_width=packet.width,
            frame_height=packet.height,
            people=people,
            faces=faces,
            objects=objects,
            scene=scene,
            metadata={
                "people_count": len(people),
                "face_count": len(faces),
                "object_count": len(objects),
                "detectors": self.detector_status(),
            },
        )