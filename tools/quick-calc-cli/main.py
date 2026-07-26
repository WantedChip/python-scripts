"""Safe AST-based Math Calculator CLI with variable storage and history.

Evaluates mathematical expressions using Python's AST module for secure
computation, supporting math functions, constants, variable assignments, and
history logging.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=too-many-return-statements


HISTORY_FILE = "calc_history.json"


class SafeMathEvaluator:
    """AST-based evaluator for safe mathematical expressions."""

    def __init__(self) -> None:
        """Initialize evaluator with default constants and functions."""
        self.variables: Dict[str, float] = {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "ans": 0.0,
        }
        self.functions: Dict[str, Callable[..., Any]] = {
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "sqrt": math.sqrt,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "abs": abs,
            "floor": math.floor,
            "ceil": math.ceil,
            "round": round,
            "rad": math.radians,
            "deg": math.degrees,
        }
        self.history: List[Dict[str, Any]] = []
        self._load_history()

    def _load_history(self) -> None:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.history = data
            except (json.JSONDecodeError, OSError):
                self.history = []

    def _save_history(self) -> None:
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-100:], f, indent=2)
        except OSError:
            pass

    def evaluate(self, expr_str: str) -> float:
        """Evaluate expression string safely.

        Args:
            expr_str: Math expression string, e.g. "2 * sin(pi / 4) + x"

        Returns:
            Computed numerical result.

        Raises:
            ValueError: On invalid syntax or undefined variables.
        """
        expr_str = expr_str.strip()
        if not expr_str:
            raise ValueError("Expression is empty.")

        # Check if this is a variable assignment e.g. "x = 5 + 3"
        if "=" in expr_str and not expr_str.startswith("="):
            parts = expr_str.split("=", 1)
            var_name = parts[0].strip()
            if not var_name.isidentifier() or var_name in self.functions:
                raise ValueError(f"Invalid variable name: '{var_name}'")
            val = self.evaluate(parts[1].strip())
            self.variables[var_name] = val
            self.variables["ans"] = val
            self.history.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "expression": expr_str,
                    "result": val,
                }
            )
            self._save_history()
            return val

        try:
            parsed_ast = ast.parse(expr_str, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Syntax error in expression: {e}") from e

        result = self._eval_node(parsed_ast.body)
        self.variables["ans"] = result
        self.history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "expression": expr_str,
                "result": result,
            }
        )
        self._save_history()
        return result

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant):  # Python 3.8+
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported constant type: {type(node.value)}")

        if isinstance(node, ast.Name):
            if node.id in self.variables:
                return float(self.variables[node.id])
            raise ValueError(f"Undefined variable: '{node.id}'")

        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")

        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("Division by zero.")
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    raise ValueError("Division by zero.")
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                res_pow = float(left**right)
                return res_pow
            raise ValueError(f"Unsupported binary operator: {type(node.op)}")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Complex function calls not supported.")
            func_name = node.func.id
            if func_name not in self.functions:
                err_msg = f"Unknown or unauthorized function: '{func_name}'"
                raise ValueError(err_msg)
            args = [self._eval_node(arg) for arg in node.args]
            func_val = self.functions[func_name](*args)
            return float(func_val)

        raise ValueError(f"Unsupported AST node type: {type(node)}")

    def get_history(self) -> List[Dict[str, Any]]:
        """Return calculation history."""
        return self.history


def interactive_repl(evaluator: SafeMathEvaluator) -> None:
    """Run interactive calculation session."""
    print("Quick Calc CLI REPL. Type 'exit', 'quit', or 'history'.")
    while True:
        try:
            user_input = input("calc> ").strip()  # nosec B322
            if user_input.lower() in ("exit", "quit"):
                break
            if user_input.lower() == "history":
                for entry in evaluator.history[-10:]:
                    print(f"  {entry['expression']} = {entry['result']}")
                continue
            if not user_input:
                continue

            result = evaluator.evaluate(user_input)
            print(f"= {result}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting calculator.")
            break
        except ValueError as err:
            print(f"Error: {err}")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Quick Calc AST Math Calculator"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("expression", nargs="?", help="Math expression to evaluate")
    parser.add_argument(
        "--history", action="store_true", help="Display calculation history"
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Start REPL interactive mode"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Quick Calc CLI."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    evaluator = SafeMathEvaluator()

    if parsed.history:
        print("Calculation History:")
        for h in evaluator.history[-20:]:
            print(f"[{h['timestamp']}] {h['expression']} = {h['result']}")
    elif parsed.interactive or parsed.expression == "interactive":
        interactive_repl(evaluator)
    elif parsed.expression:
        try:
            res = evaluator.evaluate(parsed.expression)
            print(res)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        interactive_repl(evaluator)

    return 0


if __name__ == "__main__":
    sys.exit(main())
