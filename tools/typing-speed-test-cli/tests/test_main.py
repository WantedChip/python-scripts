"""
Unit tests for Typing Speed Test CLI
"""

import contextlib
import io
import json
import os
import runpy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

import main as typing_module
from main import (
    DEFAULT_PASSAGES,
    HistoryManager,
    PassageManager,
    ScoreCalculator,
    build_parser,
    main,
    run_typing_test,
)


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


class TestScoreCalculatorEdgeCases(unittest.TestCase):
    """Boundary-condition tests for score math."""

    def test_zero_elapsed_time_yields_zero_wpm(self) -> None:
        """Both WPM formulas guard against zero-duration runs."""
        self.assertEqual(ScoreCalculator.calculate_wpm("hello", 0.0), 0.0)
        self.assertEqual(ScoreCalculator.calculate_net_wpm("hello", "hello", -1.0), 0.0)

    def test_net_wpm_never_negative(self) -> None:
        """A very error-heavy run clamps to zero Net WPM."""
        target = "a" * 50
        typed = "z" * 50
        net = ScoreCalculator.calculate_net_wpm(target, typed, 1.0)
        self.assertEqual(net, 0.0)
        self.assertEqual(ScoreCalculator.calculate_net_wpm("", "", 10.0), 0.0)

    def test_accuracy_with_empty_target_is_perfect(self) -> None:
        """An empty target text is treated as fully accurate."""
        self.assertEqual(ScoreCalculator.calculate_accuracy("", "anything"), 100.0)

    def test_accuracy_penalizes_missing_characters(self) -> None:
        """Typed input shorter than the target lowers the score."""
        acc = ScoreCalculator.calculate_accuracy("abcdef", "abc")
        self.assertEqual(acc, 50.0)

    def test_highlight_marks_missing_typed_characters(self) -> None:
        """Characters absent from the typed input render as MISSING."""
        diff, errors = ScoreCalculator.highlight_errors("abcd", "ab")
        self.assertIn("c_MISSING", diff)
        self.assertIn("d_MISSING", diff)
        self.assertEqual(errors, [2, 3])


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

    def test_missing_file_falls_back_to_defaults(self) -> None:
        """Without a stored file the default library is loaded."""
        missing = os.path.join(self.temp_dir, "nope.json")
        mgr = PassageManager(missing)
        self.assertEqual(mgr.passages, DEFAULT_PASSAGES)

    def test_corrupt_file_falls_back_to_defaults(self) -> None:
        """Unparseable JSON files fall back to the default library."""
        with open(self.file_path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        mgr = PassageManager(self.file_path)
        self.assertEqual(mgr.passages, DEFAULT_PASSAGES)

    def test_valid_file_is_loaded_verbatim(self) -> None:
        """A well-formed JSON library is loaded as-is."""
        custom = [
            {"id": "1", "difficulty": "hard", "text": "custom passage"},
        ]
        with open(self.file_path, "w", encoding="utf-8") as handle:
            json.dump(custom, handle)
        mgr = PassageManager(self.file_path)
        self.assertEqual(mgr.passages, custom)

    def test_add_passage_persists_and_normalizes(self) -> None:
        """Added passages are saved to disk with normalized fields."""
        mgr = PassageManager(self.file_path)
        item = mgr.add_passage("  padded text  ", "HARD")
        self.assertEqual(item["difficulty"], "hard")
        self.assertEqual(item["text"], "padded text")
        reloaded = PassageManager(self.file_path)
        self.assertIn(item, reloaded.passages)

    def test_get_passage_filters_by_difficulty(self) -> None:
        """Difficulty selection only returns matching passages."""
        mgr = PassageManager(self.file_path)
        easy_ids = {p["id"] for p in DEFAULT_PASSAGES if p["difficulty"] == "easy"}
        for _ in range(20):
            self.assertIn(mgr.get_passage("EASY")["id"], easy_ids)

    def test_unknown_difficulty_falls_back_to_all(self) -> None:
        """A difficulty with no matches selects from every passage."""
        mgr = PassageManager(self.file_path)
        all_ids = {p["id"] for p in mgr.passages}
        for _ in range(20):
            self.assertIn(mgr.get_passage("impossible")["id"], all_ids)


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

    def test_missing_or_corrupt_history_returns_empty(self) -> None:
        """Missing and unreadable history files both yield empty lists."""
        missing = HistoryManager(os.path.join(self.temp_dir, "none.json"))
        self.assertEqual(missing.load_history(), [])
        with open(self.file_path, "w", encoding="utf-8") as handle:
            handle.write("definitely not json")
        corrupt = HistoryManager(self.file_path)
        self.assertEqual(corrupt.load_history(), [])


class TestRunTypingTest(unittest.TestCase):
    """Interactive-session tests using scripted stdin and clock mocks."""

    PASSAGE: Dict[str, str] = {
        "id": "42",
        "difficulty": "easy",
        "text": "hello world",
    }

    def run_session(
        self,
        inputs: List[str],
        passage: Dict[str, str],
        history_mgr: Optional[HistoryManager] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Simulate one interactive session with a fixed 30s duration."""
        buffer = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs):
            with mock.patch.object(
                typing_module.time, "time", side_effect=[100.0, 130.0]
            ):
                with contextlib.redirect_stdout(buffer):
                    result = run_typing_test(passage, history_mgr)
        return result, buffer.getvalue()

    def test_perfect_run_reports_full_accuracy(self) -> None:
        """Typing the exact passage yields zero errors and 100% accuracy."""
        result, output = self.run_session(["", "hello world"], self.PASSAGE)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["accuracy"], 100.0)
        self.assertAlmostEqual(result["duration"], 30.0)
        # 11 chars / 5 = 2.2 words in 0.5 minutes = 4.4 gross WPM
        self.assertAlmostEqual(result["gross_wpm"], 4.4)
        self.assertNotIn("Error Comparison Visualization", output)

    def test_error_run_prints_visualization_and_saves_history(self) -> None:
        """Mistyped runs show a visualization and persist a history entry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = HistoryManager(os.path.join(tmp_dir, "h.json"))
            result, output = self.run_session(
                ["", "hxllo worzd"], self.PASSAGE, history
            )
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "h.json")))
        self.assertEqual(result["errors"], 2)
        self.assertIn("Error Comparison Visualization:", output)
        self.assertIn("[x != e]", output)
        self.assertIn("Score saved to history!", output)


class TestCommandLine(unittest.TestCase):
    """CLI tests exercising each non-interactive subcommand."""

    def capture_main(self, args_list: List[str]) -> Tuple[int, str]:
        """Run main() capturing stdout inside a scratch cwd."""
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                with contextlib.redirect_stdout(buffer):
                    code = main(args_list)
        return code, buffer.getvalue()

    def test_history_empty_message(self) -> None:
        """--history with no recorded tests reports an empty history."""
        code, out = self.capture_main(["--history"])
        self.assertEqual(code, 0)
        self.assertIn("No test history found.", out)

    def test_history_lists_previous_scores(self) -> None:
        """--history renders one line per logged entry."""
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                HistoryManager().log_score(61.5, 55.0, 93.0, 25.0, "2")
                with contextlib.redirect_stdout(buffer):
                    code = main(["--history"])
        self.assertEqual(code, 0)
        self.assertIn("=== SCORE HISTORY ===", buffer.getvalue())
        self.assertIn("Gross WPM: 61.5", buffer.getvalue())

    def test_list_passages_shows_library(self) -> None:
        """--list-passages prints every passage with its difficulty."""
        code, out = self.capture_main(["--list-passages"])
        self.assertEqual(code, 0)
        self.assertIn("=== PASSAGE LIBRARY ===", out)
        self.assertIn("Difficulty: EASY", out)
        self.assertIn("quick brown fox", out)

    def test_add_passage_command(self) -> None:
        """--add-passage appends to the on-disk passage library."""
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                with contextlib.redirect_stdout(buffer):
                    code = main(
                        ["--add-passage", "custom words here", "--difficulty", "hard"]
                    )
                stored = json.loads(
                    Path("typing_passages.json").read_text(encoding="utf-8")
                )
                with contextlib.redirect_stdout(buffer):
                    code_list = main(["--list-passages"])
        self.assertEqual(code, 0)
        self.assertIn("Passage added successfully with ID 6 (hard)!", buffer.getvalue())
        self.assertEqual(stored[-1]["text"], "custom words here")
        self.assertEqual(code_list, 0)

    def test_interactive_flow_runs_selected_difficulty(self) -> None:
        """The default command starts a test for the chosen difficulty."""
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                with mock.patch(
                    "builtins.input", side_effect=["", "The quick brown fox"]
                ):
                    with mock.patch.object(
                        typing_module.time, "time", side_effect=[0.0, 60.0]
                    ):
                        with contextlib.redirect_stdout(buffer):
                            code = main(["--difficulty", "easy"])
        self.assertEqual(code, 0)
        self.assertIn("TYPING SPEED TEST (Difficulty: EASY)", buffer.getvalue())
        self.assertIn("TEST RESULTS:", buffer.getvalue())

    def test_parser_flags_exist(self) -> None:
        """The parser exposes difficulty choices and boolean flags."""
        parser = build_parser()
        parsed = parser.parse_args(["--difficulty", "medium"])
        self.assertEqual(parsed.difficulty, "medium")
        flags = parser.parse_args([])
        self.assertFalse(flags.history)
        self.assertFalse(flags.list_passages)
        self.assertIsNone(flags.add_passage)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program lists passages cleanly."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        argv = [entry, "--list-passages"]
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                with mock.patch.object(sys, "argv", argv):
                    with contextlib.redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as ctx:
                            runpy.run_path(entry, run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("PASSAGE LIBRARY", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
