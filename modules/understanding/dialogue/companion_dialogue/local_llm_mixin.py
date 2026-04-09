from __future__ import annotations

import importlib.util
from typing import Any

from modules.shared.logging.logger import append_log

from .models import DialogueReply


class CompanionDialogueLocalLLMMixin:
    """
    Optional local LLM integration for richer dialogue replies.
    """

    def _try_build_local_llm(self) -> Any | None:
        if importlib.util.find_spec("modules.understanding.dialogue.llm.local_llm") is None:
            return None

        try:
            module = __import__(
                "modules.understanding.dialogue.llm.local_llm",
                fromlist=["LocalLLMService"],
            )
            service_class = getattr(module, "LocalLLMService", None)
            if service_class is None:
                return None

            instance = service_class(self.settings)
            append_log("Local LLM service detected and initialized for dialogue layer.")
            return instance
        except Exception as error:
            append_log(f"Local LLM service initialization skipped: {error}")
            return None

    def _try_local_llm(
        self,
        *,
        normalized_text: str,
        language: str,
        topics: list[str],
        user_profile: dict | None,
        route_kind: str,
    ) -> DialogueReply | None:
        if self.local_llm is None:
            return None

        is_available = getattr(self.local_llm, "is_available", None)
        if callable(is_available):
            try:
                if not is_available():
                    return None
            except Exception:
                return None

        generate_reply = getattr(self.local_llm, "generate_companion_reply", None)
        if not callable(generate_reply):
            return None

        context = {
            "topics": topics,
            "route_kind": route_kind,
            "recent_context": self.conversation_memory.summary_for_prompt(
                limit=6,
                preferred_language=language,
            ),
            "user_profile": dict(user_profile or {}),
        }

        try:
            reply = generate_reply(
                normalized_text,
                language,
                context=context,
            )
        except TypeError:
            try:
                reply = generate_reply(normalized_text, language)
            except Exception:
                return None
        except Exception:
            return None

        if not reply:
            return None

        text = str(
            getattr(reply, "text", "") or getattr(reply, "spoken_text", "") or ""
        ).strip()
        if not text:
            return None

        return self._reply(
            language,
            text,
            display_title=self._text(language, "ODPOWIEDŹ", "REPLY"),
            source="local_llm",
        )


__all__ = ["CompanionDialogueLocalLLMMixin"]