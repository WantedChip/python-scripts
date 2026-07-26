"""
Unit tests for Typing Speed Test CLI
"""

import os
import shutil
import tempfile
import unittest

from main import HistoryManager, PassageManager, ScoreCalculator


class TestScoreCalculator(unittest.TestCase):
    def test_calculate_wpm(self) -> None:
        # 50 chars in 60 seconds = 10 words / 1 min = 10.0 WPM
        typed = "a" * 50
        wpm = ScoreCalculator.calculate_wpm(typed, 60.0)
        self.assertEqual(wpm, 10.0)

    def test_calculate_net_wpm(self) -> None:
        target = "The quick brown fox"
        typed = "The quick brown fox"
        # 19 chars in 30 sec (0.5 min) = (19/5)/0.5 = 7.6
        net_wpm = ScoreCalculator.calculate_net_wpm(target, typed, 30.0)
        self.assertGreater(net_wpm, 0)

    def test_calculate_accuracy(self) -> None:
        target = "hello world"
        typed = "hello wordd"
        acc = ScoreCalculator.calculate_accuracy(target, typed)
        self.assertLess(acc, 100.0)
        self.assertGreater(acc, 80.0)

    def test_highlight_errors(self) -> None:
        target = "abc"
        typed = "adc"
        diff, errors = ScoreCalculator.highlight_errors(target, typed)
        self.assertIn(1, errors)
        self.assertIn("d != b", diff)


class TestPassageManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "passages.json")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_add_and_get_passage(self) -> None:
        mgr = PassageManager(self.file_path)
        item = mgr.add_passage("Test passage text", "easy")
        self.assertEqual(item["text"], "Test passage text")

        fetched = mgr.get_passage("easy")
        self.assertIsNotNone(fetched)


class TestHistoryManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "history.json")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_log_and_load_score(self) -> None:
        mgr = HistoryManager(self.file_path)
        mgr.log_score(60.0, 55.0, 95.0, 30.0, "1")
        history = mgr.load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["gross_wpm"], 60.0)


if __name__ == "__main__":
    unittest.main()
