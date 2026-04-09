from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DialogueReply:
    language: str
    spoken_text: str
    follow_up_text: str = ""
    suggested_actions: list[str] = field(default_factory=list)
    display_title: str = ""
    display_lines: list[str] = field(default_factory=list)
    source: str = "template"


__all__ = ["DialogueReply"]