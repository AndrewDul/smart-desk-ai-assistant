from modules.presentation.visual_shell.contracts import (
    VisualEvent,
    VisualEventName,
    VisualState,
)
from modules.presentation.visual_shell.controller import VisualShellController
from modules.presentation.visual_shell.transport import InMemoryVisualShellTransport


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
    