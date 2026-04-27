from __future__ import annotations

from enum import Enum


class VoiceTurnState(str, Enum):
    """Lifecycle state for one Voice Engine v2 turn."""

    CREATED = "created"
    COMMAND_RECOGNIZED = "command_recognized"
    INTENT_RESOLVED = "intent_resolved"
    FALLBACK_REQUIRED = "fallback_required"
    COMPLETED = "completed"
    REJECTED = "rejected"