from __future__ import annotations

import socket
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
    """Base transport helper for socket/WebSocket implementations."""

    codec: VisualShellMessageCodec = field(default_factory=VisualShellMessageCodec)

    def encode_message(self, message: dict[str, object]) -> str:
        return self.codec.encode(message)

    def encode_message_line(self, message: dict[str, object]) -> bytes:
        return self.codec.encode_line(message)


@dataclass(slots=True)
class TcpVisualShellTransport(EncodedVisualShellTransport):
    """Best-effort local TCP transport for the Godot Visual Shell.

    The transport intentionally fails softly by default. Visual Shell must never
    become a hard dependency for the core assistant runtime.
    """

    host: str = "127.0.0.1"
    port: int = 8765
    timeout_sec: float = 0.15
    raise_on_failure: bool = False

    def send(self, message: dict[str, object]) -> bool:
        payload = self.encode_message_line(message)

        try:
            with socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_sec,
            ) as sock:
                sock.sendall(payload)
            return True

        except OSError:
            if self.raise_on_failure:
                raise

            return False