import json
import os
import sys
from unittest.mock import MagicMock, patch

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import command_replay  # noqa: E402


def test_run_recording_immediate_exit(tmp_path):
    output_file = os.path.join(tmp_path, "history.json")
    with patch("builtins.input", side_effect=["exit"]):
        command_replay.run_recording(output_file)

    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        data = json.load(f)
        assert data == []


def test_run_recording_keyboard_interrupt(tmp_path):
    output_file = os.path.join(tmp_path, "history.json")
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        command_replay.run_recording(output_file)

    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        data = json.load(f)
        assert data == []


def test_run_recording_commands(tmp_path):
    output_file = os.path.join(tmp_path, "history.json")
    inputs = ["", "echo hello", "ls -la", "done"]  # Empty command
    with patch("builtins.input", side_effect=inputs), patch(
        "subprocess.run"
    ) as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        command_replay.run_recording(output_file)

    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        data = json.load(f)
        assert len(data) == 2
        assert data[0]["command"] == "echo hello"
        assert data[0]["exit_code"] == 0
        assert data[1]["command"] == "ls -la"


def test_run_recording_cd_command(tmp_path):
    output_file = os.path.join(tmp_path, "history.json")
    sub_dir = tmp_path / "mydir"
    sub_dir.mkdir()

    inputs = [f"cd {str(sub_dir)}", "cd non_existent_dir_xyz", "exit"]
    with patch("builtins.input", side_effect=inputs):
        command_replay.run_recording(output_file)

    with open(output_file, "r") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["command"] == f"cd {str(sub_dir)}"
        assert data[0]["cwd"] == str(sub_dir)


def test_run_recording_subprocess_exception(tmp_path, capsys):
    output_file = os.path.join(tmp_path, "history.json")
    with patch("builtins.input", side_effect=["bad_cmd", "exit"]), patch(
        "subprocess.run", side_effect=OSError("Execution failed")
    ):
        command_replay.run_recording(output_file)

    captured = capsys.readouterr()
    assert "Failed to run command: Execution failed" in captured.out


def test_run_parameterize_no_file(capsys):
    command_replay.run_parameterize("nonexistent.json", "script.sh")
    captured = capsys.readouterr()
    assert "Recorded file not found" in captured.err


def test_run_parameterize_bad_json(tmp_path, capsys):
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("invalid json")
    command_replay.run_parameterize(str(bad_json), "script.sh")
    captured = capsys.readouterr()
    assert "Error loading recorded history" in captured.err


def test_run_parameterize_empty_history(tmp_path, capsys):
    empty_json = tmp_path / "empty.json"
    empty_json.write_text("[]")
    command_replay.run_parameterize(str(empty_json), "script.sh")
    captured = capsys.readouterr()
    assert "No commands logged" in captured.out


def test_run_parameterize_sh(tmp_path):
    history_file = tmp_path / "history.json"
    history_data = [
        {"command": "curl http://localhost:8080/api/users", "cwd": "/home/user"},
        {"command": "docker run -p 8080:8080 myapp", "cwd": "/home/user"},
    ]
    with open(history_file, "w") as f:
        json.dump(history_data, f)

    inputs = ["8080", "$PORT", "myapp", "$APP_NAME", ""]  # Done
    output_script = tmp_path / "run.sh"

    with patch("builtins.input", side_effect=inputs):
        command_replay.run_parameterize(str(history_file), str(output_script))

    assert os.path.exists(output_script)
    content = output_script.read_text()
    assert "#!/bin/bash" in content
    assert 'PORT="8080"' in content or 'PORT="8080"' in content
    assert 'APP_NAME="myapp"' in content
    assert "curl http://localhost:$PORT/api/users" in content
    assert "docker run -p $PORT:$PORT $APP_NAME" in content


def test_run_parameterize_ps1(tmp_path):
    history_file = tmp_path / "history.json"
    history_data = [
        {"command": "curl http://localhost:8080/api/users", "cwd": "/home/user"},
        {"command": "docker run -p 8080:8080 myapp", "cwd": "/home/user"},
    ]
    with open(history_file, "w") as f:
        json.dump(history_data, f)

    inputs = ["8080", "%PORT%", "myapp", "$APP_NAME", ""]  # Done
    output_script = tmp_path / "run.ps1"

    with patch("builtins.input", side_effect=inputs):
        command_replay.run_parameterize(str(history_file), str(output_script))

    assert os.path.exists(output_script)
    content = output_script.read_text()
    assert "#!/usr/bin/env pwsh" in content
    assert '$PORT = "8080"' in content
    assert '$APP_NAME = "myapp"' in content
    assert "curl http://localhost:$PORT/api/users" in content
    assert "docker run -p $PORT:$PORT $APP_NAME" in content


def test_main_record():
    with patch("sys.argv", ["command_replay.py", "record", "output.json"]), patch(
        "command_replay.run_recording"
    ) as mock_record:
        command_replay.main()
        mock_record.assert_called_once_with("output.json")


def test_main_parameterize():
    with patch(
        "sys.argv", ["command_replay.py", "parameterize", "input.json", "output.sh"]
    ), patch("command_replay.run_parameterize") as mock_param:
        command_replay.main()
        mock_param.assert_called_once_with("input.json", "output.sh")
