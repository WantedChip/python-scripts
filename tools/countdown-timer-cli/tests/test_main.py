"""Unit tests for Countdown Timer CLI."""

import unittest

from main import (
    PRESET_TIMERS,
    CountdownTimer,
    format_time,
    parse_duration,
    render_progress_bar,
)


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


if __name__ == "__main__":
    unittest.main()
