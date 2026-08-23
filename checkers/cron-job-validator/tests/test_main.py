"""Unit tests for Cron Job Validator."""

import contextlib
import datetime
import io
import json
import sys
import unittest
from unittest import mock

import main as main_module
from main import (
    check_cron_conflicts,
    get_next_executions,
    parse_cron_expression,
    validate_cron,
)


class TestCronJobValidator(unittest.TestCase):

    def test_validate_cron_valid(self) -> None:
        self.assertTrue(validate_cron("0 0 * * *")[0])
        self.assertTrue(validate_cron("*/15 9-17 1,15 JAN,JUN MON-FRI")[0])
        self.assertTrue(validate_cron("0 12 * * 0")[0])

    def test_validate_cron_invalid(self) -> None:
        self.assertFalse(validate_cron("60 * * * *")[0])  # Minute 60 invalid
        self.assertFalse(validate_cron("* * * *")[0])  # Too few fields
        self.assertFalse(validate_cron("0 0 32 * *")[0])  # Day 32 invalid

    def test_parse_cron_expression(self) -> None:
        parsed = parse_cron_expression("0 12 * * *")
        self.assertIn(0, parsed[0])
        self.assertEqual(len(parsed[0]), 1)
        self.assertIn(12, parsed[1])
        self.assertEqual(len(parsed[3]), 12)  # All 12 months

    def test_get_next_executions(self) -> None:
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=utc)
        runs = get_next_executions("0 * * * *", count=3, start_time=start)
        self.assertEqual(len(runs), 3)
        self.assertIn("2026-01-01 01:00:00 UTC", runs[0])
        self.assertIn("2026-01-01 02:00:00 UTC", runs[1])
        self.assertIn("2026-01-01 03:00:00 UTC", runs[2])

    def test_check_cron_conflicts(self) -> None:
        jobs = [
            ("Job1", "0 * * * *"),
            ("Job2", "0 0-23/2 * * *"),
        ]
        conflicts = check_cron_conflicts(jobs, window_minutes=120)
        self.assertGreater(len(conflicts), 0)
        self.assertIn("Job1", conflicts[0]["conflicting_jobs"])
        self.assertIn("Job2", conflicts[0]["conflicting_jobs"])


class TestCronParsingEdgeCases(unittest.TestCase):
    """Tests for parser edge cases: steps, ranges, names, 6-field input."""

    def test_empty_subtokens_are_ignored(self) -> None:
        """Double commas produce empty subtokens that are skipped."""
        parsed = parse_cron_expression("1,,3 * * * *")
        self.assertEqual(parsed[0], {1, 3})

    def test_zero_step_is_rejected(self) -> None:
        """A step of zero raises a validation error."""
        valid, err = validate_cron("*/0 * * * *")
        self.assertFalse(valid)
        self.assertIn("Step value must be > 0", err)

    def test_reversed_range_is_rejected(self) -> None:
        """A range whose start exceeds its end raises a validation error."""
        valid, err = validate_cron("10-2 * * * *")
        self.assertFalse(valid)
        self.assertIn("Invalid range start > end", err)

    def test_out_of_bounds_value_is_rejected(self) -> None:
        """Values beyond the field limit are rejected."""
        valid, err = validate_cron("* 25 * * *")
        self.assertFalse(valid)
        self.assertIn("out of bounds", err)

    def test_sunday_seven_normalized_to_zero(self) -> None:
        """Day-of-week 7 wraps around to Sunday (0)."""
        parsed = parse_cron_expression("* * * * SUN")
        self.assertEqual(parsed[4], {0})
        parsed = parse_cron_expression("* * * * 7")
        self.assertEqual(parsed[4], {0})

    def test_six_field_expression_with_seconds(self) -> None:
        """A leading numeric field <= 59 is interpreted as seconds."""
        parsed = parse_cron_expression("30 0 12 * * *")
        self.assertEqual(parsed[0], {0})  # minutes
        self.assertEqual(parsed[1], {12})  # hours

    def test_six_field_expression_without_seconds(self) -> None:
        """A leading '*' shifts the field window instead of seconds."""
        parsed = parse_cron_expression("* 15 10 * * *")
        # Fields shift: minute='*', hour=15, dom=10, month=*, dow=*
        self.assertEqual(parsed[0], set(range(60)))
        self.assertEqual(parsed[1], {15})
        self.assertEqual(parsed[2], {10})


class TestConflictSkips(unittest.TestCase):
    """Tests for conflict checker robustness."""

    def test_conflict_checker_skips_invalid_expressions(self) -> None:
        """Invalid expressions are dropped without aborting the scan."""
        jobs = [("Bad", "not a cron"), ("Good", "0 * * * *")]
        conflicts = check_cron_conflicts(jobs, window_minutes=60)
        for conflict in conflicts:
            self.assertEqual(conflict["conflicting_jobs"], ["Good"])

    def test_disjoint_jobs_never_overlap(self) -> None:
        """Jobs pinned to disjoint months cannot overlap in any window."""
        jobs = [("Winter", "0 0 * 1 *"), ("Summer", "0 0 * 7 *")]
        self.assertEqual(check_cron_conflicts(jobs, window_minutes=2880), [])


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def _run_main(self, argv: list) -> tuple:
        """Run main() with patched argv; return (code, stdout, stderr)."""
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with mock.patch.object(sys, "argv", ["main.py"] + argv):
                try:
                    main_module.main()
                except SystemExit as exc:
                    code = int(exc.code if exc.code is not None else 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_main_no_args_prints_help_exits_zero(self) -> None:
        """Invoking without cron expressions prints help and exits 0."""
        code, out, _ = self._run_main([])
        self.assertEqual(code, 0)
        self.assertIn("usage:", out)

    def test_main_text_output_mixed_validity(self) -> None:
        """Text output marks valid and invalid expressions distinctly."""
        code, out, _ = self._run_main(["*/5 * * * *", "99 * * * *"])
        self.assertEqual(code, 0)
        self.assertIn("VALID", out)
        self.assertIn("INVALID (", out)
        self.assertIn("Next executions:", out)

    def test_main_json_report_with_conflicts(self) -> None:
        """JSON mode includes validation entries and detected conflicts."""
        code, out, _ = self._run_main(
            ["0 * * * *", "0 * * * *", "--check-conflicts", "--json"]
        )
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(len(report["validation"]), 2)
        self.assertTrue(report["validation"][0]["valid"])
        self.assertTrue(report["conflicts"])
        self.assertEqual(
            set(report["conflicts"][0]["conflicting_jobs"]), {"Job_1", "Job_2"}
        )

    def test_main_conflict_flag_with_single_job_skips_check(self) -> None:
        """Conflict detection needs at least two valid jobs."""
        code, out, _ = self._run_main(["0 * * * *", "--check-conflicts", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["conflicts"], [])

    def test_main_text_overlap_display(self) -> None:
        """Two identical hourly schedules overlap and are listed in text."""
        code, out, _ = self._run_main(["0 * * * *", "0 * * * *", "--check-conflicts"])
        self.assertEqual(code, 0)
        self.assertIn("Overlap at", out)
        self.assertIn("[Job_1, Job_2]", out)

    def test_main_text_no_overlaps_message(self) -> None:
        """Disjoint schedules produce the clean-scan message."""
        code, out, _ = self._run_main(["0 0 * 1 *", "0 0 * 7 *", "--check-conflicts"])
        self.assertEqual(code, 0)
        self.assertIn("No scheduling overlaps detected.", out)


if __name__ == "__main__":
    unittest.main()
