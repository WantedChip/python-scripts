"""Tests for Cron Job Health Checker."""

import datetime
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import cron_health_checker  # noqa: E402


def test_matches_field() -> None:
    """Test cron matches field logic."""
    # Wildcard
    assert cron_health_checker.matches_field(12, "*") is True
    # Step
    assert cron_health_checker.matches_field(15, "*/5") is True
    assert cron_health_checker.matches_field(17, "*/5") is False
    assert cron_health_checker.matches_field(10, "*/invalid") is False
    # List
    assert cron_health_checker.matches_field(2, "1,2,3") is True
    assert cron_health_checker.matches_field(5, "1,2,3") is False
    # Range
    assert cron_health_checker.matches_field(3, "1-5") is True
    assert cron_health_checker.matches_field(7, "1-5") is False
    assert cron_health_checker.matches_field(3, "1-invalid") is False
    # Value
    assert cron_health_checker.matches_field(10, "10") is True
    assert cron_health_checker.matches_field(10, "invalid") is False


def test_get_next_cron_time() -> None:
    """Test native cron step simulation logic."""
    anchor = datetime.datetime(2026, 7, 11, 12, 0, 0)  # A Saturday
    # Every 5 minutes
    next_t = cron_health_checker.get_next_cron_time(anchor, "*/5 * * * *")
    assert next_t == datetime.datetime(2026, 7, 11, 12, 5, 0)

    # Every Sunday (weekday 0 in cron)
    # 2026-07-11 is Saturday. Sunday is 2026-07-12.
    next_sun = cron_health_checker.get_next_cron_time(anchor, "0 0 * * 0")
    assert next_sun == datetime.datetime(2026, 7, 12, 0, 0, 0)

    # Invalid expression
    with pytest.raises(ValueError):
        cron_health_checker.get_next_cron_time(anchor, "* * *")


def test_parse_log_line() -> None:
    """Test parsing standard log entries."""
    parsed1 = cron_health_checker.parse_log_line(
        "2026-07-11 12:00:00 - backup-job - START"
    )
    assert parsed1 is not None
    assert parsed1[1] == "backup-job"
    assert parsed1[2] == "START"

    parsed2 = cron_health_checker.parse_log_line(
        "2026-07-11 12:05:12 - backup-job - END - SUCCESS"
    )
    assert parsed2 is not None
    assert parsed2[2] == "END"
    assert parsed2[3] == "SUCCESS"

    assert cron_health_checker.parse_log_line("invalid log line format") is None
    assert (
        cron_health_checker.parse_log_line("2026-99-99 12:00:00 - job - START") is None
    )


def test_check_cron_health() -> None:
    """Test auditing health issues for failures, overlaps, stuck, and missed tasks."""
    logs = [
        "2026-07-11 12:00:00 - job_a - START",
        "2026-07-11 12:02:00 - job_a - END - SUCCESS",
        # Overlap test
        "2026-07-11 12:05:00 - job_a - START",
        "2026-07-11 12:06:00 - job_a - START",  # Overlap!
        "2026-07-11 12:08:00 - job_a - END - SUCCESS",
        # Failure test
        "2026-07-11 12:10:00 - job_a - START",
        "2026-07-11 12:12:00 - job_a - END - ERROR - exit status 1",
    ]
    schedules = {"job_a": "*/5 * * * *"}
    issues = cron_health_checker.check_cron_health(logs, schedules, threshold_min=60)

    # Overlap and Failure should be detected
    types = [issue.issue_type for issue in issues]
    assert "OVERLAP" in types
    assert "FAILURE" in types


def test_check_cron_health_missed() -> None:
    """Test auditing missed cron run events."""
    logs = [
        "2026-07-11 12:00:00 - job_a - START",
        "2026-07-11 12:01:00 - job_a - END - SUCCESS",
        # Missing 12:05 execution
        "2026-07-11 12:10:00 - job_a - START",
        "2026-07-11 12:11:00 - job_a - END - SUCCESS",
    ]
    schedules = {"job_a": "*/5 * * * *"}
    issues = cron_health_checker.check_cron_health(logs, schedules, threshold_min=60)

    types = [issue.issue_type for issue in issues]
    assert "MISSED" in types


def test_main_cli_health_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI runs with expected inputs and output JSON report files."""
    log_file = tmp_path / "cron.log"
    log_file.write_text(
        "2026-07-11 12:00:00 - job_a - START\n"
        "2026-07-11 12:02:00 - job_a - END - ERROR - code 1\n",
        encoding="utf-8",
    )
    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({"job_a": "*/5 * * * *"}), encoding="utf-8")
    out_json = tmp_path / "out.json"

    args = [
        "cron_health_checker.py",
        "-i",
        str(log_file),
        "-s",
        str(schedules_file),
        "-o",
        str(out_json),
    ]
    monkeypatch.setattr(sys, "argv", args)
    cron_health_checker.main()

    assert out_json.exists()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["issue_type"] == "FAILURE"


def test_main_cli_missing_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exits 1 on missing log files."""
    args = ["cron_health_checker.py", "-i", "nonexistent_cron.log"]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        cron_health_checker.main()
    assert exc.value.code == 1


def test_main_cli_missing_schedules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test CLI behavior when schedule reference file is missing."""
    log_file = tmp_path / "cron.log"
    log_file.write_text("2026-07-11 12:00:00 - job_a - START\n", encoding="utf-8")

    args = [
        "cron_health_checker.py",
        "-i",
        str(log_file),
        "-s",
        "nonexistent_schedules.json",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        cron_health_checker.main()
    assert exc.value.code == 1
