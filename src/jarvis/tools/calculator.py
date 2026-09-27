import ast
import operator
from collections.abc import Callable, Mapping
from typing import ClassVar

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class CalculatorTool(Tool):
    """
    Safe deterministic arithmetic calculator.

    JARVIS should use this tool for exact arithmetic
    instead of trusting the language model to calculate
    numbers itself.

    SECURITY:

    Python eval() is deliberately NOT used.

    The expression is parsed using Python's AST module
    and only specifically approved arithmetic operations
    are allowed.
    """

    name = "calculator"

    description = (
        "Perform exact arithmetic calculations. "
        "Use this tool for mathematical expressions instead "
        "of calculating them yourself. Supports addition, "
        "subtraction, multiplication, division, floor division, "
        "modulo, powers, parentheses, and unary plus/minus."
    )

    required_capability = Capability.CALCULATE

    parameters_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "Arithmetic expression to calculate. "
                    "Examples: '40 + 4', '937 * 428', "
                    "or '(15 * 3) / 5'."
                ),
            },
        },
        "required": [
            "expression",
        ],
        "additionalProperties": False,
    }

    # -------------------------------------------------
    # Allowed binary operators
    #
    # Anything not listed here is rejected.
    # -------------------------------------------------

    _binary_operators: ClassVar[
        dict[
            type[ast.operator],
            Callable[[float, float], float],
        ]
    ] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    # -------------------------------------------------
    # Allowed unary operators
    #
    # Examples:
    #
    # -5
    # +10
    # -------------------------------------------------

    _unary_operators: ClassVar[
        dict[
            type[ast.unaryop],
            Callable[[float], float],
        ]
    ] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        """
        Calculate one arithmetic expression safely.
        """

        expression = arguments.get(
            "expression"
        )

        if not isinstance(
            expression,
            str,
        ):
            raise TypeError(
                "'expression' must be a string."
            )

        if not expression.strip():
            raise ValueError(
                "Expression cannot be empty."
            )

        # Parse the expression without executing it.
        try:
            parsed = ast.parse(
                expression,
                mode="eval",
            )

        except SyntaxError as exc:
            raise ValueError(
                "Invalid mathematical expression."
            ) from exc

        result = self._evaluate(
            parsed.body
        )

        # Make clean integer results look like:
        #
        # 44
        #
        # rather than:
        #
        # 44.0
        if isinstance(
            result,
            float,
        ) and result.is_integer():
            return int(result)

        return result

    def _evaluate(
        self,
        node: ast.AST,
    ) -> float:
        """
        Recursively evaluate only approved AST nodes.

        Anything outside our arithmetic whitelist
        is rejected.
        """

        # -------------------------------------------------
        # Numbers
        # -------------------------------------------------

        if isinstance(
            node,
            ast.Constant,
        ):
            value = node.value

            # Python treats bool as a subclass of int.
            #
            # We explicitly reject it because this tool
            # should accept mathematical numbers only.
            if isinstance(
                value,
                bool,
            ):
                raise TypeError(
                    "Only numbers are allowed."
                )

            if isinstance(
                value,
                (int, float),
            ):
                return float(value)

            raise TypeError(
                "Only numbers are allowed."
            )

        # -------------------------------------------------
        # Binary arithmetic
        #
        # Examples:
        #
        # 2 + 3
        # 10 / 2
        # 4 ** 2
        # -------------------------------------------------

        if isinstance(
            node,
            ast.BinOp,
        ):
            operator_type = type(
                node.op
            )

            operation = self._binary_operators.get(
                operator_type
            )

            if operation is None:
                raise ValueError(
                    "Unsupported mathematical operator."
                )

            left = self._evaluate(
                node.left
            )

            right = self._evaluate(
                node.right
            )

            try:
                return operation(
                    left,
                    right,
                )

            except ZeroDivisionError as exc:
                raise ValueError(
                    "Division by zero is not allowed."
                ) from exc

        # -------------------------------------------------
        # Unary arithmetic
        #
        # Examples:
        #
        # -5
        # +10
        # -------------------------------------------------

        if isinstance(
            node,
            ast.UnaryOp,
        ):
            operator_type = type(
                node.op
            )

            operation = self._unary_operators.get(
                operator_type
            )

            if operation is None:
                raise ValueError(
                    "Unsupported unary operator."
                )

            operand = self._evaluate(
                node.operand
            )

            return operation(
                operand
            )

        # -------------------------------------------------
        # Anything else is forbidden.
        #
        # This blocks things such as:
        #
        # function calls
        # variable names
        # imports
        # attribute access
        # lists
        # dictionaries
        # arbitrary Python code
        # -------------------------------------------------

        raise ValueError(
            "Expression contains unsupported content."
        )