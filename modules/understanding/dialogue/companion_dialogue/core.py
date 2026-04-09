from __future__ import annotations

from typing import Any

from modules.shared.config.settings import load_settings
from modules.understanding.dialogue.conversation_memory import ConversationMemory

from .content_bank import FACT_BANK, HUMOUR_BANK, RIDDLE_BANK
from .content_helpers_mixin import CompanionDialogueContentHelpersMixin
from .contract_helpers_mixin import CompanionDialogueContractHelpersMixin
from .deterministic_mixin import CompanionDialogueDeterministicMixin
from .local_llm_mixin import CompanionDialogueLocalLLMMixin
from .memory_mixin import CompanionDialogueMemoryMixin
from .reply_api_mixin import CompanionDialogueReplyApiMixin
from .templates_mixin import CompanionDialogueTemplatesMixin
from .text_helpers_mixin import CompanionDialogueTextHelpersMixin


class CompanionDialogueService(
    CompanionDialogueContractHelpersMixin,
    CompanionDialogueMemoryMixin,
    CompanionDialogueContentHelpersMixin,
    CompanionDialogueTextHelpersMixin,
    CompanionDialogueDeterministicMixin,
    CompanionDialogueTemplatesMixin,
    CompanionDialogueLocalLLMMixin,
    CompanionDialogueReplyApiMixin,
):
    """
    Offline-first dialogue service for NeXa.

    Behaviour:
    - deterministic and fast by default
    - practical and supportive tone
    - optional local-LLM hook if available later
    - never executes tools by itself
    """

    def __init__(self) -> None:
        self.settings = load_settings()

        conversation_cfg = self.settings.get("conversation", {})
        streaming_cfg = self.settings.get("streaming", {})

        self.conversation_memory = ConversationMemory(
            max_turns=int(conversation_cfg.get("max_turns", 8)),
            max_total_chars=int(conversation_cfg.get("max_total_chars", 1800)),
            max_turn_chars=int(conversation_cfg.get("max_turn_chars", 260)),
        )

        self.default_stream_mode = self._resolve_stream_mode(
            streaming_cfg.get("dialogue_stream_mode", "sentence")
        )

        self._humour_index = 0
        self._riddle_index = 0
        self._fact_index = 0

        self._humour_bank = HUMOUR_BANK
        self._riddle_bank = RIDDLE_BANK
        self._fact_bank = FACT_BANK

        self.local_llm = self._try_build_local_llm()


__all__ = ["CompanionDialogueService"]