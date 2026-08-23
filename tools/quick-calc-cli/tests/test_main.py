"""Unit tests for Quick Calc CLI AST evaluator."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List
from unittest.mock import patch

import main as main_module
from main import SafeMathEvaluator, build_parser, interactive_repl, main


class TestSafeMathEvaluator(unittest.TestCase):
    """Test suite for safe AST evaluation."""

    def setUp(self) -> None:
        self.evaluator = SafeMathEvaluator()

    def test_basic_arithmetic(self) -> None:
        self.assertEqual(self.evaluator.evaluate("2 + 3 * 4"), 14.0)
        self.assertEqual(self.evaluator.evaluate("(10 - 2) / 4"), 2.0)
        self.assertEqual(self.evaluator.evaluate("2 ** 3"), 8.0)
        self.assertEqual(self.evaluator.evaluate("-5 + 10"), 5.0)

    def test_math_functions(self) -> None:
        self.assertAlmostEqual(self.evaluator.evaluate("sin(pi / 2)"), 1.0)
        self.assertAlmostEqual(self.evaluator.evaluate("cos(0)"), 1.0)
        self.assertEqual(self.evaluator.evaluate("sqrt(16)"), 4.0)
        self.assertAlmostEqual(self.evaluator.evaluate("log10(100)"), 2.0)

    def test_variable_assignment(self) -> None:
        self.assertEqual(self.evaluator.evaluate("x = 5 + 3"), 8.0)
        self.assertEqual(self.evaluator.evaluate("x * 2"), 16.0)
        self.assertEqual(self.evaluator.evaluate("ans"), 16.0)

    def test_unauthorized_code_prevention(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("__import__('os').system('dir')")
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("eval('1+1')")

    def test_division_by_zero(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("10 / 0")

    def test_history_logging(self) -> None:
        self.evaluator.evaluate("5 * 5")
        self.assertGreater(len(self.evaluator.history), 0)
        self.assertEqual(self.evaluator.history[-1]["result"], 25.0)


class TestEvaluatorEdgeCases(unittest.TestCase):
    """Test suite for AST rejection rules and operator coverage."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Redirect history persistence into a scratch directory.
        patcher = patch.object(
            main_module, "HISTORY_FILE", str(Path(self.tmp.name) / "h.json")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.evaluator = SafeMathEvaluator()

    def test_empty_expression_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("   ")

    def test_invalid_assignment_names_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("1x = 4")
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("sin = 4")

    def test_syntax_error_becomes_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("2 +* 3")

    def test_string_constant_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate('"abc"')

    def test_undefined_variable_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("mystery_var + 1")

    def test_logical_unary_operator_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("not 1")

    def test_unary_plus_supported(self) -> None:
        self.assertEqual(self.evaluator.evaluate("+7"), 7.0)

    def test_floor_division_and_modulo(self) -> None:
        self.assertEqual(self.evaluator.evaluate("7 // 2"), 3.0)
        self.assertEqual(self.evaluator.evaluate("7 % 3"), 1.0)
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("7 // 0")

    def test_bitwise_operator_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("2 | 3")

    def test_attribute_call_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("math.sqrt(4)")

    def test_unknown_function_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.evaluator.evaluate("exec('1')")

    def test_extra_math_functions_and_constants(self) -> None:
        self.assertAlmostEqual(self.evaluator.evaluate("abs(-3) + tau/tau"), 4.0)
        self.assertEqual(self.evaluator.evaluate("floor(2.9)"), 2.0)
        self.assertEqual(self.evaluator.evaluate("ceil(2.1)"), 3.0)
        self.assertAlmostEqual(self.evaluator.evaluate("deg(pi)"), 180.0)
        self.assertAlmostEqual(self.evaluator.evaluate("rad(180)"), 3.141592653589793)
        self.assertAlmostEqual(self.evaluator.evaluate("e * 0 + 1"), 1.0)

    def test_history_survives_restart_via_file(self) -> None:
        self.evaluator.evaluate("21 * 2")
        fresh = SafeMathEvaluator()
        loaded: List[Dict[str, Any]] = fresh.get_history()
        self.assertTrue(any(entry["expression"] == "21 * 2" for entry in loaded))

    def test_corrupt_history_file_is_ignored(self) -> None:
        hist_path = Path(main_module.HISTORY_FILE)
        hist_path.write_text("{corrupt", encoding="utf-8")
        evaluator = SafeMathEvaluator()
        self.assertEqual(evaluator.get_history(), [])

    def test_save_failure_does_not_break_evaluation(self) -> None:
        # Point history at a directory so open() fails on save.
        with patch.object(main_module, "HISTORY_FILE", str(Path(self.tmp.name))):
            evaluator = SafeMathEvaluator()
            self.assertEqual(evaluator.evaluate("2 + 3"), 5.0)


class TestInteractiveRepl(unittest.TestCase):
    """Test suite for the REPL loop (input fully mocked)."""

    def _run_repl(self, inputs: List[str]) -> str:
        buf = io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(buf):
            interactive_repl(SafeMathEvaluator())
        return buf.getvalue()

    def test_repl_evaluates_history_command_and_exit(self) -> None:
        out = self._run_repl(["6 * 7", "history", "", "exit"])
        self.assertIn("= 42.0", out)
        self.assertIn("6 * 7 = 42.0", out)

    def test_repl_reports_errors_and_continues(self) -> None:
        out = self._run_repl(["1 / 0", "quit"])
        self.assertIn("Error:", out)

    def test_repl_exits_on_eof(self) -> None:
        buf = io.StringIO()
        with patch("builtins.input", side_effect=EOFError), redirect_stdout(buf):
            interactive_repl(SafeMathEvaluator())
        self.assertIn("Exiting calculator.", buf.getvalue())


class TestQuickCalcCli(unittest.TestCase):
    """End-to-end tests for build_parser and main()."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(
            main_module, "HISTORY_FILE", str(Path(self.tmp.name) / "hist.json")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_build_parser_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--history"])
        self.assertTrue(args.history)
        self.assertIsNone(args.expression)
        args2 = parser.parse_args(["1 + 1", "--interactive"])
        self.assertEqual(args2.expression, "1 + 1")
        self.assertTrue(args2.interactive)

    def test_main_history_flag_prints_entries(self) -> None:
        SafeMathEvaluator().evaluate("40 + 2")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--history"])
        self.assertEqual(rc, 0)
        self.assertIn("Calculation History:", buf.getvalue())
        self.assertIn("40 + 2 = 42.0", buf.getvalue())

    def test_main_expression_prints_result(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["3 * 9"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "27.0")

    def test_main_bad_expression_returns_one(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["1 / zero"])
        self.assertEqual(rc, 1)
        self.assertIn("Error:", err.getvalue())

    def test_main_interactive_flag_starts_repl(self) -> None:
        with patch("builtins.input", side_effect=["exit"]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--interactive"])
        self.assertEqual(rc, 0)
        self.assertIn("Quick Calc CLI REPL", buf.getvalue())

    def test_main_without_args_starts_repl(self) -> None:
        with patch("builtins.input", side_effect=EOFError):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main([])
        self.assertEqual(rc, 0)
        self.assertIn("Exiting calculator.", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
