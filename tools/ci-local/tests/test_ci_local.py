import sys
from unittest.mock import mock_open, patch

import pytest
import yaml

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/ci-local")

# pylint: disable=wrong-import-position
from ci_local import (  # noqa: E402
    analyze_step,
    expand_matrix,
    generate_local_script,
    get_jobs,
    parse_workflow,
    process_workflow_local,
    resolve_expression,
)

SAMPLE_WORKFLOW = """
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18, 20]
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Use Node.js ${{ matrix.node-version }}
        uses: actions/setup-python@v5
      - name: Cache dependencies
        uses: actions/cache@v4
      - name: Install dependencies
        run: npm ci
      - name: Third Party
        uses: other/action@v1
"""


def test_parse_workflow_valid() -> None:
    """Test parsing a valid workflow file."""
    m = mock_open(read_data=SAMPLE_WORKFLOW)
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        wf = parse_workflow("fake_path.yml")
        assert wf["name"] == "CI"
        assert "build" in wf["jobs"]


def test_parse_workflow_file_not_found() -> None:
    """Test parsing workflow file that does not exist."""
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError):
            parse_workflow("nonexistent.yml")


def test_parse_workflow_invalid() -> None:
    """Test parsing invalid workflow files."""
    m = mock_open(read_data="[invalid yaml")
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        with pytest.raises(yaml.YAMLError):
            parse_workflow("invalid.yml")

    m2 = mock_open(read_data="not-a-dict")
    with patch("builtins.open", m2), patch("os.path.exists", return_value=True):
        with pytest.raises(ValueError):
            parse_workflow("string.yml")


def test_get_jobs() -> None:
    """Test retrieving jobs from parsed workflow."""
    wf = {"jobs": {"job1": {"name": "Job 1"}}}
    assert get_jobs(wf) == {"job1": {"name": "Job 1"}}
    assert get_jobs({}) == {}


def test_expand_matrix() -> None:
    """Test matrix expansion for combinations."""
    matrix = {"os": ["ubuntu-latest", "windows-latest"], "python": ["3.11", "3.12"]}
    combos = expand_matrix(matrix)
    assert len(combos) == 4
    assert {"os": "ubuntu-latest", "python": "3.11"} in combos
    assert {"os": "windows-latest", "python": "3.12"} in combos

    # Test single/empty matrix
    assert expand_matrix({}) == [{}]
    assert expand_matrix({"single": ["val"]}) == [{"single": "val"}]


def test_resolve_expression() -> None:
    """Test expression resolution with matrix variables."""
    assert resolve_expression("test-${{ matrix.os }}", {"os": "linux"}) == "test-linux"
    assert resolve_expression("${{ matrix.py }}", {"py": "3.12"}) == "3.12"
    # Fallback/non-matrix expressions
    assert resolve_expression("${{ secrets.TOKEN }}", {}) == "${secrets.TOKEN}"
    assert resolve_expression("no-expr", {}) == "no-expr"


def test_analyze_step() -> None:
    """Test analysis of GHA steps."""
    matrix = {"node-version": "20"}

    # 1. Run step
    step_run = {"name": "Install", "run": "npm ci\nnpm test"}
    status, name, cmds, note = analyze_step(step_run, matrix)
    assert status == "REPRODUCIBLE"
    assert name == "Install"
    assert cmds == ["npm ci", "npm test"]
    assert "shell command" in note

    # 2. Known actions
    step_checkout = {"uses": "actions/checkout@v4"}
    status, name, cmds, note = analyze_step(step_checkout, matrix)
    assert status == "MAPPED"
    assert "git status" in cmds

    step_setup = {"uses": "actions/setup-python@v5"}
    status, name, cmds, note = analyze_step(step_setup, matrix)
    assert status == "MAPPED"
    assert "python --version" in cmds

    step_cache = {"uses": "actions/cache@v4"}
    status, name, cmds, note = analyze_step(step_cache, matrix)
    assert status == "SKIPPED"

    # 3. Third-party action
    step_other = {"uses": "other/action@v1"}
    status, name, cmds, note = analyze_step(step_other, matrix)
    assert status == "WARNING"
    assert "cannot run locally" in note

    # 4. Unknown step type
    status, name, cmds, note = analyze_step({}, matrix)
    assert status == "SKIPPED"


def test_generate_local_script() -> None:
    """Test local reproduction script generation."""
    steps = [
        ("REPRODUCIBLE", "Install", ["npm ci"], "Runs npm ci"),
        ("WARNING", "Upload", [], "Cannot upload"),
    ]
    bash_script = generate_local_script("build", steps, "bash")
    assert "set -euo pipefail" in bash_script
    assert "npm ci" in bash_script
    assert "# Skipped: Upload" in bash_script

    pwsh_script = generate_local_script("build", steps, "powershell")
    assert "$ErrorActionPreference = 'Stop'" in pwsh_script
    assert "npm ci" in pwsh_script


def test_process_workflow_local_integration() -> None:
    """Test end-to-end processing logic with mocks."""
    wf_data = yaml.safe_load(SAMPLE_WORKFLOW)

    with patch("ci_local.parse_workflow", return_value=wf_data), patch(
        "builtins.open", mock_open()
    ) as mock_file:
        # No job specified
        assert process_workflow_local("ci.yml") == 0

        # Invalid job specified
        assert process_workflow_local("ci.yml", "invalid-job") == 1

        # Valid job specified
        assert (
            process_workflow_local(
                "ci.yml", "build", "node-version=18,os=ubuntu-latest"
            )
            == 0
        )
        mock_file.assert_called()

    # Parse error test
    with patch(
        "ci_local.parse_workflow",
        side_effect=ValueError("Parse failed"),
    ):
        assert process_workflow_local("ci.yml", "build") == 1

    # Empty workflow
    with patch("ci_local.parse_workflow", return_value={}):
        assert process_workflow_local("ci.yml", "build") == 1
