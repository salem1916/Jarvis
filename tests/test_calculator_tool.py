import pytest

from jarvis.tools.calculator import CalculatorTool


def test_calculator_addition() -> None:
    """
    Basic arithmetic should be exact.
    """

    tool = CalculatorTool()

    result = tool.execute(
        {
            "expression": "40 + 4",
        }
    )

    assert result == 44


def test_calculator_complex_expression() -> None:
    """
    Parentheses and several operations should work.
    """

    tool = CalculatorTool()

    result = tool.execute(
        {
            "expression": "(10 + 5) * 3 - 5",
        }
    )

    assert result == 40


def test_calculator_division() -> None:
    """
    Floating-point results are supported.
    """

    tool = CalculatorTool()

    result = tool.execute(
        {
            "expression": "5 / 2",
        }
    )

    assert result == 2.5


def test_calculator_rejects_division_by_zero() -> None:
    """
    Invalid arithmetic must fail cleanly.
    """

    tool = CalculatorTool()

    with pytest.raises(
        ValueError,
        match="Division by zero",
    ):
        tool.execute(
            {
                "expression": "10 / 0",
            }
        )


def test_calculator_rejects_python_code() -> None:
    """
    Security test.

    CalculatorTool must never behave like eval().

    Function calls and arbitrary Python code are rejected.
    """

    tool = CalculatorTool()

    with pytest.raises(
        ValueError,
        match="unsupported content",
    ):
        tool.execute(
            {
                "expression": (
                    "__import__('os').system('echo hacked')"
                ),
            }
        )


def test_calculator_requires_string_expression() -> None:
    """
    Tool arguments must have the correct type.
    """

    tool = CalculatorTool()

    with pytest.raises(
        TypeError,
        match="'expression' must be a string",
    ):
        tool.execute(
            {
                "expression": 44,
            }
        )