from __future__ import annotations

from typing import Any

from modules.shared.logging.logger import get_logger

from .context import NotificationFlowContext
from .delivery import NotificationFlowDelivery
from .helpers import NotificationFlowHelpers
from .internals import NotificationFlowInternals
from .reminders import NotificationFlowReminders

LOGGER = get_logger(__name__)


class NotificationFlowOrchestrator(
    NotificationFlowContext,
    NotificationFlowReminders,
    NotificationFlowDelivery,
    NotificationFlowInternals,
    NotificationFlowHelpers,
):
    """
    Premium async notification delivery for NeXa.

    Responsibilities:
    - interrupt current interaction safely when a higher-priority notification appears
    - keep display + spoken output aligned
    - deliver timer/reminder notifications without corrupting session state
    - remember notification turns in dialogue memory
    - stay resilient even when one subsystem is temporarily degraded
    """

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant
        coordination_cfg = getattr(assistant, "settings", {}).get("audio_coordination", {})
        self.interrupt_settle_seconds = max(
            float(coordination_cfg.get("notification_interrupt_settle_seconds", 0.05)),
            0.0,
        )


__all__ = ["NotificationFlowOrchestrator"]