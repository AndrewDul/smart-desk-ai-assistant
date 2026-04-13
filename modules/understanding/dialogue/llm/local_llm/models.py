from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    healthcheck_timeout_seconds: float = 3.0
    auto_recovery_enabled: bool = True
    auto_recovery_cooldown_seconds: float = 20.0
    max_auto_recovery_attempts: int = 3


@dataclass(slots=True)
class LocalLLMHealthSnapshot:
    enabled: bool
    runner: str
    state: str
    available: bool
    healthy: bool
    warmup_required: bool
    warmup_ready: bool
    startup_warmup_enabled: bool
    last_error: str = ""
    health_reason: str = ""
    last_check_age_seconds: float | None = None
    last_success_age_seconds: float | None = None
    consecutive_failures: int = 0
    recovery_allowed: bool = False
    recovery_cooldown_seconds: float = 0.0
    max_auto_recovery_attempts: int = 0
    recovery_attempts_since_success: int = 0
    last_recovery_age_seconds: float | None = None
    last_recovery_ok: bool = False
    last_recovery_error: str = ""
    last_warmup_ok: bool = False
    last_warmup_error: str = ""
    last_generation_ok: bool = False
    last_generation_latency_ms: float = 0.0
    last_first_chunk_latency_ms: float = 0.0
    last_generation_source: str = ""
    server_url: str = ""
    server_model_name: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "LocalLLMBackendPolicy",
    "LocalLLMChunk",
    "LocalLLMContext",
    "LocalLLMHealthSnapshot",
    "LocalLLMProfile",
    "LocalLLMReply",
]