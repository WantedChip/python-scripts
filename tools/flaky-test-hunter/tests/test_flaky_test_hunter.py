import json
import sys
from unittest.mock import mock_open, patch

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/flaky-test-hunter")

# pylint: disable=wrong-import-position
from flaky_test_hunter import (  # noqa: E402
    analyze_outcomes,
    create_plugin_file,
    hunt_flaky_tests,
    run_test_iteration,
)


def test_create_plugin_file() -> None:
    """Test generating temporary pytest plugin file content."""
    m = mock_open()
    with patch("builtins.open", m):
        create_plugin_file("plugin.py", 42, 0.01, 0.05, "results.json")
        m.assert_called_with("plugin.py", "w", encoding="utf-8")
        # Ensure path is escaped properly in output
        written_data = "".join(call[0][0] for call in m().write.call_args_list)
        assert "SEED = 42" in written_data
        assert "MIN_DELAY = 0.01" in written_data
        assert (
            'RESULT_PATH = "results.json"' in written_data
            or 'RESULT_PATH = "results.json".replace' in written_data
        )


def test_analyze_outcomes() -> None:
    """Test classification and sorting of test outcomes."""
    # Outcomes: test1 fails twice, passes once -> Flaky
    # Outcomes: test2 fails three times -> Consistently failing
    # Outcomes: test3 passes three times -> Passed
    outcomes = [
        [
            {"nodeid": "test1", "outcome": "passed", "duration": 0.1},
            {"nodeid": "test2", "outcome": "failed", "duration": 0.1},
            {"nodeid": "test3", "outcome": "passed", "duration": 0.1},
        ],
        [
            {"nodeid": "test1", "outcome": "failed", "duration": 0.1},
            {"nodeid": "test2", "outcome": "failed", "duration": 0.1},
            {"nodeid": "test3", "outcome": "passed", "duration": 0.1},
        ],
        [
            {"nodeid": "test1", "outcome": "failed", "duration": 0.1},
            {"nodeid": "test2", "outcome": "failed", "duration": 0.1},
            {"nodeid": "test3", "outcome": "passed", "duration": 0.1},
        ],
    ]

    reports = analyze_outcomes(outcomes)
    assert len(reports) == 3

    # Check classifications
    test1_report = next(r for r in reports if r["nodeid"] == "test1")
    assert test1_report["status"] == "FLAKY"
    assert test1_report["passes"] == 1
    assert test1_report["failures"] == 2

    test2_report = next(r for r in reports if r["nodeid"] == "test2")
    assert test2_report["status"] == "CONSISTENTLY_FAILING"

    test3_report = next(r for r in reports if r["nodeid"] == "test3")
    assert test3_report["status"] == "PASSED"

    # FLAKY should sort first
    assert reports[0]["nodeid"] == "test1"


def test_run_test_iteration() -> None:
    """Test running a single test iteration via subprocess mocking."""
    iter_outcomes = [{"nodeid": "test1", "outcome": "passed", "duration": 0.05}]

    with patch("flaky_test_hunter.create_plugin_file"), patch(
        "subprocess.run"
    ) as mock_sub, patch(
        "os.path.exists", side_effect=lambda p: p.endswith(".json") or p.endswith(".py")
    ), patch(
        "builtins.open", mock_open(read_data=json.dumps(iter_outcomes))
    ), patch(
        "os.remove"
    ):
        results = run_test_iteration("pytest", "tests", 1, 42, 0.0, 0.0)
        assert len(results) == 1
        assert results[0]["nodeid"] == "test1"
        mock_sub.assert_called_once()


def test_hunt_flaky_tests_integration() -> None:
    """Test end-to-end hunter execution orchestration."""
    iter_results = [[{"nodeid": "test_ok", "outcome": "passed", "duration": 0.1}]]

    with patch(
        "flaky_test_hunter.run_test_iteration",
        side_effect=iter_results,
    ):
        exit_code = hunt_flaky_tests("tests", 1, 0.0, 0.0)
        assert exit_code == 0

    # No test results
    with patch(
        "flaky_test_hunter.run_test_iteration",
        return_value=[],
    ):
        exit_code_empty = hunt_flaky_tests("tests", 1, 0.0, 0.0)
        assert exit_code_empty == 1
