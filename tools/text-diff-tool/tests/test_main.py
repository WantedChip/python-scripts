"""Unit tests for Text Diff Tool."""

import unittest

from main import (
    calculate_diff_metrics,
    generate_side_by_side_diff,
    generate_unified_diff,
)


class TestTextDiffTool(unittest.TestCase):
    """Test suite for diff generation and metric calculations."""

    def test_identical_texts(self):
        text = "line 1\nline 2\nline 3"
        metrics = calculate_diff_metrics(text, text)
        self.assertEqual(metrics["additions"], 0)
        self.assertEqual(metrics["deletions"], 0)
        self.assertEqual(metrics["modifications"], 0)
        self.assertEqual(metrics["unchanged"], 3)

    def test_additions_and_deletions(self):
        text1 = "apple\nbanana\ncherry"
        text2 = "apple\ndragonfruit\ncherry\nelderberry"
        metrics = calculate_diff_metrics(text1, text2)
        self.assertGreaterEqual(metrics["additions"], 1)

    def test_unified_diff_output(self):
        t1 = "hello\nworld"
        t2 = "hello\nthere\nworld"
        diff = generate_unified_diff(t1, t2, from_file="a", to_file="b")
        self.assertIn("--- a", diff)
        self.assertIn("+++ b", diff)
        self.assertIn("+there", diff)

    def test_side_by_side_diff_output(self):
        t1 = "line A\nline B"
        t2 = "line A\nline C"
        diff = generate_side_by_side_diff(t1, t2, width=60)
        self.assertIn("ORIGINAL", diff)
        self.assertIn("MODIFIED", diff)
        self.assertIn("line A", diff)

    def test_empty_input(self):
        metrics = calculate_diff_metrics("", "")
        self.assertEqual(metrics["unchanged"], 0)
        self.assertEqual(metrics["additions"], 0)


if __name__ == "__main__":
    unittest.main()
