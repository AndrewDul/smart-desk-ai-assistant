"""
Deterministic arithmetic handler for the NeXa fast command lane.

This sits next to FastCommandLane rather than inside the action_flow
executor framework because it delivers a spoken reply directly via
the assistant's text response path and does not need intent, tool, or
executor wiring. Keeping it self-contained keeps the fast lane genuinely
fast.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any


_PL_WORD_OPS = {
    "plus": "+",
    "dodac": "+",
    "dodać": "+",
    "minus": "-",
    "odjac": "-",
    "odjąć": "-",
    "razy": "*",
    "pomnozyc": "*",
    "pomnożyć": "*",
    "podzielic": "/",
    "podzielić": "/",
    "przez": "/",
}

_EN_WORD_OPS = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "over": "/",
}

_SYMBOL_OPS = {
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "x": "*",
    "X": "*",
    "×": "*",
    "·": "*",
    "÷": "/",
    ":": "/",
}

# Compound word operators that consist of two tokens with "by"/"przez".
# We normalize them to a single symbol before the regex scan so the
# detection and extraction regexes stay simple and fast.
_COMPOUND_OPS_RE = re.compile(
    r"\b("
    r"divided\s+by"
    r"|multiplied\s+by"
    r"|podzielone\s+przez"
    r"|pomnożone\s+przez"
    r"|pomnozone\s+przez"
    r")\b",
    flags=re.IGNORECASE,
)

_COMPOUND_OPS_MAP = {
    "divided by": " / ",
    "multiplied by": " * ",
    "podzielone przez": " / ",
    "pomnożone przez": " * ",
    "pomnozone przez": " * ",
}

_EXPRESSION_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?)"
    r"\s*([+\-*/xX×·÷:]|plus|minus|razy|dodac|dodać|odjac|odjąć|"
    r"pomnozyc|pomnożyć|podzielic|podzielić|przez|times|over)\s*"
    r"(-?\d+(?:[.,]\d+)?)",
    flags=re.IGNORECASE,
)

_DETECT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*"
    r"(?:[+\-*/xX×·÷:]|plus|minus|razy|dodac|dodać|odjac|odjąć|"
    r"pomnozyc|pomnożyć|podzielic|podzielić|przez|times|over)"
    r"\s*\d+(?:[.,]\d+)?",
    flags=re.IGNORECASE,
)


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_compound_operators(text: str) -> str:
    """
    Replace multi-word operators with their single-symbol equivalent.

    The substitution leaves a single regular space on either side of the
    symbol; any incidental double spaces created by the substitution are
    collapsed so downstream regexes stay simple.
    """
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        key = " ".join(match.group(0).lower().split())
        return _COMPOUND_OPS_MAP.get(key, match.group(0))

    substituted = _COMPOUND_OPS_RE.sub(_replace, text)
    return _WHITESPACE_RE.sub(" ", substituted).strip()


@dataclass(slots=True)
class _CalcOutcome:
    ok: bool
    expression: str
    result: str
    error: str = ""


def looks_like_arithmetic(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    cleaned = _normalize_compound_operators(cleaned)
    return bool(_DETECT_RE.search(cleaned))


def try_handle_arithmetic(*, assistant: Any, raw_text: str, language: str) -> bool:
    """
    If raw_text contains a simple arithmetic expression, compute it and
    deliver the reply through the assistant's text response path. Returns
    True if handled, False otherwise.
    """
    outcome = _evaluate_expression(raw_text)
    if not outcome.ok:
        return False

    from modules.runtime.contracts import RouteKind

    lang = str(language or "en").strip().lower() or "en"
    # Display uses unicode math symbols; speech uses words Piper can pronounce.
    display_expr = outcome.expression.replace("*", "×").replace("/", ":")

    if lang.startswith("pl"):
        spoken_op = (
            outcome.expression
            .replace("+", " plus ")
            .replace("-", " minus ")
            .replace("*", " razy ")
            .replace("/", " podzielić przez ")
        )
        spoken = f"{spoken_op} to {outcome.result}."
        display_title = "KALKULATOR"
    else:
        spoken_op = (
            outcome.expression
            .replace("+", " plus ")
            .replace("-", " minus ")
            .replace("*", " times ")
            .replace("/", " divided by ")
        )
        spoken = f"{spoken_op} is {outcome.result}."
        display_title = "CALCULATOR"

    metadata = {
        "source": "fast_command_lane.calculate",
        "expression": outcome.expression,
        "result": outcome.result,
        "language": lang,
        "response_kind": "calculation",
        "display_title": display_title,
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


def _evaluate_expression(text: str) -> _CalcOutcome:
    cleaned = str(text or "").strip()
    if not cleaned:
        return _CalcOutcome(ok=False, expression="", result="", error="empty")

    cleaned = _normalize_compound_operators(cleaned)
    match = _EXPRESSION_RE.search(cleaned)
    if not match:
        return _CalcOutcome(ok=False, expression="", result="", error="no pattern")

    left_raw = match.group(1)
    op_raw = match.group(2)
    right_raw = match.group(3)

    try:
        left = Decimal(left_raw.replace(",", "."))
        right = Decimal(right_raw.replace(",", "."))
    except InvalidOperation:
        return _CalcOutcome(ok=False, expression="", result="", error="parse")

    op_key = op_raw.strip().lower()
    op = _SYMBOL_OPS.get(op_key)
    if op is None:
        op = _PL_WORD_OPS.get(op_key)
    if op is None:
        op = _EN_WORD_OPS.get(op_key)
    if not op:
        return _CalcOutcome(ok=False, expression="", result="", error=f"op:{op_key}")

    try:
        if op == "+":
            value = left + right
        elif op == "-":
            value = left - right
        elif op == "*":
            value = left * right
        elif op == "/":
            value = left / right
        else:
            return _CalcOutcome(ok=False, expression="", result="", error="bad_op")
    except DivisionByZero:
        return _CalcOutcome(ok=False, expression="", result="", error="div_zero")
    except (InvalidOperation, ArithmeticError) as error:
        return _CalcOutcome(ok=False, expression="", result="", error=str(error))

    expression = f"{_format_decimal(left)} {op} {_format_decimal(right)}"
    return _CalcOutcome(ok=True, expression=expression, result=_format_decimal(value))


def _format_decimal(value: Decimal) -> str:
    try:
        normalized = value.normalize()
    except InvalidOperation:
        return str(value)

    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


__all__ = [
    "looks_like_arithmetic",
    "try_handle_arithmetic",
]