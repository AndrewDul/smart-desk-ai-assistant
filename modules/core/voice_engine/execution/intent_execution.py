from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from modules.core.command_intents.intent import CommandIntent


class IntentExecutionStatus(str, Enum):
    """Execution result state for resolved Voice Engine v2 intents."""

    EXECUTED = "executed"
    NO_HANDLER = "no_handler"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class IntentExecutionRequest:
    """Request passed to the execution adapter for one resolved intent."""

    intent: CommandIntent
    turn_id: str
    action_first: bool = True
    allow_spoken_acknowledgement: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class IntentExecutionResult:
    """Result returned after executing a resolved intent."""

    status: IntentExecutionStatus
    turn_id: str
    intent_key: str
    action: str
    action_first: bool
    spoken_acknowledgement_allowed: bool
    executed_before_tts: bool
    detail: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if not self.intent_key.strip():
            raise ValueError("intent_key must not be empty")
        if not self.action.strip():
            raise ValueError("action must not be empty")

        object.__setattr__(
            self,
            "payload",
            MappingProxyType(dict(self.payload)),
        )

    @property
    def executed(self) -> bool:
        return self.status is IntentExecutionStatus.EXECUTED

    @classmethod
    def executed_result(
        cls,
        *,
        request: IntentExecutionRequest,
        detail: str = "executed",
        payload: Mapping[str, Any] | None = None,
    ) -> IntentExecutionResult:
        return cls(
            status=IntentExecutionStatus.EXECUTED,
            turn_id=request.turn_id,
            intent_key=request.intent.key,
            action=request.intent.action,
            action_first=request.action_first,
            spoken_acknowledgement_allowed=request.allow_spoken_acknowledgement,
            executed_before_tts=request.action_first,
            detail=detail,
            payload=payload or {},
        )

    @classmethod
    def no_handler(
        cls,
        *,
        request: IntentExecutionRequest,
    ) -> IntentExecutionResult:
        return cls(
            status=IntentExecutionStatus.NO_HANDLER,
            turn_id=request.turn_id,
            intent_key=request.intent.key,
            action=request.intent.action,
            action_first=request.action_first,
            spoken_acknowledgement_allowed=request.allow_spoken_acknowledgement,
            executed_before_tts=False,
            detail="no_handler",
        )

    @classmethod
    def failed(
        cls,
        *,
        request: IntentExecutionRequest,
        detail: str,
    ) -> IntentExecutionResult:
        return cls(
            status=IntentExecutionStatus.FAILED,
            turn_id=request.turn_id,
            intent_key=request.intent.key,
            action=request.intent.action,
            action_first=request.action_first,
            spoken_acknowledgement_allowed=request.allow_spoken_acknowledgement,
            executed_before_tts=False,
            detail=detail,
        )


IntentExecutionHandler = Callable[
    [IntentExecutionRequest],
    Mapping[str, Any] | None,
]


class IntentExecutionAdapter:
    """Registry-based executor for resolved Voice Engine v2 intents."""

    def __init__(self) -> None:
        self._handlers_by_action: dict[str, IntentExecutionHandler] = {}

    @property
    def registered_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers_by_action))

    def register_action(
        self,
        action: str,
        handler: IntentExecutionHandler,
    ) -> None:
        if not action.strip():
            raise ValueError("action must not be empty")

        self._handlers_by_action[action] = handler

    def execute(self, request: IntentExecutionRequest) -> IntentExecutionResult:
        handler = self._handlers_by_action.get(request.intent.action)
        if handler is None:
            return IntentExecutionResult.no_handler(request=request)

        try:
            payload = handler(request)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            return IntentExecutionResult.failed(
                request=request,
                detail=f"{type(exc).__name__}: {exc}",
            )

        return IntentExecutionResult.executed_result(
            request=request,
            payload=payload or {},
        )