from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from modules.presentation.visual_shell.transport.message_codec import (
    VisualShellMessageCodec,
)


class VisualShellTransport(Protocol):
    """Transport contract used by the Visual Shell controller."""

    def send(self, message: dict[str, object]) -> bool:
        """Send a message to the Visual Shell renderer."""


@dataclass(slots=True)
class InMemoryVisualShellTransport:
    """Test-safe transport that stores outgoing messages in memory."""

    sent_messages: list[dict[str, object]] = field(default_factory=list)

    def send(self, message: dict[str, object]) -> bool:
        self.sent_messages.append(dict(message))
        return True


@dataclass(slots=True)
class EncodedVisualShellTransport:
    """Base transport helper for future socket/WebSocket implementations."""

    codec: VisualShellMessageCodec = field(default_factory=VisualShellMessageCodec)

    def encode_message(self, message: dict[str, object]) -> str:
        return self.codec.encode(message)