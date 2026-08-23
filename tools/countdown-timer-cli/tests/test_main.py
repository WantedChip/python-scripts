"""Unit tests for Countdown Timer CLI."""

import contextlib
import io
import unittest
from typing import List, Tuple
from unittest.mock import MagicMock, patch

from main import (
    PRESET_TIMERS,
    CountdownTimer,
    build_parser,
    format_time,
    main,
    parse_duration,
    render_progress_bar,
)


def _run_main(args: List[str]) -> Tuple[int, str, str]:
    """Runs ``main`` capturing stdout/stderr; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


class TestCountdownTimer(unittest.TestCase):
    """Test suite for duration parsing and countdown formatting."""

    def test_parse_duration_valid(self) -> None:
        self.assertEqual(parse_duration("10s"), 10)
        self.assertEqual(parse_duration("5m"), 300)
        self.assertEqual(parse_duration("1h"), 3600)
        self.assertEqual(parse_duration("1h30m20s"), 5420)
        self.assertEqual(parse_duration("120"), 120)

    def test_parse_duration_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("invalid")
        with self.assertRaises(ValueError):
            parse_duration("0s")
        with self.assertRaises(ValueError):
            parse_duration("-5m")

    def test_format_time(self) -> None:
        self.assertEqual(format_time(45), "00:45")
        self.assertEqual(format_time(125), "02:05")
        self.assertEqual(format_time(3665), "01:01:05")

    def test_render_progress_bar(self) -> None:
        bar = render_progress_bar(50, 100, width=10)
        self.assertIn("50%", bar)
        self.assertIn("00:50 remaining", bar)

    def test_non_interactive_execution(self) -> None:
        called = False

        def callback() -> None:
            nonlocal called
            called = True

        timer = CountdownTimer(duration_seconds=5, message="Done")
        timer.run(non_interactive=True, callback=callback)
        self.assertTrue(called)

    def test_presets_exist(self) -> None:
        self.assertIn("pomodoro", PRESET_TIMERS)
        self.assertEqual(PRESET_TIMERS["pomodoro"], 1500)


class TestParseDurationExtra(unittest.TestCase):
    """Additional parser cases: whitespace, mixed units, bad input."""

    def test_whitespace_is_tolerated_and_case_folded(self) -> None:
        self.assertEqual(parse_duration(" 90S "), 90)
        self.assertEqual(parse_duration(" 2H "), 7200)

    def test_plain_zero_or_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("")
        with self.assertRaises(ValueError):
            parse_duration("   ")
        with self.assertRaises(ValueError):
            parse_duration("0")

    def test_unitless_suffix_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("10x")

    def test_bare_units_without_digits_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_duration("hm")


class TestFormatAndBarEdges(unittest.TestCase):
    """Boundary rendering checks."""

    def test_format_time_boundaries(self) -> None:
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(59), "00:59")
        self.assertEqual(format_time(60), "01:00")
        self.assertEqual(format_time(3600), "01:00:00")

    def test_progress_bar_at_start_end_and_zero_total(self) -> None:
        start = render_progress_bar(100, 100, width=4)
        self.assertIn("  0%", start)
        end = render_progress_bar(0, 100, width=4)
        self.assertIn("100%", end)
        self.assertIn("00:00 remaining", end)
        self.assertEqual(end.count("█"), 4)
        zero_total = render_progress_bar(10, 0, width=4)
        self.assertIn("100%", zero_total)


class TestTimerRunModes(unittest.TestCase):
    """Execution paths of CountdownTimer.run."""

    @patch("main.time.sleep")
    def test_interactive_run_writes_progress_and_message(
        self, mock_sleep: MagicMock
    ) -> None:
        completed: List[str] = []
        timer = CountdownTimer(2, message="Tea ready")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            timer.run(callback=lambda: completed.append("done"))
        out = buffer.getvalue()
        self.assertIn("Starting timer for 00:02...", out)
        self.assertIn("🔔 Tea ready", out)
        self.assertEqual(completed, ["done"])
        self.assertGreaterEqual(mock_sleep.call_count, 1)

    @patch("main.time.sleep", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_reports_cancellation(
        self, mock_sleep: MagicMock
    ) -> None:
        timer = CountdownTimer(10)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            timer.run()
        self.assertIn("Timer cancelled by user.", buffer.getvalue())

    def test_non_interactive_without_callback(self) -> None:
        timer = CountdownTimer(7)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            timer.run(non_interactive=True)
        self.assertIn("Non-interactive run for 7s completed.", buffer.getvalue())


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI behaviour for flags and error reporting."""

    def test_list_presets_prints_table(self) -> None:
        code, out, _ = _run_main(["--list-presets"])
        self.assertEqual(code, 0)
        self.assertIn("Available presets:", out)
        self.assertIn(f"- pomodoro: {format_time(1500)} (1500s)", out)

    def test_invalid_duration_returns_error_code_one(self) -> None:
        code, _, err = _run_main(["-d", "banana"])
        self.assertEqual(code, 1)
        self.assertIn("Error:", err)

    def test_missing_duration_and_preset_shows_help(self) -> None:
        code, out, err = _run_main([])
        self.assertEqual(code, 1)
        self.assertIn("--duration or --preset", err)
        self.assertIn("usage:", out)

    def test_duration_non_interactive_runs_immediately(self) -> None:
        code, out, _ = _run_main(["-d", "45s", "--non-interactive"])
        self.assertEqual(code, 0)
        self.assertIn("Non-interactive run for 45s completed.", out)

    def test_preset_resolves_known_duration(self) -> None:
        code, out, _ = _run_main(["--preset", "tea", "--non-interactive"])
        self.assertEqual(code, 0)
        self.assertIn("Non-interactive run for 180s completed.", out)

    def test_custom_completion_message_forwarded(self) -> None:
        code, out, _ = _run_main(["-d", "1s", "--non-interactive", "-m", "Egg done"])
        self.assertEqual(code, 0)
        self.assertIn("Non-interactive run for 1s completed.", out)

    def test_parser_rejects_mutually_exclusive_flags(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["-d", "10s", "-p", "tea"])


if __name__ == "__main__":
    unittest.main()
