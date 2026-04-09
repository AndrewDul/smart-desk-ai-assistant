from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LocalLLMReply:
    ok: bool
    text: str = ""
    language: str = "en"
    source: str = "disabled"
    error: str = ""
    raw_output: str = ""


@dataclass(slots=True)
class LocalLLMContext:
    user_name: str = ""
    assistant_name: str = "NeXa"
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    user_text: str = ""
    route_kind: str = "conversation"
    recent_context: str = ""
    user_profile: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LocalLLMProfile:
    prompt_chars: int
    n_predict: int
    timeout_seconds: float
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float
    max_sentences: int
    style_hint: str