from modules.core.calculator.simple_arithmetic import (
    evaluate_arithmetic_expression,
    format_spoken_expression,
    looks_like_arithmetic,
)


def test_evaluates_polish_square_root_command() -> None:
    outcome = evaluate_arithmetic_expression("ile to jest pierwiastek z dziewięć")

    assert outcome.ok
    assert outcome.expression == "√9"
    assert outcome.result == "3"


def test_evaluates_english_square_root_command() -> None:
    outcome = evaluate_arithmetic_expression("calculate square root of sixteen")

    assert outcome.ok
    assert outcome.expression == "√16"
    assert outcome.result == "4"


def test_evaluates_binary_operation_between_roots() -> None:
    outcome = evaluate_arithmetic_expression(
        "pierwiastek z dziewięć plus pierwiastek z szesnaście"
    )

    assert outcome.ok
    assert outcome.expression == "√9 + √16"
    assert outcome.result == "7"


def test_evaluates_root_and_number_operation() -> None:
    outcome = evaluate_arithmetic_expression("square root of nine times two")

    assert outcome.ok
    assert outcome.expression == "√9 * 2"
    assert outcome.result == "6"


def test_square_root_phrases_are_detected_as_arithmetic() -> None:
    assert looks_like_arithmetic("pierwiastek z dziewięć")
    assert looks_like_arithmetic("square root of nine plus two")


def test_spoken_expression_expands_square_root_symbol() -> None:
    assert (
        format_spoken_expression("√9 + √16", language="pl")
        == "pierwiastek z 9 plus pierwiastek z 16"
    )
    assert (
        format_spoken_expression("√9 + √16", language="en")
        == "square root of 9 plus square root of 16"
    )
