from __future__ import annotations

from dataclasses import dataclass, field

from modules.presentation.visual_shell.contracts import (
    VisualCommand,
    VisualCommandName,
    VisualEvent,
    VisualState,
)
from modules.presentation.visual_shell.controller.state_mapper import VisualStateMapper
from modules.presentation.visual_shell.service import VisualShellSystemMetricsProvider
from modules.presentation.visual_shell.transport.ipc_client import VisualShellTransport


@dataclass(slots=True)
class VisualShellController:
    """Runtime-facing controller for the NEXA Visual Shell."""

    transport: VisualShellTransport
    state_mapper: VisualStateMapper = field(default_factory=VisualStateMapper)
    metrics_provider: VisualShellSystemMetricsProvider = field(
        default_factory=VisualShellSystemMetricsProvider
    )

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

    def show_temperature(
        self,
        value_c: int,
        *,
        source: str = "nexa-runtime",
    ) -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_TEMPERATURE,
                payload={"value_c": int(value_c)},
                source=source,
            )
        )

    def show_battery(
        self,
        percent: int,
        *,
        source: str = "nexa-runtime",
    ) -> bool:
        clamped_percent = max(0, min(100, int(percent)))

        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_BATTERY,
                payload={"percent": clamped_percent},
                source=source,
            )
        )

    def show_current_temperature(self, *, source: str = "nexa-runtime") -> bool:
        reading = self.metrics_provider.read_temperature()
        if reading is None:
            return self.report_degraded(
                reason="temperature_unavailable",
                source=source,
            )

        return self.show_temperature(reading.value_c, source=source)

    def show_current_battery(self, *, source: str = "nexa-runtime") -> bool:
        reading = self.metrics_provider.read_battery()
        if reading is None:
            return self.report_degraded(
                reason="battery_unavailable",
                source=source,
            )

        return self.show_battery(reading.percent, source=source)

    def report_degraded(
        self,
        *,
        reason: str,
        source: str = "nexa-runtime",
    ) -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.REPORT_DEGRADED,
                payload={"reason": reason},
                source=source,
            )
        )

    def send_command(self, command: VisualCommand) -> bool:
        return self.transport.send(command.to_dict())