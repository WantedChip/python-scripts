"""Unit tests for CLI Workflow Recorder."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Insert src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cli_workflow_recorder.main import (  # noqa: E402
    main,
    record_workflow,
    run_workflow,
    suggest_parameters,
)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture to provide a temporary directory."""
    return tmp_path


def test_suggest_parameters() -> None:
    """Test parameterization suggestions for file paths and numbers."""
    cmd1 = "python scripts/hello.py --input data.csv --port 8080"
    suggestions = suggest_parameters(cmd1)

    assert "data.csv" in suggestions
    assert "8080" in suggestions
    assert suggestions["data.csv"] == "data_path"
    assert suggestions["8080"] == "port_num"


def test_run_workflow(temp_dir: Path) -> None:
    """Test execution of parameterized workflows."""
    wf_file = temp_dir / "wf.json"
    wf_data = {
        "name": "Test Workflow",
        "parameters": {"file_name": "test.txt", "message": "hello"},
        "steps": [
            {
                "name": "Step 1",
                "command": "echo {message} > {file_name}",
                "expected_exit_code": 0,
            }
        ],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    # Run with mocks
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        # Pass CLI params
        run_workflow(wf_file, ["file_name=out.txt", "message=goodbye"], False)

        # Assert correct interpolation
        mock_run.assert_called_once_with(
            "echo goodbye > out.txt", shell=True, capture_output=False, check=False
        )


def test_record_workflow(temp_dir: Path) -> None:
    """Test interactive recording session compilation."""
    wf_file = temp_dir / "recorded.json"

    # Mock inputs:
    # 1. Workflow Name: MyRecordedWorkflow
    # 2. Command 1: echo hello
    # 3. Keep command: y
    # 4. Step 1 Name: Say Hello
    # 5. Stop command: stop
    inputs = ["MyRecordedWorkflow", "echo hello", "y", "Say Hello", "stop"]

    with patch("builtins.input", side_effect=inputs), patch(
        "subprocess.run"
    ) as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        record_workflow(wf_file)

        assert wf_file.is_file()
        with open(wf_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["name"] == "MyRecordedWorkflow"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["name"] == "Say Hello"
        assert data["steps"][0]["command"] == "echo hello"
        assert data["steps"][0]["expected_exit_code"] == 0


def test_cli_run(temp_dir: Path) -> None:
    """Test run subcommand via CLI arguments."""
    wf_file = temp_dir / "wf.json"
    wf_data = {
        "name": "Workflow CLI",
        "parameters": {"val": "123"},
        "steps": [{"name": "Step", "command": "echo {val}", "expected_exit_code": 0}],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    test_args = ["cli_workflow_recorder", "run", str(wf_file), "--param", "val=456"]

    with patch.object(sys, "argv", test_args), patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        main()

        mock_run.assert_called_once_with(
            "echo 456", shell=True, capture_output=False, check=False
        )


def test_run_workflow_missing_file() -> None:
    """Test error code when workflow JSON is missing."""
    with pytest.raises(SystemExit) as exc:
        run_workflow(Path("non_existent_workflow.json"), [], False)
    assert exc.value.code == 1


def test_run_workflow_malformed_json(temp_dir: Path) -> None:
    """Test error code when workflow JSON is malformed."""
    bad_file = temp_dir / "bad.json"
    bad_file.write_text("{malformed json")
    with pytest.raises(SystemExit) as exc:
        run_workflow(bad_file, [], False)
    assert exc.value.code == 1


def test_run_workflow_missing_param(temp_dir: Path) -> None:
    """Test execution abort when a required parameter is missing."""
    wf_file = temp_dir / "wf.json"
    # Workflow uses {missing_param} which isn't defined under parameters
    wf_data = {
        "name": "Bad Workflow",
        "parameters": {},
        "steps": [{"name": "Step", "command": "echo {missing_param}"}],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    with pytest.raises(SystemExit) as exc:
        run_workflow(wf_file, [], False)
    assert exc.value.code == 1


def test_run_workflow_step_failure(temp_dir: Path) -> None:
    """Test workflow termination on command execution failure."""
    wf_file = temp_dir / "wf.json"
    wf_data = {
        "name": "Fail Workflow",
        "parameters": {},
        "steps": [{"name": "Step", "command": "false", "expected_exit_code": 0}],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    with patch("subprocess.run") as mock_run, pytest.raises(SystemExit) as exc:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res
        run_workflow(wf_file, [], False)
    assert exc.value.code == 1


def test_run_workflow_step_failure_ignored(temp_dir: Path) -> None:
    """Test that execution continues when ignore-failures is enabled."""
    wf_file = temp_dir / "wf.json"
    wf_data = {
        "name": "Fail Workflow",
        "parameters": {},
        "steps": [{"name": "Step", "command": "false", "expected_exit_code": 0}],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res
        # Should not raise SystemExit because ignore_failures=True
        run_workflow(wf_file, [], True)


def test_run_workflow_prompt(temp_dir: Path) -> None:
    """Test interactive parameter prompt when not supplied via CLI."""
    wf_file = temp_dir / "wf.json"
    wf_data = {
        "name": "Prompt Workflow",
        "parameters": {"user_val": "default_value"},
        "steps": [{"name": "Step", "command": "echo {user_val}"}],
    }
    with open(wf_file, "w", encoding="utf-8") as f:
        json.dump(wf_data, f)

    with patch("subprocess.run") as mock_run, patch(
        "builtins.input", return_value="custom_value"
    ):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        run_workflow(wf_file, [], False)
        mock_run.assert_called_once_with(
            "echo custom_value", shell=True, capture_output=False, check=False
        )
