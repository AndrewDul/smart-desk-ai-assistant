from __future__ import annotations

from modules.presentation.visual_shell.contracts import (
    VisualCommand,
    VisualCommandName,
    VisualEvent,
    VisualEventName,
    VisualState,
)


_EVENT_TO_STATE: dict[VisualEventName, VisualState] = {
    VisualEventName.BOOT_READY: VisualState.IDLE_PARTICLE_CLOUD,
    VisualEventName.WAKE_DETECTED: VisualState.LISTENING_CLOUD,
    VisualEventName.LISTENING_STARTED: VisualState.LISTENING_CLOUD,
    VisualEventName.LISTENING_FINISHED: VisualState.THINKING_SWARM,
    VisualEventName.THINKING_STARTED: VisualState.THINKING_SWARM,
    VisualEventName.SPEAKING_STARTED: VisualState.SPEAKING_PULSE,
    VisualEventName.SPEAKING_FINISHED: VisualState.IDLE_PARTICLE_CLOUD,
    VisualEventName.VISION_SCAN_STARTED: VisualState.SCANNING_EYES,
    VisualEventName.VISION_SCAN_FINISHED: VisualState.IDLE_PARTICLE_CLOUD,
    VisualEventName.DESKTOP_REQUESTED: VisualState.DESKTOP_DOCKED,
    VisualEventName.ASSISTANT_SCREEN_REQUESTED: VisualState.DESKTOP_HIDDEN,
    VisualEventName.SHOW_SELF_REQUESTED: VisualState.SHOW_SELF_EYES,
    VisualEventName.DEGRADED: VisualState.ERROR_DEGRADED,
}


class VisualStateMapper:
    """Maps NEXA runtime events to Visual Shell commands."""

    def command_for_event(self, event: VisualEvent) -> VisualCommand:
        state = _EVENT_TO_STATE.get(event.name, VisualState.IDLE_PARTICLE_CLOUD)

        return VisualCommand(
            command=VisualCommandName.SET_STATE,
            payload={
                "state": state.value,
                **event.payload,
            },
            source=event.source,
        )

    def command_for_state(
        self,
        state: VisualState,
        *,
        source: str = "nexa-runtime",
    ) -> VisualCommand:
        return VisualCommand(
            command=VisualCommandName.SET_STATE,
            payload={"state": state.value},
            source=source,
        )