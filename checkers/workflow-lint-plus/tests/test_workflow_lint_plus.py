import sys
from unittest.mock import mock_open, patch

import pytest
import yaml

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/workflow-lint-plus")

# pylint: disable=wrong-import-position
from workflow_lint_plus import (  # noqa: E402
    check_cache_mistakes,
    check_duplicate_jobs,
    check_impossible_conditions,
    check_missing_timeouts,
    check_unnecessary_matrix,
    check_unpinned_actions,
    lint_workflow_file,
)


def test_check_unpinned_actions() -> None:
    """Test verification of unpinned actions."""
    # Properly pinned
    step_good = {"uses": "actions/checkout@8ade135a41bc03ea155e62e844d188df1fd71776"}
    assert check_unpinned_actions("job1", step_good, 1) == []

    # Tag pinned (security warning)
    step_tag = {"uses": "actions/checkout@v4"}
    warnings = check_unpinned_actions("job1", step_tag, 1)
    assert len(warnings) == 1
    assert "not pinned to a full SHA" in warnings[0]

    # Local action (should skip)
    step_local = {"uses": "./.github/actions/local"}
    assert check_unpinned_actions("job1", step_local, 1) == []

    # No version
    step_no_version = {"uses": "actions/checkout"}
    warnings2 = check_unpinned_actions("job1", step_no_version, 1)
    assert len(warnings2) == 1
    assert "no version reference" in warnings2[0]


def test_check_missing_timeouts() -> None:
    """Test detection of missing timeouts."""
    # Job has timeout
    job_good = {"timeout-minutes": 10}
    assert check_missing_timeouts("job1", job_good, [{"run": "echo"}]) == []

    # Job has no timeout, but step has timeout
    job_step_timeout = {}
    steps = [{"run": "echo", "timeout-minutes": 5}]
    assert check_missing_timeouts("job1", job_step_timeout, steps) == []

    # Job has no timeout, step has no timeout
    job_bad = {}
    steps_bad = [{"run": "echo"}]
    warnings = check_missing_timeouts("job1", job_bad, steps_bad)
    assert len(warnings) == 1
    assert "Missing 'timeout-minutes'" in warnings[0]


def test_check_impossible_conditions() -> None:
    """Test identification of impossible/redundant conditions."""
    # success() and failure() combined with &&
    cond1 = "success() && failure()"
    warnings = check_impossible_conditions("job1", cond1, is_job=True)
    assert len(warnings) == 1
    assert "impossible" in warnings[0]

    # always() and success()
    cond2 = "always() && success()"
    warnings2 = check_impossible_conditions("step1", cond2, is_job=False)
    assert len(warnings2) == 1
    assert "redundant" in warnings2[0]

    # always() and failure()
    cond3 = "always() && failure()"
    warnings3 = check_impossible_conditions("step1", cond3, is_job=False)
    assert len(warnings3) == 1
    assert "redundant" in warnings3[0]


def test_check_unnecessary_matrix() -> None:
    """Test warnings for redundant single-value matrices."""
    job_good = {"strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}}}
    assert check_unnecessary_matrix("job1", job_good) == []

    job_bad = {"strategy": {"matrix": {"python-version": ["3.12"]}}}
    warnings = check_unnecessary_matrix("job1", job_bad)
    assert len(warnings) == 1
    assert "only one value" in warnings[0]


def test_check_cache_mistakes() -> None:
    """Test caching configuration rules."""
    # Missing key/path
    step_bad = {"uses": "actions/cache@v4", "with": {}}
    warnings = check_cache_mistakes("job1", step_bad, 1)
    assert len(warnings) == 2
    assert "missing the 'key'" in warnings[0]
    assert "missing the 'path'" in warnings[1]

    # Outdated cache version
    step_outdated = {
        "uses": "actions/cache@v1",
        "with": {"key": "cache-key", "path": "node_modules"},
    }
    warnings2 = check_cache_mistakes("job1", step_outdated, 1)
    assert len(warnings2) == 1
    assert "outdated" in warnings2[0]


def test_check_duplicate_jobs() -> None:
    """Test discovery of duplicate jobs with identical steps."""
    jobs = {
        "job1": {
            "steps": [
                {"uses": "actions/checkout@v4"},
                {"run": "pip install -r requirements.txt"},
            ]
        },
        "job2": {
            "steps": [
                {"uses": "actions/checkout@v4"},
                {"run": "pip install -r requirements.txt"},
            ]
        },
    }
    warnings = check_duplicate_jobs(jobs)
    assert len(warnings) == 1
    assert "identical execution steps" in warnings[0]


def test_lint_workflow_file_integration() -> None:
    """Test full integration of lint rules on a GHA workflow definition."""
    workflow = {
        "name": "CI",
        "jobs": {
            "build": {
                "timeout-minutes": 10,
                "strategy": {"matrix": {"node": [18]}},
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {"uses": "actions/cache@v1", "with": {"key": "cache"}},
                ],
            }
        },
    }
    m = mock_open(read_data=yaml.dump(workflow))
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        warnings = lint_workflow_file("workflow.yml")
        # Should catch:
        # 1. Single value matrix 'node'
        # 2. Checkout unpinned SHA
        # 3. Cache missing path
        # 4. Outdated cache v1
        # 5. Cache unpinned SHA
        assert len(warnings) == 5

    # Test file-not-found
    with patch("os.path.exists", return_value=False):
        assert "File not found" in lint_workflow_file("missing.yml")[0]

    # Test YAML parse error
    m_invalid = mock_open(read_data="{invalid yaml")
    with patch("builtins.open", m_invalid), patch("os.path.exists", return_value=True):
        assert "YAML Parse Error" in lint_workflow_file("invalid.yml")[0]

    # Test invalid layout
    m_list = mock_open(read_data="[1, 2, 3]")
    with patch("builtins.open", m_list), patch("os.path.exists", return_value=True):
        assert "Invalid GHA workflow layout" in lint_workflow_file("list.yml")[0]


def test_edge_cases_and_main() -> None:
    """Test GHA edge case logic and linter main function."""
    # 1. Non-string condition
    assert check_impossible_conditions("id", None) == []  # type: ignore[arg-type]

    # 2. Non-dict matrix
    assert check_unnecessary_matrix("job", {"strategy": {"matrix": "string"}}) == []

    # 3. Non-dict jobs / empty jobs in duplicate check
    assert check_duplicate_jobs({"job1": "not-a-dict"}) == []
    assert check_duplicate_jobs({"job1": {"steps": None}}) == []

    # 4. lint_workflow_file invalid jobs dict
    invalid_workflow = {"jobs": "not-a-dict"}
    m = mock_open(read_data=yaml.dump(invalid_workflow))
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        assert "Invalid 'jobs' element" in lint_workflow_file("invalid_jobs.yml")[0]

    # 5. Job has list of steps instead of dicts, or other weird structures
    weird_workflow = {
        "jobs": {
            "build": {
                "if": "success() && failure()",
                "steps": [
                    "not-a-dict",
                    {
                        "uses": (
                            "actions/checkout@"
                            "8ade135a41bc03ea155e62e844d188df1fd71776"
                        )
                    },
                ],
            }
        }
    }
    m2 = mock_open(read_data=yaml.dump(weird_workflow))
    with patch("builtins.open", m2), patch("os.path.exists", return_value=True):
        warnings = lint_workflow_file("weird.yml")
        # should catch the impossible condition at job level
        assert any("impossible" in w for w in warnings)

    # 6. Test CLI main function
    from workflow_lint_plus import main as linter_main

    # No files found path
    with patch("sys.argv", ["workflow-lint-plus", "nonexistent-dir"]), patch(
        "os.path.isdir", return_value=False
    ), patch("os.path.isfile", return_value=False):
        with pytest.raises(SystemExit) as exc:
            linter_main()
        assert exc.value.code == 0

    # File found path, run successfully
    with patch("sys.argv", ["workflow-lint-plus", "wf.yml"]), patch(
        "os.path.isdir", return_value=False
    ), patch("os.path.isfile", return_value=True), patch(
        "workflow_lint_plus.lint_workflow_file", return_value=[]
    ):
        with pytest.raises(SystemExit) as exc:
            linter_main()
        assert exc.value.code == 0

    # File found path, warnings exit code 1
    with patch("sys.argv", ["workflow-lint-plus", "wf.yml"]), patch(
        "os.path.isdir", return_value=False
    ), patch("os.path.isfile", return_value=True), patch(
        "workflow_lint_plus.lint_workflow_file", return_value=["warn"]
    ):
        with pytest.raises(SystemExit) as exc:
            linter_main()
        assert exc.value.code == 1

    # Directory walk path
    with patch("sys.argv", ["workflow-lint-plus", "workflows_dir"]), patch(
        "os.path.isdir", return_value=True
    ), patch("os.walk", return_value=[("workflows_dir", [], ["ci.yml"])]), patch(
        "workflow_lint_plus.lint_workflow_file", return_value=[]
    ):
        with pytest.raises(SystemExit) as exc:
            linter_main()
        assert exc.value.code == 0
