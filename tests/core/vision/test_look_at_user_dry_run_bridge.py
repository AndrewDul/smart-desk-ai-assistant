from __future__ import annotations

from modules.core.flows.action_flow.models import ResolvedAction
from modules.core.flows.action_flow.visual_shell_actions_mixin import ActionVisualShellActionsMixin
from modules.devices.vision.tracking import TrackingMotionPlan


class _FakeVisionTrackingService:
    def __init__(self) -> None:
        self.force_refresh_values: list[bool] = []

    def plan_once(self, *, force_refresh: bool = False) -> TrackingMotionPlan:
        self.force_refresh_values.append(force_refresh)
        return TrackingMotionPlan(
            has_target=True,
            target=None,
            pan_delta_degrees=0.5,
            tilt_delta_degrees=0.0,
            desired_pan_degrees=15.5,
            clamped_pan_degrees=15.0,
            pan_at_limit=True,
            base_yaw_assist_required=True,
            base_yaw_direction="right",
            base_forward_velocity=0.0,
            base_backward_velocity=0.0,
            reason="pan_limit_base_yaw_assist_required",
        )


class _FakeAssistant:
    def __init__(self) -> None:
        self.vision_tracking = _FakeVisionTrackingService()
        self._last_vision_tracking_plan: dict = {}


class _Harness(ActionVisualShellActionsMixin):
    def __init__(self, assistant: _FakeAssistant) -> None:
        self.assistant = assistant


def test_look_at_user_action_runs_tracking_dry_run_without_movement() -> None:
    assistant = _FakeAssistant()
    harness = _Harness(assistant)

    result = harness._handle_look_at_user(
        route=object(),
        language="en",
        payload={},
        resolved=ResolvedAction(
            name="look_at_user",
            payload={},
            source="voice_engine_v2_runtime_candidate",
            primary_intent="visual_shell.look_at_user",
        ),
    )

    assert result.handled is True
    assert result.response_delivered is False
    assert result.action == "look_at_user"
    assert result.status == "pan_limit_base_yaw_assist_required"
    assert assistant.vision_tracking.force_refresh_values == [False]

    assert result.metadata["dry_run"] is True
    assert result.metadata["movement_execution_enabled"] is False
    assert result.metadata["pan_tilt_movement_executed"] is False
    assert result.metadata["base_movement_executed"] is False
    assert result.metadata["base_yaw_assist_required"] is True
    assert result.metadata["base_yaw_direction"] == "right"
    assert result.metadata["base_yaw_assist_execution_enabled"] is False

    plan = result.metadata["vision_tracking_plan"]
    assert plan["base_forward_velocity"] == 0.0
    assert plan["base_backward_velocity"] == 0.0
    assert assistant._last_vision_tracking_plan["reason"] == "pan_limit_base_yaw_assist_required"


def test_look_at_user_action_is_handled_even_when_tracking_service_is_missing() -> None:
    class _AssistantWithoutTracking:
        pass

    harness = _Harness(_AssistantWithoutTracking())

    result = harness._handle_look_at_user(
        route=object(),
        language="pl",
        payload={},
        resolved=ResolvedAction(
            name="look_at_user",
            payload={},
            source="test",
            primary_intent="visual_shell.look_at_user",
        ),
    )

    assert result.handled is True
    assert result.response_delivered is False
    assert result.status == "vision_tracking_unavailable"
    assert result.metadata["vision_tracking_available"] is False
    assert result.metadata["movement_execution_enabled"] is False
    assert result.metadata["pan_tilt_movement_executed"] is False
    assert result.metadata["base_movement_executed"] is False
