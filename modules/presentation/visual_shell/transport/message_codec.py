from __future__ import annotations

import json
from typing import Any


class VisualShellMessageCodec:
    """Encodes Visual Shell messages into stable JSON payloads."""

    @staticmethod
    def encode(message: dict[str, Any]) -> str:
        return json.dumps(message, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def encode_line(message: dict[str, Any]) -> bytes:
        """Encode one line-delimited JSON message for local socket transport."""
        return (VisualShellMessageCodec.encode(message) + "\n").encode("utf-8")

    @staticmethod
    def decode(raw_message: str | bytes) -> dict[str, Any]:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        decoded = json.loads(raw_message)
        if not isinstance(decoded, dict):
            raise ValueError("Visual Shell message must decode to a JSON object.")

        return decoded

    @staticmethod
    def decode_line(raw_message: str | bytes) -> dict[str, Any]:
        """Decode one line-delimited JSON message."""
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        return VisualShellMessageCodec.decode(raw_message.strip())