from __future__ import annotations

from dataclasses import dataclass, field

from modules.presentation.visual_shell.contracts import (
    VisualCommand,
    VisualEvent,
    VisualState,
)
from modules.presentation.visual_shell.controller.state_mapper import VisualStateMapper
from modules.presentation.visual_shell.transport.ipc_client import VisualShellTransport


@dataclass(slots=True)
class VisualShellController:
    """Runtime-facing controller for the NEXA Visual Shell."""

    transport: VisualShellTransport
    state_mapper: VisualStateMapper = field(default_factory=VisualStateMapper)

    def handle_event(self, event: VisualEvent) -> bool:
        command = self.state_mapper.command_for_event(event)
        return self.send_command(command)

    def set_state(
        self,
        state: VisualState,
        *,
        source: str = "nexa-runtime",
    ) -> bool:
        command = self.state_mapper.command_for_state(state, source=source)
        return self.send_command(command)

    def send_command(self, command: VisualCommand) -> bool:
        return self.transport.send(command.to_dict())