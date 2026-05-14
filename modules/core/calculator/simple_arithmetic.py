"""Small deterministic arithmetic evaluator for fast-line commands.

The evaluator intentionally supports a compact, safe subset: one binary
operation between two decimal values. It is designed for local command
handling, not for executing arbitrary Python expressions.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation

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

_TOKEN_RE = re.compile(r"-?\d+(?:[.,]\d+)?|[a-ząćęłńóśźż]+|[+\-*/xX×·÷:]", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")

_PL_UNITS = {
    "zero": 0,
    "jeden": 1,
    "jedna": 1,
    "jedno": 1,
    "dwa": 2,
    "dwie": 2,
    "trzy": 3,
    "cztery": 4,
    "piec": 5,
    "pięć": 5,
    "szesc": 6,
    "sześć": 6,
    "siedem": 7,
    "osiem": 8,
    "dziewiec": 9,
    "dziewięć": 9,
    "dziesiec": 10,
    "dziesięć": 10,
    "jedenascie": 11,
    "jedenaście": 11,
    "dwanascie": 12,
    "dwanaście": 12,
    "trzynascie": 13,
    "trzynaście": 13,
    "czternascie": 14,
    "czternaście": 14,
    "pietnascie": 15,
    "piętnaście": 15,
    "szesnascie": 16,
    "szesnaście": 16,
    "siedemnascie": 17,
    "siedemnaście": 17,
    "osiemnascie": 18,
    "osiemnaście": 18,
    "dziewietnascie": 19,
    "dziewiętnaście": 19,
}

_PL_TENS = {
    "dwadziescia": 20,
    "dwadzieścia": 20,
    "trzydziesci": 30,
    "trzydzieści": 30,
    "czterdziesci": 40,
    "czterdzieści": 40,
    "piecdziesiat": 50,
    "pięćdziesiąt": 50,
    "szescdziesiat": 60,
    "sześćdziesiąt": 60,
    "siedemdziesiat": 70,
    "siedemdziesiąt": 70,
    "osiemdziesiat": 80,
    "osiemdziesiąt": 80,
    "dziewiecdziesiat": 90,
    "dziewięćdziesiąt": 90,
}

_EN_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_EN_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_NUMBER_WORDS = set(_PL_UNITS) | set(_PL_TENS) | set(_EN_UNITS) | set(_EN_TENS) | {"hundred", "sto"}
_OPERATOR_WORDS = set(_PL_WORD_OPS) | set(_EN_WORD_OPS)


@dataclass(frozen=True, slots=True)
class CalculationOutcome:
    ok: bool
    expression: str
    result: str
    error: str = ""


def looks_like_arithmetic(text: str) -> bool:
    cleaned = _normalize_compound_operators(str(text or "").strip())
    if not cleaned:
        return False
    return bool(_DETECT_RE.search(cleaned) or _extract_word_expression(cleaned) is not None)


def evaluate_arithmetic_expression(text: str) -> CalculationOutcome:
    cleaned = _normalize_compound_operators(str(text or "").strip())
    if not cleaned:
        return CalculationOutcome(ok=False, expression="", result="", error="empty")

    direct = _evaluate_digit_expression(cleaned)
    if direct.ok:
        return direct

    word_expression = _extract_word_expression(cleaned)
    if word_expression is None:
        return CalculationOutcome(ok=False, expression="", result="", error="no_pattern")

    left, op, right = word_expression
    return _calculate(left=left, op=op, right=right)


def _evaluate_digit_expression(cleaned: str) -> CalculationOutcome:
    match = _EXPRESSION_RE.search(cleaned)
    if not match:
        return CalculationOutcome(ok=False, expression="", result="", error="no_pattern")

    try:
        left = Decimal(match.group(1).replace(",", "."))
        right = Decimal(match.group(3).replace(",", "."))
    except InvalidOperation:
        return CalculationOutcome(ok=False, expression="", result="", error="parse")

    op_key = match.group(2).strip().lower()
    op = _SYMBOL_OPS.get(op_key) or _PL_WORD_OPS.get(op_key) or _EN_WORD_OPS.get(op_key)
    if not op:
        return CalculationOutcome(ok=False, expression="", result="", error=f"op:{op_key}")
    return _calculate(left=left, op=op, right=right)


def _calculate(*, left: Decimal, op: str, right: Decimal) -> CalculationOutcome:
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
            return CalculationOutcome(ok=False, expression="", result="", error="bad_op")
    except DivisionByZero:
        return CalculationOutcome(ok=False, expression="", result="", error="div_zero")
    except (InvalidOperation, ArithmeticError) as error:
        return CalculationOutcome(ok=False, expression="", result="", error=str(error))

    expression = f"{_format_decimal(left)} {op} {_format_decimal(right)}"
    return CalculationOutcome(ok=True, expression=expression, result=_format_decimal(value))


def _extract_word_expression(text: str) -> tuple[Decimal, str, Decimal] | None:
    tokens = [_normalize_token(token) for token in _TOKEN_RE.findall(text)]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None

    for index, token in enumerate(tokens):
        op = _SYMBOL_OPS.get(token) or _PL_WORD_OPS.get(token) or _EN_WORD_OPS.get(token)
        if not op:
            continue

        left = _parse_number_suffix(tokens[:index])
        right = _parse_number_prefix(tokens[index + 1 :])
        if left is None or right is None:
            continue
        return Decimal(left), op, Decimal(right)

    return None


def _parse_number_suffix(tokens: list[str]) -> int | None:
    for width in range(min(3, len(tokens)), 0, -1):
        value = _parse_number_tokens(tokens[-width:])
        if value is not None:
            return value
    return None


def _parse_number_prefix(tokens: list[str]) -> int | None:
    for width in range(min(3, len(tokens)), 0, -1):
        value = _parse_number_tokens(tokens[:width])
        if value is not None:
            return value
    return None


def _parse_number_tokens(tokens: list[str]) -> int | None:
    if not tokens:
        return None
    if len(tokens) == 1:
        token = tokens[0]
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        if token in _PL_UNITS:
            return _PL_UNITS[token]
        if token in _PL_TENS:
            return _PL_TENS[token]
        if token in _EN_UNITS:
            return _EN_UNITS[token]
        if token in _EN_TENS:
            return _EN_TENS[token]
        if token == "sto":
            return 100
        if token == "hundred":
            return 100
        return None

    if len(tokens) == 2:
        first, second = tokens
        if first in _PL_TENS and second in _PL_UNITS and _PL_UNITS[second] < 10:
            return _PL_TENS[first] + _PL_UNITS[second]
        if first in _EN_TENS and second in _EN_UNITS and _EN_UNITS[second] < 10:
            return _EN_TENS[first] + _EN_UNITS[second]
        if first in _EN_UNITS and second == "hundred":
            return _EN_UNITS[first] * 100
        if first in _PL_UNITS and second == "sto":
            return _PL_UNITS[first] * 100
        return None

    if len(tokens) == 3:
        first, second, third = tokens
        if first in _EN_UNITS and second == "hundred":
            tail = _parse_number_tokens([third])
            if tail is not None and tail < 100:
                return _EN_UNITS[first] * 100 + tail
        return None

    return None


def _normalize_compound_operators(text: str) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        key = " ".join(match.group(0).lower().split())
        return _COMPOUND_OPS_MAP.get(key, match.group(0))

    substituted = _COMPOUND_OPS_RE.sub(_replace, text)
    return _WHITESPACE_RE.sub(" ", substituted).strip()


def _normalize_token(token: str) -> str:
    cleaned = str(token or "").strip().lower()
    if not cleaned:
        return ""
    if cleaned in _SYMBOL_OPS:
        return cleaned
    decomposed = unicodedata.normalize("NFD", cleaned)
    ascii_token = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    if ascii_token in _NUMBER_WORDS or ascii_token in _OPERATOR_WORDS:
        return ascii_token
    return cleaned


def _format_decimal(value: Decimal) -> str:
    try:
        normalized = value.normalize()
    except InvalidOperation:
        return str(value)

    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
