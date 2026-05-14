"""Deterministic arithmetic handler for the NeXa fast command lane."""
from __future__ import annotations

from typing import Any

from modules.core.calculator.simple_arithmetic import (
    evaluate_arithmetic_expression,
    format_spoken_expression,
    looks_like_arithmetic,
)


def try_handle_arithmetic(*, assistant: Any, raw_text: str, language: str) -> bool:
    """Compute a simple arithmetic expression and deliver a fast local reply."""

    outcome = evaluate_arithmetic_expression(raw_text)
    if not outcome.ok:
        return False

    from modules.runtime.contracts import RouteKind

    lang = str(language or "en").strip().lower() or "en"
    display_expr = outcome.expression.replace("*", "×").replace("/", ":")

    if lang.startswith("pl"):
        spoken_op = format_spoken_expression(outcome.expression, language="pl")
        spoken = f"{spoken_op} to {outcome.result}."
        display_title = "KALKULATOR"
    else:
        spoken_op = format_spoken_expression(outcome.expression, language="en")
        spoken = f"{spoken_op} is {outcome.result}."
        display_title = "CALCULATOR"

    metadata = {
        "source": "fast_command_lane.calculate",
        "expression": outcome.expression,
        "display_expression": display_expr,
        "result": outcome.result,
        "language": lang,
        "response_kind": "calculation",
        "display_title": display_title,
        "llm_prevented": True,
    }

    delivered = assistant.deliver_text_response(
        spoken,
        language=lang,
        route_kind=RouteKind.ACTION,
        source="fast_command_lane.calculate",
        remember=True,
        metadata=metadata,
    )
    return bool(delivered)


__all__ = [
    "looks_like_arithmetic",
    "try_handle_arithmetic",
]
