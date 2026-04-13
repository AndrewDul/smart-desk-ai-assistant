from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import ChunkKind


@dataclass(slots=True)
class LocalLLMReply:
    ok: bool
    text: str = ""
    language: str = "en"
    source: str = "disabled"
    error: str = ""
    raw_output: str = ""
    streamed: bool = False
    first_chunk_latency_ms: float = 0.0
    chunks: list["LocalLLMChunk"] = field(default_factory=list)


@dataclass(slots=True)
class LocalLLMChunk:
    text: str = ""
    language: str = "en"
    source: str = "disabled"
    sequence: int = 0
    finished: bool = False
    flush: bool = True
    speak_now: bool = True
    kind: ChunkKind = ChunkKind.CONTENT
    metadata: dict[str, Any] = field(default_factory=dict)
    first_chunk_latency_ms: float = 0.0


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


@dataclass(slots=True)
class LocalLLMBackendPolicy:
    require_persistent_backend: bool = True
    allow_cli_fallback: bool = False
    stream_responses: bool = True
    startup_warmup: bool = True
    startup_warmup_timeout_seconds: float = 8.0


__all__ = [
    "LocalLLMBackendPolicy",
    "LocalLLMChunk",
    "LocalLLMContext",
    "LocalLLMProfile",
    "LocalLLMReply",
]