from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IntentSuggestion:
    """
    One clarification suggestion produced by the parser when the utterance
    looks close to a known action but is not certain enough.
    """

    action: str
    label: str | None = None
    confidence: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "action": str(self.action),
            "confidence": float(self.confidence),
        }
        if self.label:
            data["label"] = str(self.label)
        if self.payload:
            data["payload"] = dict(self.payload)
        return data


@dataclass(slots=True)
class IntentResult:
    """
    Final result returned by the rule-based parser.

    This is intentionally compatible with the old project shape so migration
    stays smooth:
    - action
    - data
    - confidence
    - needs_confirmation
    - suggestions
    - normalized_text
    """

    action: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    needs_confirmation: bool = False
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    normalized_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "data": dict(self.data),
            "confidence": float(self.confidence),
            "needs_confirmation": bool(self.needs_confirmation),
            "suggestions": [dict(item) for item in self.suggestions],
            "normalized_text": self.normalized_text,
        }

    @classmethod
    def unknown(cls, normalized_text: str = "") -> "IntentResult":
        return cls(
            action="unknown",
            data={},
            confidence=0.0,
            needs_confirmation=False,
            suggestions=[],
            normalized_text=str(normalized_text or "").strip(),
        )

    @classmethod
    def confirmation(
        cls,
        *,
        action: str,
        normalized_text: str = "",
        confidence: float = 1.0,
    ) -> "IntentResult":
        return cls(
            action=action,
            data={},
            confidence=float(confidence),
            needs_confirmation=False,
            suggestions=[],
            normalized_text=str(normalized_text or "").strip(),
        )

    @classmethod
    def from_action(
        cls,
        *,
        action: str,
        data: dict[str, Any] | None = None,
        confidence: float = 1.0,
        needs_confirmation: bool = False,
        suggestions: list[dict[str, Any]] | None = None,
        normalized_text: str = "",
    ) -> "IntentResult":
        return cls(
            action=str(action),
            data=dict(data or {}),
            confidence=float(confidence),
            needs_confirmation=bool(needs_confirmation),
            suggestions=[dict(item) for item in (suggestions or [])],
            normalized_text=str(normalized_text or "").strip(),
        )

    @classmethod
    def unclear(
        cls,
        *,
        suggestions: list["IntentSuggestion | dict[str, Any]"] | None = None,
        normalized_text: str = "",
        confidence: float = 0.35,
    ) -> "IntentResult":
        rendered_suggestions: list[dict[str, Any]] = []

        for item in suggestions or []:
            if isinstance(item, IntentSuggestion):
                rendered_suggestions.append(item.to_dict())
            elif isinstance(item, dict):
                rendered_suggestions.append(dict(item))

        return cls(
            action="unclear",
            data={},
            confidence=float(confidence),
            needs_confirmation=bool(rendered_suggestions),
            suggestions=rendered_suggestions,
            normalized_text=str(normalized_text or "").strip(),
        )


__all__ = [
    "IntentResult",
    "IntentSuggestion",
]