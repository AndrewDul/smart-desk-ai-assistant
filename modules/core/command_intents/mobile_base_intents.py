from __future__ import annotations

from modules.core.command_intents.intent import CommandIntentDefinition, CommandIntentDomain

_MOBILE_BASE_INTENTS = {
    "mobile_base.drive_mode": CommandIntentDefinition(
        key="mobile_base.drive_mode",
        domain=CommandIntentDomain.MOBILE_BASE,
        action="drive_mode_start",
    ),
    "mobile_base.stop": CommandIntentDefinition(
        key="mobile_base.stop",
        domain=CommandIntentDomain.MOBILE_BASE,
        action="drive_mode_stop",
    ),
}

def get_mobile_base_intent_definition(intent_key: str) -> CommandIntentDefinition | None:
    return _MOBILE_BASE_INTENTS.get(str(intent_key or "").strip())
