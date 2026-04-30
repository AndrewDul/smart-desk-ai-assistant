from modules.presentation.visual_shell.controller.voice_command_router import VisualVoiceAction
from dataclasses import dataclass

from modules.presentation.visual_shell.contracts import (
    VisualCommand,
    VisualCommandName,
    VisualEvent,
    VisualEventName,
    VisualState,
)
from modules.presentation.visual_shell.controller import VisualShellController
from modules.presentation.visual_shell.service import BatteryReading, TemperatureReading
from modules.presentation.visual_shell.transport import (
    InMemoryVisualShellTransport,
    TcpVisualShellTransport,
    VisualShellMessageCodec,
)


@dataclass(slots=True)
class StubMetricsProvider:
    temperature: TemperatureReading | None = TemperatureReading(
        value_c=57,
        raw_value_c=57.4,
        source="stub",
    )
    battery: BatteryReading | None = BatteryReading(
        percent=82,
        source="stub",
    )

    def read_temperature(self) -> TemperatureReading | None:
        return self.temperature

    def read_battery(self) -> BatteryReading | None:
        return self.battery


def test_visual_shell_controller_maps_wake_event_to_listening_state() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_event(VisualEvent(name=VisualEventName.WAKE_DETECTED))

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SET_STATE",
            "payload": {"state": "LISTENING_CLOUD"},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_can_set_scanning_state_directly() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.set_state(VisualState.SCANNING_EYES)

    assert result is True
    assert transport.sent_messages[0]["payload"]["state"] == "SCANNING_EYES"


def test_visual_state_supports_metric_glyph_states() -> None:
    assert VisualState.coerce("temperature_glyph") == VisualState.TEMPERATURE_GLYPH
    assert VisualState.coerce("battery_glyph") == VisualState.BATTERY_GLYPH


def test_visual_command_supports_temperature_and_battery_commands() -> None:
    temperature_command = VisualCommand(
        command=VisualCommandName.SHOW_TEMPERATURE,
        payload={"value_c": 57},
    )
    battery_command = VisualCommand(
        command=VisualCommandName.SHOW_BATTERY,
        payload={"percent": 82},
    )

    assert temperature_command.to_dict() == {
        "command": "SHOW_TEMPERATURE",
        "payload": {"value_c": 57},
        "source": "nexa-runtime",
    }
    assert battery_command.to_dict() == {
        "command": "SHOW_BATTERY",
        "payload": {"percent": 82},
        "source": "nexa-runtime",
    }


def test_visual_shell_controller_sends_explicit_temperature_metric() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.show_temperature(58)

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_TEMPERATURE",
            "payload": {"value_c": 58},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_sends_explicit_battery_metric() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.show_battery(141)

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_BATTERY",
            "payload": {"percent": 100},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_sends_current_temperature_metric() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(),
    )

    result = controller.show_current_temperature()

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_TEMPERATURE",
            "payload": {"value_c": 57},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_sends_current_battery_metric() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(),
    )

    result = controller.show_current_battery()

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "SHOW_BATTERY",
            "payload": {"percent": 82},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_reports_degraded_when_temperature_is_unavailable() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(temperature=None),
    )

    result = controller.show_current_temperature()

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "REPORT_DEGRADED",
            "payload": {"reason": "temperature_unavailable"},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_controller_reports_degraded_when_battery_is_unavailable() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(
        transport=transport,
        metrics_provider=StubMetricsProvider(battery=None),
    )

    result = controller.show_current_battery()

    assert result is True
    assert transport.sent_messages == [
        {
            "command": "REPORT_DEGRADED",
            "payload": {"reason": "battery_unavailable"},
            "source": "nexa-runtime",
        }
    ]


def test_visual_shell_message_codec_supports_line_delimited_json() -> None:
    message = {
        "command": "SET_STATE",
        "payload": {"state": "SPEAKING_PULSE"},
        "source": "test",
    }

    encoded = VisualShellMessageCodec.encode_line(message)

    assert encoded.endswith(b"\n")
    assert VisualShellMessageCodec.decode_line(encoded) == message


def test_tcp_visual_shell_transport_fails_softly_when_renderer_is_unavailable() -> None:
    transport = TcpVisualShellTransport(
        host="127.0.0.1",
        port=1,
        timeout_sec=0.01,
    )

    result = transport.send(
        {
            "command": "SET_STATE",
            "payload": {"state": "IDLE_PARTICLE_CLOUD"},
            "source": "test",
        }
    )

    assert result is False

def test_visual_shell_controller_handles_show_time_voice_action() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_action(VisualVoiceAction.SHOW_TIME)

    assert result is True
    assert transport.sent_messages[-1]["command"] == "SHOW_TIME"
    assert transport.sent_messages[-1]["payload"]["text"]


def test_visual_shell_controller_handles_show_date_voice_action() -> None:
    transport = InMemoryVisualShellTransport()
    controller = VisualShellController(transport=transport)

    result = controller.handle_voice_action(VisualVoiceAction.SHOW_DATE)

    assert result is True
    assert transport.sent_messages[-1]["command"] == "SHOW_DATE"
    assert transport.sent_messages[-1]["payload"]["text"]
