from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import ChunkKind


@dataclass(slots=True)
class ActionResponseSpec:
    action: str
    spoken_text: str
    display_title: str
    display_lines: list[str]
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    chunk_kind: ChunkKind = ChunkKind.CONTENT


@dataclass(slots=True)
class ActionFollowUpPromptSpec:
    action: str
    spoken_text: str
    source: str
    follow_up_type: str
    extra_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["ActionResponseSpec", "ActionFollowUpPromptSpec"]