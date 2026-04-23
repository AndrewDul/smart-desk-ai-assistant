from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.devices.vision.behavior.computer_work import ComputerWorkInterpreter
from modules.devices.vision.behavior.desk_activity import DeskActivityInterpreter
from modules.devices.vision.behavior.models import BehaviorSnapshot
from modules.devices.vision.behavior.phone_usage import PhoneUsageInterpreter
from modules.devices.vision.behavior.presence import PresenceInterpreter
from modules.devices.vision.behavior.study_activity import StudyActivityInterpreter
from modules.devices.vision.perception.models import PerceptionSnapshot


@dataclass(slots=True)
class BehaviorPipeline:
    presence_interpreter: PresenceInterpreter = field(default_factory=PresenceInterpreter)
    desk_activity_interpreter: DeskActivityInterpreter = field(default_factory=DeskActivityInterpreter)
    computer_work_interpreter: ComputerWorkInterpreter = field(default_factory=ComputerWorkInterpreter)
    phone_usage_interpreter: PhoneUsageInterpreter = field(default_factory=PhoneUsageInterpreter)
    study_activity_interpreter: StudyActivityInterpreter = field(default_factory=StudyActivityInterpreter)
    version: int = 2

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "BehaviorPipeline":
        payload = dict(raw or {})
        return cls(
            computer_work_interpreter=ComputerWorkInterpreter.from_mapping(payload),
            phone_usage_interpreter=PhoneUsageInterpreter.from_mapping(payload),
            study_activity_interpreter=StudyActivityInterpreter.from_mapping(payload),
            version=2,
        )

    def analyze(self, perception: PerceptionSnapshot) -> BehaviorSnapshot:
        presence = self.presence_interpreter.interpret(perception)
        desk_activity = self.desk_activity_interpreter.interpret(perception, presence)
        computer_work = self.computer_work_interpreter.interpret(perception, presence, desk_activity)
        phone_usage = self.phone_usage_interpreter.interpret(
            perception,
            presence,
            desk_activity,
            computer_work,
        )
        study_activity = self.study_activity_interpreter.interpret(
            perception,
            presence,
            desk_activity,
            computer_work,
            phone_usage,
        )

        return BehaviorSnapshot(
            presence=presence,
            desk_activity=desk_activity,
            computer_work=computer_work,
            phone_usage=phone_usage,
            study_activity=study_activity,
            metadata={
                "behavior_pipeline_version": self.version,
                "computer_work_active_threshold": self.computer_work_interpreter.active_threshold,
                "phone_usage_active_threshold": self.phone_usage_interpreter.active_threshold,
                "study_activity_active_threshold": self.study_activity_interpreter.active_threshold,
            },
        )