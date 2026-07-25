"""Unit tests for Cron Job Validator."""

import datetime
import unittest

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


if __name__ == "__main__":
    unittest.main()
