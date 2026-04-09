from __future__ import annotations

from enum import Enum


class InputSource(str, Enum):
    """Normalized source of an incoming user turn."""

    VOICE = "voice"
    TEXT = "text"
    SYSTEM = "system"
    VISION = "vision"


class RouteKind(str, Enum):
    """High-level decision made by the understanding layer."""

    ACTION = "action"
    CONVERSATION = "conversation"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class StreamMode(str, Enum):
    """How NeXa should release spoken output."""

    WHOLE_RESPONSE = "whole_response"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


class ChunkKind(str, Enum):
    """Logical meaning of an assistant output chunk."""

    ACK = "ack"
    CONTENT = "content"
    TOOL_STATUS = "tool_status"
    FOLLOW_UP = "follow_up"
    ERROR = "error"
    FINAL = "final"


__all__ = [
    "ChunkKind",
    "InputSource",
    "RouteKind",
    "StreamMode",
]