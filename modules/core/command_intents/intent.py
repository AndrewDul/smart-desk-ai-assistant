from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from modules.devices.audio.command_asr.command_language import CommandLanguage


class CommandIntentDomain(str, Enum):
    """High-level command intent domain."""

    VISUAL_SHELL = "visual_shell"
    SYSTEM = "system"
    ASSISTANT = "assistant"
    FOCUS = "focus"
    BREAK = "break"


@dataclass(frozen=True, slots=True)
class CommandIntentDefinition:
    """Static definition that maps an intent key to an executable action."""

    key: str
    domain: CommandIntentDomain
    action: str
    default_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("key must not be empty")
        if not self.action.strip():
            raise ValueError("action must not be empty")

        object.__setattr__(
            self,
            "default_parameters",
            MappingProxyType(dict(self.default_parameters)),
        )


@dataclass(frozen=True, slots=True)
class CommandIntent:
    """Resolved deterministic command intent."""

    key: str
    domain: CommandIntentDomain
    action: str
    language: CommandLanguage
    source_text: str
    normalized_source_text: str
    confidence: float
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("key must not be empty")
        if not self.action.strip():
            raise ValueError("action must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(self.parameters)),
        )

    @classmethod
    def from_definition(
        cls,
        *,
        definition: CommandIntentDefinition,
        language: CommandLanguage,
        source_text: str,
        normalized_source_text: str,
        confidence: float,
        parameters: Mapping[str, Any] | None = None,
    ) -> CommandIntent:
        merged_parameters: dict[str, Any] = dict(definition.default_parameters)
        if parameters:
            merged_parameters.update(parameters)

        return cls(
            key=definition.key,
            domain=definition.domain,
            action=definition.action,
            language=language,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            confidence=confidence,
            parameters=merged_parameters,
        )