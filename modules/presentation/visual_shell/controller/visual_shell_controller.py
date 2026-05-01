from __future__ import annotations

from dataclasses import dataclass, field

from modules.presentation.visual_shell.contracts import (
    VisualCommand,
    VisualCommandName,
    VisualEvent,
    VisualState,
)
from modules.presentation.visual_shell.controller.state_mapper import VisualStateMapper
from modules.presentation.visual_shell.controller.voice_command_router import (
    VisualShellVoiceCommandRouter,
    VisualVoiceAction,
)
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
    voice_command_router: VisualShellVoiceCommandRouter = field(
        default_factory=VisualShellVoiceCommandRouter
    )

    def handle_event(self, event: VisualEvent) -> bool:
        command = self.state_mapper.command_for_event(event)
        return self.send_command(command)

    def handle_voice_text(
        self,
        text: str,
        *,
        source: str = "nexa-voice-builtins",
    ) -> bool:
        match = self.voice_command_router.match(text)
        if match is None:
            return False

        return self.handle_voice_action(match.action, source=source)

    def handle_voice_action(
        self,
        action: VisualVoiceAction,
        *,
        source: str = "nexa-voice-builtins",
    ) -> bool:
        if action == VisualVoiceAction.SHOW_TEMPERATURE:
            return self.show_current_temperature(source=source)

        if action == VisualVoiceAction.SHOW_BATTERY:
            return self.show_current_battery(source=source)

        if action == VisualVoiceAction.SHOW_TIME:
            return self.show_current_time(source=source)

        if action == VisualVoiceAction.SHOW_DATE:
            return self.show_current_date(source=source)

        if action == VisualVoiceAction.SHOW_DESKTOP:
            return self.show_desktop(source=source)

        if action == VisualVoiceAction.HIDE_DESKTOP:
            return self.hide_desktop(source=source)

        if action == VisualVoiceAction.SHOW_SELF:
            return self.show_self(source=source)

        if action == VisualVoiceAction.SHOW_EYES:
            return self.show_eyes(source=source, ensure_fullscreen=True)

        if action == VisualVoiceAction.LOOK_AT_USER:
            return self.show_eyes(source=source, ensure_fullscreen=False)

        if action == VisualVoiceAction.SHOW_FACE_CONTOUR:
            return self.show_face_contour(source=source)

        if action == VisualVoiceAction.START_SCANNING:
            return self.start_scanning(source=source)

        if action == VisualVoiceAction.RETURN_TO_IDLE:
            return self.return_to_idle(source=source)

        return False

    def set_state(
        self,
        state: VisualState,
        *,
        source: str = "nexa-runtime",
    ) -> bool:
        command = self.state_mapper.command_for_state(state, source=source)
        return self.send_command(command)

    def show_desktop(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_DESKTOP,
                payload={},
                source=source,
            )
        )

    def hide_desktop(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.HIDE_DESKTOP,
                payload={},
                source=source,
            )
        )

    def show_self(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command_sequence(
            [
                VisualCommand(
                    command=VisualCommandName.HIDE_DESKTOP,
                    payload={},
                    source=source,
                ),
                VisualCommand(
                    command=VisualCommandName.SHOW_SELF,
                    payload={},
                    source=source,
                ),
            ]
        )

    def show_eyes(
        self,
        *,
        source: str = "nexa-runtime",
        ensure_fullscreen: bool = True,
    ) -> bool:
        commands: list[VisualCommand] = []

        if ensure_fullscreen:
            commands.append(
                VisualCommand(
                    command=VisualCommandName.HIDE_DESKTOP,
                    payload={},
                    source=source,
                )
            )

        commands.append(
            VisualCommand(
                command=VisualCommandName.SHOW_EYES,
                payload={},
                source=source,
            )
        )

        return self.send_command_sequence(commands)

    def show_face_contour(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command_sequence(
            [
                VisualCommand(
                    command=VisualCommandName.HIDE_DESKTOP,
                    payload={},
                    source=source,
                ),
                VisualCommand(
                    command=VisualCommandName.SHOW_FACE_CONTOUR,
                    payload={},
                    source=source,
                ),
            ]
        )

    def start_scanning(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.START_SCANNING,
                payload={},
                source=source,
            )
        )

    def return_to_idle(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.RETURN_TO_IDLE,
                payload={},
                source=source,
            )
        )

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


    def show_current_date(self, *, source: str = "nexa-runtime") -> bool:
        from datetime import datetime
        now = datetime.now()
        date_text = f"{now.day:02d}.{now.month:02d}"
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_DATE,
                payload={"text": date_text},
                source=source,
            )
        )

    def show_current_time(self, *, source: str = "nexa-runtime") -> bool:
        from datetime import datetime
        now = datetime.now()
        time_text = f"{now.hour:02d}:{now.minute:02d}"
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_TIME,
                payload={"text": time_text},
                source=source,
            )
        )

    def show_help(
        self,
        *,
        language: str = "en",
        source: str = "nexa-runtime",
    ) -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_HELP,
                payload={"language": str(language or "en")},
                source=source,
            )
        )


    def show_timer_countdown(
        self,
        *,
        mode: str,
        remaining_seconds: int,
        total_seconds: int,
        label: str = "",
        color_state: str = "",
        source: str = "nexa-runtime",
    ) -> bool:
        safe_remaining = max(0, int(remaining_seconds))
        safe_total = max(0, int(total_seconds))
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.SHOW_TIMER_COUNTDOWN,
                payload={
                    "mode": str(mode or "timer"),
                    "remaining_seconds": safe_remaining,
                    "total_seconds": safe_total,
                    "label": str(label or ""),
                    "color_state": str(color_state or ""),
                },
                source=source,
            )
        )

    def clear_timer_countdown(self, *, source: str = "nexa-runtime") -> bool:
        return self.send_command(
            VisualCommand(
                command=VisualCommandName.CLEAR_TIMER_COUNTDOWN,
                payload={},
                source=source,
            )
        )

    def send_command(self, command: VisualCommand) -> bool:
        return self.transport.send(command.to_dict())

    def send_command_sequence(self, commands: list[VisualCommand]) -> bool:
        results = [self.send_command(command) for command in commands]
        return all(results)