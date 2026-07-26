"""Unit tests for Quick Calc CLI AST evaluator."""

import unittest

from main import SafeMathEvaluator


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


if __name__ == "__main__":
    unittest.main()
