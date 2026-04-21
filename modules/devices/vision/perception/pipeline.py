from __future__ import annotations

from dataclasses import dataclass, field

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import PerceptionSnapshot
from modules.devices.vision.perception.objects import NullObjectDetector, ObjectDetector
from modules.devices.vision.perception.people import NullPeopleDetector, PeopleDetector
from modules.devices.vision.perception.scene import NullSceneAnalyzer, SceneAnalyzer


@dataclass(slots=True)
class PerceptionPipeline:
    people_detector: PeopleDetector = field(default_factory=NullPeopleDetector)
    object_detector: ObjectDetector = field(default_factory=NullObjectDetector)
    scene_analyzer: SceneAnalyzer = field(default_factory=NullSceneAnalyzer)

    def analyze(self, packet: FramePacket) -> PerceptionSnapshot:
        people = tuple(self.people_detector.detect_people(packet))
        objects = tuple(self.object_detector.detect_objects(packet))
        scene = self.scene_analyzer.analyze_scene(packet, people, objects)

        return PerceptionSnapshot(
            frame_width=packet.width,
            frame_height=packet.height,
            people=people,
            objects=objects,
            scene=scene,
            metadata={
                "people_count": len(people),
                "object_count": len(objects),
            },
        )